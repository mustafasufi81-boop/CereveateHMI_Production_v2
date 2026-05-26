using System.Collections.Concurrent;
using Microsoft.Extensions.Logging;
using PlcGateway.Interfaces;

namespace PlcGateway.Services;

/// <summary>
/// ISOLATED PLC Connection Worker
/// 
/// CRITICAL DESIGN PRINCIPLES:
/// 1. ONE worker per PLC - completely isolated
/// 2. Own thread/task - no shared resources
/// 3. Own driver instance - no connection sharing
/// 4. Own pool - no data interference
/// 5. Own error state - failures don't cascade
/// 6. Own cancellation token - independent lifecycle
/// 
/// BENEFITS:
/// - PLC1 failure does NOT affect PLC2
/// - Same manufacturer PLCs work independently
/// - Different manufacturers work together
/// - System load distributed across workers
/// - Easy to add/remove PLCs at runtime
/// </summary>
public sealed class PlcWorker : IAsyncDisposable
{
    // ═══════════════════════════════════════════════════════════════════
    // IDENTITY - Unique per worker
    // ═══════════════════════════════════════════════════════════════════
    public string WorkerId { get; }
    public string PlcId { get; }
    public string PlcName { get; }
    public string PlantId { get; }
    public string Protocol { get; }

    // ═══════════════════════════════════════════════════════════════════
    // ISOLATED COMPONENTS - Not shared with any other worker
    // ═══════════════════════════════════════════════════════════════════
    private readonly IPlcDriver _driver;              // Own driver instance
    private readonly PlcWorkerPool _pool;             // Own data pool (for worker stats)
    private readonly PlcTagValuesPoolService? _sharedPool; // Shared pool for API access
    private readonly PlcSampleBufferService? _sampleBuffer; // Shared sample buffer for MQTT
    private readonly PlcWorkerConfig _config;         // Own configuration
    private readonly ILogger _logger;                 // Shared but thread-safe
    private readonly PlcScanRateScheduler? _scheduler; // Scan rate scheduler with deadband
    
    // ═══════════════════════════════════════════════════════════════════
    // LIFECYCLE - Independent control
    // ═══════════════════════════════════════════════════════════════════
    private readonly CancellationTokenSource _cts;    // Own cancellation
    private Task? _pollingTask;                       // Own polling loop
    private readonly SemaphoreSlim _stateLock = new(1, 1);  // Own lock

    // ═══════════════════════════════════════════════════════════════════
    // STATE - Isolated from other workers
    // ═══════════════════════════════════════════════════════════════════
    private PlcWorkerState _state = PlcWorkerState.Created;
    private DateTime _startedAt;
    private DateTime _lastPollTime;
    private DateTime _lastSuccessTime;
    private DateTime _lastFailureTime;
    private int _consecutiveFailures;
    private int _totalPolls;
    private int _successfulPolls;
    private int _failedPolls;
    private long _totalReadTimeMs;
    private long _lastReadTimeMs;  // Most recent single read (raw value)
    private string? _lastError;
    private bool _disposed;

    // ── PLC-offline backoff ────────────────────────────────────────────────
    // Tracks whether we’ve already logged the “PLC offline” warning so we
    // don’t repeat it every second.  Also tracks the backoff window so we
    // don’t call ConnectAsync (and initialize 128 × 2-second timeout tags)
    // every polling tick when the PLC is known unreachable.
    private bool _plcOfflineLogged = false;          // have we emitted the offline notice?
    private int  _workerBackoffSeconds = 0;           // current wait (0 = first attempt)
    private DateTime _workerNextConnectAt = DateTime.MinValue;

