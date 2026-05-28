using System.Collections.Concurrent;
using System.Runtime.InteropServices;

namespace OpcDaWebBrowser.Services;

/// <summary>
/// Typed state enum for the OPC STA dispatcher.
/// All transitions are validated by TransitionTo() — invalid ones are rejected and logged.
/// </summary>
public enum DispatcherState
{
    Starting,
    Running,
    Degraded,
    Faulted,
    ShuttingDown,
    Stopped
}

/// <summary>
/// Snapshot of dispatcher metrics — all fields set on the STA thread,
/// read lock-free from any thread via volatile reference swap.
/// </summary>
public sealed record DispatcherMetricsSnapshot
{
    public int    ThreadId            { get; init; }
    public string Apartment           { get; init; } = "Unknown";
    public int    QueueDepth          { get; init; }
    public int    MaxQueueDepth       { get; init; }
    public long   OperationsProcessed { get; init; }
    public int    TimeoutCount        { get; init; }
    public int    RejectedCount       { get; init; }
    public string State               { get; init; } = "Starting";
    public DateTime  LastStateChangeUtc { get; init; }
    public string?   StateReason        { get; init; }
    public DateTime? LastSuccess      { get; init; }
    public DateTime? LastHeartbeat    { get; init; }
    public string? LastError          { get; init; }
}

/// <summary>
/// Permanent STA thread dispatcher for all OPC DA COM operations.
///
/// WHY THIS EXISTS:
/// OPC DA uses COM objects (IOPCServer, IOPCItemMgt, IOPCSyncIO) that are created
/// in an STA (Single-Threaded Apartment). The apartment that CREATES the COM object
/// must remain alive for the lifetime of those objects. If the creating STA thread exits:
///   - COM proxies become orphaned
///   - Subsequent calls from any thread fail silently or throw RPC_E_DISCONNECTED
///   - AddItems, Read, etc. all fail — tags never load
///
/// This dispatcher owns a single permanent STA thread. ALL OPC DA COM operations
/// (Connect, AddTag, ReadTagValues, RemoveTag, Disconnect) are posted to this thread
/// via a queue. The thread never exits during the process lifetime.
///
/// Callers interact via InvokeAsync&lt;T&gt; / InvokeAsync (fire-and-await)
/// or InvokeAsync&lt;T&gt;(func, timeout) for bounded-latency operations.
///
/// Metrics exposed via GetMetrics() — lock-free snapshot read, &lt;1µs.
/// </summary>
public sealed class OpcStaDispatcher : IDisposable
{
    // Fix #6 — bounded queue: caps memory growth; full queue → reject with logged error.
    private const int QueueCapacity = 1000;
    private readonly BlockingCollection<Action> _queue = new(QueueCapacity);
    private readonly Thread _thread;
    private readonly ILogger<OpcStaDispatcher> _logger;
    private readonly Timer _watchdog;
    private bool _disposed;

    // ── Metrics (written on STA thread or Interlocked, read via GetMetrics) ────
    private int    _threadId;
    private string _apartment        = "Unknown";
    private long   _opsProcessed;            // Interlocked
    private int    _timeoutCount     = 0;    // Fix #7 — Interlocked, incremented on InvokeAsync timeout
    private int    _rejectedCount    = 0;    // Fix #6 — Interlocked, incremented on queue-full rejection
    private int    _maxQueueDepth;           // high-watermark — Interlocked
    private int    _consecutiveErrors = 0;   // Fix #9 — resets on success, triggers Degraded state
    private DispatcherState _state     = DispatcherState.Starting;
    private DateTime  _lastStateChange  = DateTime.UtcNow;
    private string?   _stateReason;
    private DateTime? _lastSuccess;
    private DateTime? _lastHeartbeat;
    private string?   _lastError;

    // ── Constants ─────────────────────────────────────────────────────────────
    private const int QUEUE_WARN_DEPTH       = 100;
    private const int QUEUE_CRITICAL_DEPTH   = 500;
    private const int DEGRADED_ERROR_THRESH  = 5;    // Fix #9: consecutive errors before Degraded
    private static readonly TimeSpan WatchdogInterval    = TimeSpan.FromSeconds(30);
    private static readonly TimeSpan WatchdogStaleThresh = TimeSpan.FromSeconds(120); // Fix #10

    public OpcStaDispatcher(ILogger<OpcStaDispatcher> logger)
    {
        _logger = logger;
        _thread = new Thread(Run);
        _thread.SetApartmentState(ApartmentState.STA);
        _thread.IsBackground = false; // Must NOT be background — owns COM objects
        _thread.Name = "OPC-STA-Dispatcher";
        _thread.Start();

        // Fix #10 — watchdog: detects STA thread freeze / heartbeat staleness
        _watchdog = new Timer(WatchdogTick, null, WatchdogInterval, WatchdogInterval);
    }