    public PlcWorker(
        string plcId,
        string plcName,
        string plantId,
        IPlcDriver driver,
        PlcWorkerConfig config,
        PlcTagValuesPoolService? sharedPool,
        PlcSampleBufferService? sampleBuffer,
        ILogger logger,
        List<PlcTagDefinition>? tagDefinitions = null)
    {
        WorkerId = $"PLCWorker_{plcId}_{Guid.NewGuid():N}";
        PlcId = plcId;
        PlcName = plcName;
        PlantId = plantId;
        Protocol = driver.DriverName;
        
        _driver = driver;
        _config = config;
        _logger = logger;
        _pool = new PlcWorkerPool(plcId, plcName);
        _sharedPool = sharedPool;
        _sampleBuffer = sampleBuffer;
        _cts = new CancellationTokenSource();
        
        // Initialize scan rate scheduler with deadband if tag definitions provided
        if (tagDefinitions != null && tagDefinitions.Count > 0)
        {
            var schedulerConfig = new ScanSchedulerConfig
            {
                DefaultScanRateMs = config.PollingIntervalMs,
                TransmissionIntervalMs = 1000
            };
            _scheduler = new PlcScanRateScheduler(_logger, schedulerConfig);
            _scheduler.Initialize(tagDefinitions);
            
            _logger.LogInformation(
                "[WORKER {WorkerId}] Initialized scheduler with {Count} tags, deadband enabled",
                WorkerId, tagDefinitions.Count);
        }

        _logger.LogInformation(
            "[WORKER {WorkerId}] Created for PLC {PlcId} ({Protocol}), PollingInterval={Interval}ms, SharedPool: {HasShared}, Scheduler: {HasScheduler}",
            WorkerId, PlcId, Protocol, config.PollingIntervalMs, sharedPool != null, _scheduler != null);
    }

    // ═══════════════════════════════════════════════════════════════════
    // LIFECYCLE CONTROL
    // ═══════════════════════════════════════════════════════════════════

    /// <summary>
    /// Start the worker - begins isolated polling loop
    /// </summary>
    public async Task StartAsync()
    {
        await _stateLock.WaitAsync();
        try
        {
            if (_state != PlcWorkerState.Created && _state != PlcWorkerState.Stopped)
            {
                _logger.LogWarning("[WORKER {WorkerId}] Cannot start - current state: {State}",
                    WorkerId, _state);
                return;
            }

            TransitionTo(PlcWorkerState.Starting, "StartAsync called");
            _startedAt = DateTime.UtcNow;
            
            // Start polling loop in dedicated task
            _pollingTask = Task.Run(() => PollingLoopAsync(_cts.Token));
            
            TransitionTo(PlcWorkerState.Running, "Polling loop task started");
            
            _logger.LogInformation("[WORKER {WorkerId}] Started polling loop", WorkerId);
        }
        finally
        {
            _stateLock.Release();
        }
    }