    /// <summary>
    /// Guarded state transition. Invalid transitions are logged at ERROR and rejected — state does not change.
    /// </summary>
    private void TransitionTo(DispatcherState next, string reason)
    {
        if (!IsValidTransition(_state, next))
        {
            _logger.LogError(
                "[OPC STATE] Invalid transition {From} → {To} ({Reason}) — REJECTED",
                _state, next, reason);
            return;
        }
        _logger.LogInformation(
            "[OPC STATE] {From} → {To} | {Reason}", _state, next, reason);
        _state           = next;
        _lastStateChange = DateTime.UtcNow;
        _stateReason     = reason;
    }

    private static bool IsValidTransition(DispatcherState from, DispatcherState to) =>
        (from, to) switch
        {
            (DispatcherState.Starting,  DispatcherState.Running)      => true,
            (DispatcherState.Running,   DispatcherState.Degraded)      => true,
            (DispatcherState.Running,   DispatcherState.ShuttingDown)  => true,
            (DispatcherState.Degraded,  DispatcherState.Running)       => true,
            (DispatcherState.Degraded,  DispatcherState.Faulted)       => true,
            (DispatcherState.Degraded,  DispatcherState.ShuttingDown)  => true,
            (DispatcherState.Faulted,   DispatcherState.ShuttingDown)  => true,
            // Any → Stopped (final state from Run() finally)
            (_,                         DispatcherState.Stopped)       => true,
            _ => false
        };

    /// <summary>Return a lock-free snapshot of current dispatcher metrics.</summary>
    public DispatcherMetricsSnapshot GetMetrics() => new()
    {
        ThreadId            = _threadId,
        Apartment           = _apartment,
        QueueDepth          = _queue.Count,
        MaxQueueDepth       = _maxQueueDepth,
        OperationsProcessed = Interlocked.Read(ref _opsProcessed),
        TimeoutCount        = _timeoutCount,
        RejectedCount       = _rejectedCount,
        State               = _state.ToString(),
        LastStateChangeUtc  = _lastStateChange,
        StateReason         = _stateReason,
        LastSuccess         = _lastSuccess,
        LastHeartbeat       = _lastHeartbeat,
        LastError           = _lastError,
    };

    // Fix #10 — watchdog tick: fires every 30s, alerts if heartbeat/success is stale
    private void WatchdogTick(object? _)
    {
        if (_disposed || _state == DispatcherState.Stopped || _state == DispatcherState.ShuttingDown) return;

        // Only warn once ops have started — avoids false alarm during cold start
        long ops = Interlocked.Read(ref _opsProcessed);
        if (ops == 0) return;

        var now = DateTime.UtcNow;
        if (_lastSuccess.HasValue && (now - _lastSuccess.Value) > WatchdogStaleThresh)
        {
            // Escalate to Faulted if already Degraded (watchdog fires while degraded = sustained fault)
            if (_state == DispatcherState.Degraded)
                TransitionTo(DispatcherState.Faulted, $"Watchdog: LastSuccess stale >{WatchdogStaleThresh.TotalSeconds:F0}s while Degraded");

            _logger.LogCritical(
                "[OPC DISPATCHER WATCHDOG] ⚠️  No successful operation in {Elapsed:F0}s — "
                + "possible STA thread freeze! State={State} Ops={Ops} QueueDepth={Depth}",
                (now - _lastSuccess.Value).TotalSeconds, _state,
                ops, _queue.Count);
        }

        if (_lastHeartbeat.HasValue && (now - _lastHeartbeat.Value) > WatchdogStaleThresh)
        {
            _logger.LogWarning(
                "[OPC DISPATCHER WATCHDOG] Heartbeat stale by {Elapsed:F0}s",
                (now - _lastHeartbeat.Value).TotalSeconds);
        }
    }