    /// <summary>
    /// Stop the worker gracefully
    /// </summary>
    public async Task StopAsync(TimeSpan? timeout = null)
    {
        await _stateLock.WaitAsync();
        try
        {
            if (_state != PlcWorkerState.Running)
            {
                return;
            }

            TransitionTo(PlcWorkerState.Stopping, "StopAsync called");
            _logger.LogInformation("[WORKER {WorkerId}] Stopping...", WorkerId);

            // Signal cancellation
            _cts.Cancel();

            // Wait for polling loop to exit
            if (_pollingTask != null)
            {
                var waitTask = Task.WhenAny(
                    _pollingTask,
                    Task.Delay(timeout ?? TimeSpan.FromSeconds(10))
                );
                await waitTask;
            }

            // Disconnect driver
            try
            {
                await _driver.DisconnectAsync();
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "[WORKER {WorkerId}] Error during disconnect", WorkerId);
            }

            TransitionTo(PlcWorkerState.Stopped, "Polling loop exited, driver disconnected");
            _logger.LogInformation("[WORKER {WorkerId}] Stopped", WorkerId);
        }
        finally
        {
            _stateLock.Release();
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    // ISOLATED POLLING LOOP - Runs in dedicated task
    // ═══════════════════════════════════════════════════════════════════

    private async Task PollingLoopAsync(CancellationToken ct)
    {
        _logger.LogWarning("[WORKER] Polling loop started for {PlcId} | Interval: {Interval}ms", PlcId, _config.PollingIntervalMs);
        _logger.LogInformation(
            "[WORKER {WorkerId}] Polling loop started - Interval: {Interval}ms",
            WorkerId, _config.PollingIntervalMs);

        while (!ct.IsCancellationRequested)
        {
            var cycleStart = DateTime.UtcNow;
            
            try
            {
                // STEP 1: Ensure connected
                if (!_driver.IsConnected)
                {
                    // ── Backoff guard ────────────────────────────────────────────
                    // If we’re still inside the backoff window, skip the
                    // connect attempt entirely — just wait until the next tick.
                    if (_workerBackoffSeconds > 0 && DateTime.UtcNow < _workerNextConnectAt)
                    {
                        TransitionTo(PlcWorkerState.Disconnected, "In backoff period, waiting before retry");
                        var waitMs = (int)(_workerNextConnectAt - DateTime.UtcNow).TotalMilliseconds;
                        if (waitMs > 0)
                            await Task.Delay(Math.Min(waitMs, 5000), ct);  // wake up at most every 5 s
                        continue;
                    }

                    // Log the offline notice only on first occurrence or after recovery
                    if (!_plcOfflineLogged)
                    {
                        _logger.LogWarning(
                            "[WORKER] '{PlcId}' is OFFLINE. Will retry every {Sec}s (max 120s). " +
                            "No further offline warnings until it recovers.",
                            PlcId, Math.Max(_workerBackoffSeconds, 30));
                        _plcOfflineLogged = true;
                    }

                    TransitionTo(PlcWorkerState.Connecting, "Driver not connected, attempting connection");
                    await ConnectWithRetryAsync(ct);

                    if (!_driver.IsConnected)
                    {
                        // Still offline — apply / increase backoff
                        _workerBackoffSeconds = Math.Min(
                            _workerBackoffSeconds == 0 ? 30 : _workerBackoffSeconds * 2,
                            120);
                        _workerNextConnectAt = DateTime.UtcNow.AddSeconds(_workerBackoffSeconds);
                        TransitionTo(PlcWorkerState.Disconnected, $"Connection failed, backoff for {_workerBackoffSeconds}s");
                        continue;
                    }

                    // ── PLC came back online ───────────────────────────────
                    _workerBackoffSeconds = 0;
                    _workerNextConnectAt  = DateTime.MinValue;
                    _plcOfflineLogged     = false;
                    _logger.LogInformation(
                        "[WORKER] '{PlcId}' is back ONLINE — resuming normal polling.", PlcId);
                    TransitionTo(PlcWorkerState.Running, "PLC reconnected successfully");
                }

                // STEP 2: Determine which tags are DUE for this tick
                _lastPollTime = DateTime.UtcNow;
                _totalPolls++;
                
                PlcReadResult readResult;
                List<string>? tagsDue = null;
                
                if (_scheduler != null)
                {
                    // INDUSTRY-STANDARD: Only read tags that are DUE based on per-tag scan rates
                    // This prevents PLC overload - we don't read all tags every tick
                    tagsDue = _scheduler.GetTagsDueForScan();
                    
                    if (tagsDue.Count == 0)
                    {
                        // No tags due this tick - skip PLC read entirely
                        _logger.LogTrace("[WORKER {WorkerId}] No tags due this tick, skipping PLC read", WorkerId);
                        goto CalculateDelay;
                    }
                    
                    _logger.LogDebug("[WORKER {WorkerId}] Poll #{Poll}: {DueCount} tags due for scan", 
                        WorkerId, _totalPolls, tagsDue.Count);
                    
                    // BATCH READ only the due tags - efficient PLC communication
                    readResult = await _driver.ReadTagsAsync(tagsDue);
                }
                else
                {
                    // Fallback: No scheduler, read all tags (legacy behavior)
                    _logger.LogDebug("[WORKER {WorkerId}] ReadAllTagsAsync Poll #{Poll}", WorkerId, _totalPolls);
                    readResult = await _driver.ReadAllTagsAsync();
                }
                
                _logger.LogDebug("[WORKER {WorkerId}] Read complete: Success={Success}, Count={Count}, Duration={Ms}ms", 
                    WorkerId, readResult.Success, readResult.Values?.Count ?? 0, readResult.ReadDurationMs);
                
                // STEP 3: Process results - update pools and sample buffer
                if (readResult.Success && readResult.Values.Count > 0)
                {
                    // Local pool gets read values (for diagnostics)
                    _pool.Update(readResult.Values, readResult.ReadDurationMs);
                    
                    // Process through scheduler (updates next scan times, applies deadband)
                    if (_scheduler != null)
                    {
                        _scheduler.ProcessScannedValues(readResult.Values);
                    }
                    
                    // SAMPLE BUFFER: Buffer ALL read values (they are already filtered to due tags)
                    if (_sampleBuffer != null)
                    {
                        var samples = readResult.Values.Select(v => new TagSampleEntry
                        {
                            PlcId = PlcId,
                            Address = v.Address,
                            TagName = v.TagName,
                            Value = v.Value,
                            DataType = v.DataType,
                            Quality = v.Quality.ToString(),
                            Timestamp = v.Timestamp,
                            ScanRateMs = _scheduler?.GetTagScanRate(v.Address) ?? _config.PollingIntervalMs,
                            BufferedAt = DateTime.UtcNow
                        }).ToList();
                        
                        _sampleBuffer.AddSamples(samples);
                        
                        // LOG: Confirm PLC read with sample values
                        var firstTag = samples.FirstOrDefault();
                        if (firstTag != null)
                        {
                            _logger.LogWarning("[PLC READ] {Time} | {Count} tags | First: {Tag}={Value}",
                                DateTime.Now.ToString("HH:mm:ss.fff"), samples.Count, firstTag.TagName, firstTag.Value);
                        }
                    }
                    
                    // SHARED POOL: Update with latest values (for API/HMI that want just current value)
                    if (_sharedPool != null)
                    {
                        var cacheEntries = readResult.Values.Select(v => new PlcTagValueCacheEntry
                        {
                            PlcId = PlcId,
                            Address = v.Address,
                            TagName = v.TagName,
                            Value = v.Value,
                            DataType = v.DataType,
                            Quality = ConvertQuality(v.Quality),
                            Timestamp = v.Timestamp,
                            CachedAt = DateTime.UtcNow
                        }).ToList();
                        
                        _sharedPool.UpdateFromPlc(PlcId, cacheEntries, DateTime.UtcNow);
                    }
                    
                    _lastSuccessTime = DateTime.UtcNow;
                    _successfulPolls++;
                    _consecutiveFailures = 0;
                    _totalReadTimeMs += readResult.ReadDurationMs;
                    _lastReadTimeMs = readResult.ReadDurationMs;  // Raw value for dashboard
                    _lastError = null;

                    _logger.LogDebug(
                        "[WORKER {WorkerId}] Poll OK: {Count} tags in {Ms}ms",
                        WorkerId, readResult.TagsRead, readResult.ReadDurationMs);
                }
                else
                {
                    HandlePollFailure(readResult.ErrorMessage ?? "Unknown error");
                }
            }
            catch (OperationCanceledException)
            {
                // Normal shutdown
                break;
            }
            catch (Exception ex)
            {
                HandlePollFailure(ex.Message);
                _logger.LogError(ex, "[WORKER {WorkerId}] Poll exception", WorkerId);
                
                // Disconnect on critical error
                try { await _driver.DisconnectAsync(); } catch { }
            }

            // STEP 4: Calculate delay until next tag is due
            CalculateDelay:
            // Use minimum scan rate as base tick - simple and reliable
            var baseTick = _scheduler?.GetMinimumScanIntervalMs() ?? _config.PollingIntervalMs;
            var elapsed = (DateTime.UtcNow - cycleStart).TotalMilliseconds;
            var delay = Math.Max(1, baseTick - (int)elapsed);
            
            if (delay > 0 && !ct.IsCancellationRequested)
            {
                await Task.Delay(delay, ct);
            }
        }

        _logger.LogInformation("[WORKER {WorkerId}] Polling loop exited", WorkerId);
    }

    private async Task ConnectWithRetryAsync(CancellationToken ct)
    {
        for (int attempt = 1; attempt <= _config.MaxConnectRetries; attempt++)
        {
            if (ct.IsCancellationRequested) break;

            _logger.LogInformation(
                "[WORKER {WorkerId}] Connection attempt {Attempt}/{Max}",
                WorkerId, attempt, _config.MaxConnectRetries);

            try
            {
                if (await _driver.ConnectAsync())
                {
                    _logger.LogInformation(
                        "[WORKER {WorkerId}] Connected to {Ip}",
                        WorkerId, _config.IpAddress);
                    return;
                }
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex,
                    "[WORKER {WorkerId}] Connection attempt {Attempt} failed",
                    WorkerId, attempt);
            }

            if (attempt < _config.MaxConnectRetries)
            {
                await Task.Delay(_config.ReconnectDelayMs, ct);
            }
        }

        _lastError = $"Failed to connect after {_config.MaxConnectRetries} attempts";
        _logger.LogError("[WORKER {WorkerId}] {Error}", WorkerId, _lastError);
    }

    private void HandlePollFailure(string error)
    {
        _failedPolls++;
        _consecutiveFailures++;
        _lastFailureTime = DateTime.UtcNow;
        _lastError = error;

        _logger.LogWarning(
            "[WORKER {WorkerId}] Poll failed ({Consecutive}x): {Error}",
            WorkerId, _consecutiveFailures, error);

        // Mark pool as stale
        _pool.MarkStale();
        
        // Also mark shared pool as disconnected
        _sharedPool?.MarkPlcDisconnected(PlcId, error);
        
        // Transition to Faulted state after threshold
        if (_consecutiveFailures >= 5 && _state != PlcWorkerState.Faulted)
        {
            TransitionTo(PlcWorkerState.Faulted, 
                $"Too many consecutive failures ({_consecutiveFailures})");
        }
    }

    private PlcTagQuality ConvertQuality(Interfaces.PlcQuality quality)
    {
        return quality switch
        {
            Interfaces.PlcQuality.Good => PlcTagQuality.Good,
            Interfaces.PlcQuality.Bad => PlcTagQuality.Bad,
            Interfaces.PlcQuality.Uncertain => PlcTagQuality.Uncertain,
            Interfaces.PlcQuality.CommError => PlcTagQuality.CommError,
            _ => PlcTagQuality.NotConfigured
        };
    }