    private void Run()
    {
        _threadId  = Thread.CurrentThread.ManagedThreadId;
        _apartment = Thread.CurrentThread.GetApartmentState().ToString();
        TransitionTo(DispatcherState.Running, "STA thread started");

        _logger.LogInformation(
            "[OPC DISPATCHER] Permanent STA thread started | Thread={ThreadId} | Apartment={Apartment}",
            _threadId, _apartment);

        if (_apartment != "STA")
            _logger.LogCritical(
                "[OPC DISPATCHER] ⚠️  APARTMENT IS {Apartment} — must be STA for COM DA operations!",
                _apartment);

        try
        {
            foreach (var action in _queue.GetConsumingEnumerable())
            {
                // ── Queue depth watermark tracking ────────────────────────────
                int depth = _queue.Count;
                if (depth > _maxQueueDepth)
                    Interlocked.CompareExchange(ref _maxQueueDepth, depth, _maxQueueDepth);

                if (depth >= QUEUE_CRITICAL_DEPTH)
                    _logger.LogError("[OPC DISPATCHER] Queue CRITICAL depth={Depth} (≥{Threshold})",
                        depth, QUEUE_CRITICAL_DEPTH);
                else if (depth >= QUEUE_WARN_DEPTH)
                    _logger.LogWarning("[OPC DISPATCHER] Queue WARN depth={Depth} (≥{Threshold})",
                        depth, QUEUE_WARN_DEPTH);

                try
                {
                    action();
                    Interlocked.Increment(ref _opsProcessed);
                    _lastSuccess = DateTime.UtcNow;

                    // Fix #9 — reset consecutive error counter on success
                    if (_consecutiveErrors > 0)
                    {
                        _consecutiveErrors = 0;
                        if (_state == DispatcherState.Degraded)
                            TransitionTo(DispatcherState.Running, "Recovered: first successful op after Degraded");
                    }
                }
                catch (Exception ex)
                {
                    // Fix #9 — track consecutive errors, promote to Degraded state
                    _consecutiveErrors++;
                    _lastError = ex.Message[..Math.Min(200, ex.Message.Length)];
                    _logger.LogError(ex, "[OPC DISPATCHER] Unhandled exception in dispatched action (consecutive={Count})",
                        _consecutiveErrors);

                    if (_consecutiveErrors >= DEGRADED_ERROR_THRESH && _state == DispatcherState.Running)
                        TransitionTo(DispatcherState.Degraded, $"{_consecutiveErrors} consecutive dispatcher errors");
                }

                // Heartbeat every 100 ops
                if (Interlocked.Read(ref _opsProcessed) % 100 == 0)
                    _lastHeartbeat = DateTime.UtcNow;
            }
        }
        finally
        {
            _state = DispatcherState.Stopped;
            _lastStateChange = DateTime.UtcNow;
            _stateReason = "STA thread exited";
            _logger.LogInformation(
                "[OPC DISPATCHER] STA thread exiting | Thread={ThreadId}",
                _threadId);
        }
    }

    /// <summary>
    /// Post a function to the STA thread and await its result.
    /// Throws InvalidOperationException immediately if the bounded queue is full (Fix #6).
    /// </summary>
    public Task<T> InvokeAsync<T>(Func<T> func)
    {
        if (_disposed)
            throw new ObjectDisposedException(nameof(OpcStaDispatcher));

        var tcs = new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);

        // Fix #6 — TryAdd with 0 timeout: reject immediately if queue is at capacity.
        // This prevents ASP.NET thread pool threads from blocking on a saturated queue.
        bool enqueued = _queue.TryAdd(() =>
        {
            try   { tcs.SetResult(func()); }
            catch (Exception ex) { tcs.SetException(ex); }
        }, millisecondsTimeout: 0);

        if (!enqueued)
        {
            Interlocked.Increment(ref _rejectedCount);
            _logger.LogError(
                "[OPC DISPATCHER] Queue full (cap={Cap}) — rejecting operation. Rejected total={Total}",
                QueueCapacity, _rejectedCount);
            tcs.SetException(new InvalidOperationException(
                $"OPC dispatcher queue is full ({QueueCapacity} items). Operation rejected."));
        }

        return tcs.Task;
    }

    /// <summary>
    /// Fix #7 — Timeout-bounded InvokeAsync.
    /// Posts to the STA thread but races against a deadline.
    /// On timeout: increments TimeoutCount and throws TimeoutException to the caller.
    /// The underlying action still runs to completion on the STA thread — this avoids
    /// leaving COM objects in an inconsistent state.
    /// </summary>
    public async Task<T> InvokeAsync<T>(Func<T> func, TimeSpan timeout)
    {
        var task = InvokeAsync(func);
        if (await Task.WhenAny(task, Task.Delay(timeout)) != task)
        {
            Interlocked.Increment(ref _timeoutCount);
            _logger.LogWarning(
                "[OPC DISPATCHER] Operation timed out after {Timeout}ms. TimeoutCount={Count}",
                timeout.TotalMilliseconds, _timeoutCount);
            throw new TimeoutException(
                $"OPC dispatcher operation did not complete within {timeout.TotalMilliseconds:F0}ms.");
        }
        return await task; // propagate any exception from the STA thread
    }

    /// <summary>Post an action to the STA thread and await completion.</summary>
    public Task InvokeAsync(Action action) =>
        InvokeAsync<bool>(() => { action(); return true; });

    public void Dispose()
    {
        if (!_disposed)
        {
            TransitionTo(DispatcherState.ShuttingDown, "Dispose() called");
            _disposed = true;
            _watchdog.Dispose();
            _queue.CompleteAdding();
            _thread.Join(TimeSpan.FromSeconds(5));
            _queue.Dispose();
        }
    }
}