    // ═══════════════════════════════════════════════════════════════════
    // DATA ACCESS - Thread-safe read from isolated pool
    // ═══════════════════════════════════════════════════════════════════

    /// <summary>
    /// Get all current values from this worker's pool
    /// </summary>
    public List<PlcTagValue> GetValues() => _pool.GetAllValues();

    /// <summary>
    /// Get specific tag value
    /// </summary>
    public PlcTagValue? GetValue(string address) => _pool.GetValue(address);

    // ═══════════════════════════════════════════════════════════════════
    // STATE MACHINE (OPC Gold Standard Pattern)
    // ═══════════════════════════════════════════════════════════════════

    /// <summary>
    /// Validated state transition with logging
    /// </summary>
    private void TransitionTo(PlcWorkerState next, string reason)
    {
        if (!IsValidTransition(_state, next))
        {
            _logger.LogError(
                "[WORKER {WorkerId}] Invalid state transition {From} → {To} — REJECTED: {Reason}",
                WorkerId, _state, next, reason);
            return;
        }

        var prev = _state;
        _state = next;
        
        _logger.LogInformation(
            "[WORKER {WorkerId}] State: {From} → {To} ({Reason})",
            WorkerId, prev, next, reason);
    }

    /// <summary>
    /// Validate state transition rules
    /// </summary>
    private bool IsValidTransition(PlcWorkerState from, PlcWorkerState to)
    {
        return (from, to) switch
        {
            // Created can only start
            (PlcWorkerState.Created, PlcWorkerState.Starting) => true,
            
            // Starting can run or be stopped
            (PlcWorkerState.Starting, PlcWorkerState.Running) => true,
            (PlcWorkerState.Starting, PlcWorkerState.Stopped) => true,
            
            // Running can disconnect, stop, or fault
            (PlcWorkerState.Running, PlcWorkerState.Connecting) => true,
            (PlcWorkerState.Running, PlcWorkerState.Disconnected) => true,
            (PlcWorkerState.Running, PlcWorkerState.Stopping) => true,
            (PlcWorkerState.Running, PlcWorkerState.Faulted) => true,
            
            // Connecting outcomes
            (PlcWorkerState.Connecting, PlcWorkerState.Running) => true,
            (PlcWorkerState.Connecting, PlcWorkerState.Disconnected) => true,
            (PlcWorkerState.Connecting, PlcWorkerState.Faulted) => true,
            
            // Disconnected can retry, stop, or fault
            (PlcWorkerState.Disconnected, PlcWorkerState.Connecting) => true,
            (PlcWorkerState.Disconnected, PlcWorkerState.Stopping) => true,
            (PlcWorkerState.Disconnected, PlcWorkerState.Faulted) => true,
            
            // Faulted requires manual intervention (stop only)
            (PlcWorkerState.Faulted, PlcWorkerState.Stopping) => true,
            (PlcWorkerState.Faulted, PlcWorkerState.Connecting) => true,  // Allow retry from Faulted
            
            // Stopping always succeeds
            (PlcWorkerState.Stopping, PlcWorkerState.Stopped) => true,
            
            // Stopped can restart
            (PlcWorkerState.Stopped, PlcWorkerState.Starting) => true,
            
            // All other transitions invalid
            _ => false
        };
    }

    /// <summary>
    /// Get worker status
    /// </summary>
    public PlcWorkerStatus GetStatus()
    {
        return new PlcWorkerStatus
        {
            WorkerId = WorkerId,
            PlcId = PlcId,
            PlcName = PlcName,
            PlantId = PlantId,
            Protocol = Protocol,
            IpAddress = _config.IpAddress,
            Port = _config.Port,
            State = _state,
            IsConnected = _driver.IsConnected,
            StartedAt = _startedAt,
            LastPollTime = _lastPollTime,
            LastSuccessTime = _lastSuccessTime,
            LastFailureTime = _lastFailureTime,
            ConsecutiveFailures = _consecutiveFailures,
            TotalPolls = _totalPolls,
            SuccessfulPolls = _successfulPolls,
            FailedPolls = _failedPolls,
            AverageReadTimeMs = _successfulPolls > 0 ? _totalReadTimeMs / _successfulPolls : 0,
            LastReadTimeMs = _lastReadTimeMs,  // Raw value from last poll
            TagCount = _pool.TagCount,
            PoolLastUpdate = _pool.LastUpdateTime,
            IsPoolStale = _pool.IsStale,
            LastError = _lastError,
            PollingIntervalMs = _config.PollingIntervalMs,
            ScanRateStats = _scheduler?.GetStats()
        };
    }

    // ═══════════════════════════════════════════════════════════════════
    // CLEANUP
    // ═══════════════════════════════════════════════════════════════════

    public async ValueTask DisposeAsync()
    {
        if (_disposed) return;
        _disposed = true;

        await StopAsync();
        
        _cts.Dispose();
        _stateLock.Dispose();
        _driver.Dispose();
        
        _logger.LogInformation("[WORKER {WorkerId}] Disposed", WorkerId);
    }
}

/// <summary>
/// Worker states
/// </summary>
public enum PlcWorkerState
{
    Created,
    Starting,
    Connecting,
    Running,
    Disconnected,
    Stopping,
    Stopped,
    Faulted
}

/// <summary>
/// Worker configuration
/// </summary>
public class PlcWorkerConfig
{
    public string IpAddress { get; set; } = "";
    public int Port { get; set; }
    public int PollingIntervalMs { get; set; } = 1000;
    public int ReconnectDelayMs { get; set; } = 5000;
    public int MaxConnectRetries { get; set; } = 3;
    public int ReadTimeoutMs { get; set; } = 3000;
}

/// <summary>
/// Worker status for monitoring
/// </summary>
public class PlcWorkerStatus
{
    public string WorkerId { get; set; } = "";
    public string PlcId { get; set; } = "";
    public string PlcName { get; set; } = "";
    public string PlantId { get; set; } = "";
    public string Protocol { get; set; } = "";
    public string IpAddress { get; set; } = "";
    public int Port { get; set; }
    public PlcWorkerState State { get; set; }
    public bool IsConnected { get; set; }
    public DateTime StartedAt { get; set; }
    public DateTime LastPollTime { get; set; }
    public DateTime LastSuccessTime { get; set; }
    public DateTime LastFailureTime { get; set; }
    public int ConsecutiveFailures { get; set; }
    public int TotalPolls { get; set; }
    public int SuccessfulPolls { get; set; }
    public int FailedPolls { get; set; }
    public long AverageReadTimeMs { get; set; }
    public long LastReadTimeMs { get; set; }  // Raw value from last poll
    public int TagCount { get; set; }
    public DateTime PoolLastUpdate { get; set; }
    public bool IsPoolStale { get; set; }
    public string? LastError { get; set; }
    public int PollingIntervalMs { get; set; }
    
    // Scan Rate Scheduler Statistics
    public ScanSchedulerStats? ScanRateStats { get; set; }
}
