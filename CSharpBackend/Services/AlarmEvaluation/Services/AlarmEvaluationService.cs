using OpcDaWebBrowser.Services.AlarmEvaluation.Config;
using OpcDaWebBrowser.Services.AlarmEvaluation.Models;
using PlcGateway.Services;
using PlcGateway.Transport;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Globalization;
using System.Text.Json;

namespace OpcDaWebBrowser.Services.AlarmEvaluation.Services;

/// <summary>
/// AlarmEvaluationService — Phase 1 orchestrator (thin coordinator).
///
/// Responsibilities:
///   1. On startup: update DB schema, initialize setpoint cache, run reconciliation
///   2. Poll TagValuesPoolService every EvaluationIntervalMs
///   3. For each tag+level: check suppression, onset delay, then delegate to AlarmStateManager
///   4. Subscribe to AlarmStateManager.TransitionOccurred → publish MQTT (fire-and-forget)
///   5. Expose GetDiagnostics() and TestRaiseAlarmAsync() for the diagnostics controller
///
/// This class no longer writes to DB directly.
/// All state transitions are performed exclusively by AlarmStateManager.
/// </summary>
public sealed class AlarmEvaluationService : BackgroundService
{
    private readonly TagValuesPoolService       _tagPool;
    private readonly PlcTagValuesPoolService    _plcTagPool;
    private readonly AlarmSetpointCacheService  _setpointCache;
    private readonly AlarmStateManager          _stateManager;
    private readonly AlarmDelayTracker          _delayTracker;
    private readonly AlarmReconciliationService _reconciliation;
    private readonly AlarmEvaluationConfig      _alarmConfig;
    private readonly OpcMqttTransportConfig     _mqttTransportConfig;
    private readonly ILogger<AlarmEvaluationService> _logger;

    private MqttPublisher? _mqttPublisher;
    private long _evaluationCycles;

    private static readonly JsonSerializerOptions _json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase
    };

    public AlarmEvaluationService(
        TagValuesPoolService tagPool,
        PlcTagValuesPoolService plcTagPool,
        AlarmSetpointCacheService setpointCache,
        AlarmStateManager stateManager,
        AlarmDelayTracker delayTracker,
        AlarmReconciliationService reconciliation,
        AlarmEvaluationConfig alarmConfig,
        OpcMqttTransportConfig mqttTransportConfig,
        ILogger<AlarmEvaluationService> logger)
    {
        _tagPool             = tagPool             ?? throw new ArgumentNullException(nameof(tagPool));
        _plcTagPool          = plcTagPool          ?? throw new ArgumentNullException(nameof(plcTagPool));
        _setpointCache       = setpointCache       ?? throw new ArgumentNullException(nameof(setpointCache));
        _stateManager        = stateManager        ?? throw new ArgumentNullException(nameof(stateManager));
        _delayTracker        = delayTracker        ?? throw new ArgumentNullException(nameof(delayTracker));
        _reconciliation      = reconciliation      ?? throw new ArgumentNullException(nameof(reconciliation));
        _alarmConfig         = alarmConfig         ?? throw new ArgumentNullException(nameof(alarmConfig));
        _mqttTransportConfig = mqttTransportConfig ?? throw new ArgumentNullException(nameof(mqttTransportConfig));
        _logger              = logger              ?? throw new ArgumentNullException(nameof(logger));
    }

    // =========================================================
    // BACKGROUND SERVICE ENTRY POINT
    // =========================================================

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!_alarmConfig.Enabled)
        {
            _logger.LogWarning("AlarmEvaluationService DISABLED (AlarmEvaluation:Enabled=false)");
            return;
        }

        _logger.LogInformation("AlarmEvaluationService starting (interval={Interval}ms)", _alarmConfig.EvaluationIntervalMs);

        // 1. Update DB schema (historian_events constraint → Phase 1 states)
        await _stateManager.InitializeSchemaAsync(stoppingToken);

        // 2. Load setpoints from DB
        await _setpointCache.InitializeAsync(stoppingToken);
        _logger.LogInformation("AlarmEvaluationService: setpoint cache ready — {Count} tags", _setpointCache.Count);

        // 3. Startup reconciliation — rebuild runtime state from live OPC values
        await _reconciliation.ReconcileAsync(stoppingToken);
        _logger.LogInformation("AlarmEvaluationService: reconciliation complete — {Active} alarms in memory", _stateManager.ActiveCount);

        // 4. Wire MQTT publisher (optional)
        InitialiseMqttPublisher();

        // 5. Subscribe to state transitions for MQTT publish
        _stateManager.TransitionOccurred += OnTransitionOccurred;

        // 6. Main evaluation loop
        _logger.LogInformation("AlarmEvaluationService: entering evaluation loop");
        while (!stoppingToken.IsCancellationRequested)
        {
            var sw = Stopwatch.StartNew();
            try
            {
                await EvaluateCycleAsync(stoppingToken);
                Interlocked.Increment(ref _evaluationCycles);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
            catch (Exception ex)
            {
                _logger.LogError(ex, "AlarmEvaluationService: unhandled exception in evaluation cycle");
            }

            // CRITICAL: Task.Delay must be inside try/catch — if stoppingToken fires here
            // the uncaught OperationCanceledException would kill the BackgroundService loop permanently.
            try
            {
                var elapsed = (int)sw.ElapsedMilliseconds;
                var delay   = Math.Max(0, _alarmConfig.EvaluationIntervalMs - elapsed);
                if (delay > 0)
                    await Task.Delay(delay, stoppingToken).ConfigureAwait(false);
            }
            catch (OperationCanceledException) { break; }
        }

        _stateManager.TransitionOccurred -= OnTransitionOccurred;
        _logger.LogInformation("AlarmEvaluationService stopped. Cycles={C}, Active={A}",
            _evaluationCycles, _stateManager.ActiveCount);
    }

    // =========================================================
    // EVALUATION CYCLE
    // =========================================================

    private static readonly AlarmLevel[] _allLevels =
        [AlarmLevel.HighHigh, AlarmLevel.High, AlarmLevel.Low, AlarmLevel.LowLow];

    private async Task EvaluateCycleAsync(CancellationToken ct)
    {
        var alarmTagIds = _setpointCache.GetAllAlarmTagIds();
        if (alarmTagIds.Count == 0) return;

        var tagValues = _tagPool.GetTagValues(alarmTagIds);

        // MERGE: also check PLC pool for any alarm tags not found in OPC DA pool
        // PLC tags (TURBINE_LOADMW, BEARING_VIB_*, etc.) live in PlcTagValuesPoolService
        var opcTagIds = new HashSet<string>(tagValues.Select(t => t.TagId), StringComparer.OrdinalIgnoreCase);
        var missingIds = alarmTagIds.Where(id => !opcTagIds.Contains(id)).ToList();
        if (missingIds.Count > 0)
        {
            var plcEntries = _plcTagPool.GetTagValues(missingIds, plcId: null);
            foreach (var plc in plcEntries)
            {
                var valueStr = plc.Value?.ToString() ?? "";
                var quality  = plc.Quality == PlcTagQuality.Good ? "Good" : "Bad";
                tagValues.Add(new TagValueCacheEntry
                {
                    TagId     = plc.TagName.Length > 0 ? plc.TagName : plc.Address,
                    Value     = valueStr,
                    Quality   = quality,
                    Timestamp = plc.Timestamp,
                    UpdatedAt = plc.Quality != PlcTagQuality.Good
                              ? DateTime.UtcNow.AddSeconds(-60)  // force IsStale=true for bad-quality tags
                              : plc.CachedAt
                });
            }
        }

        if (tagValues.Count == 0) return;

        // Snapshot of all runtime states for suppression checks (lock-free read)
        var allStates = _stateManager.GetAllStates();

        foreach (var entry in tagValues)
        {
            if (ct.IsCancellationRequested) break;

            // Quality gating: Bad / Stale / Uncertain → keep current state unchanged
            if (entry.IsStale || !IsGoodQuality(entry.Quality)) continue;

            // Only numeric tags are evaluated
            if (!double.TryParse(entry.Value, NumberStyles.Any, CultureInfo.InvariantCulture, out var val))
                continue;

            var setpoint = _setpointCache.GetSetpoint(entry.TagId);
            if (setpoint == null) continue;

            // Convert to DateTimeOffset safely: DateTime.Now (Kind=Local) from pool must be
            // converted to UTC first — DateTimeOffset(localDt, TimeSpan.Zero) throws ArgumentException.
            var ts = new DateTimeOffset(entry.Timestamp.ToUniversalTime());

            await EvaluateTagAsync(entry.TagId, val, setpoint, ts, allStates, ct);
        }
    }

    private async Task EvaluateTagAsync(
        string tagId, double value, AlarmSetpoint setpoint,
        DateTimeOffset ts, IReadOnlyDictionary<string, AlarmRuntimeState> allStates,
        CancellationToken ct)
    {
        foreach (var level in _allLevels)
        {
            // Only evaluate levels that are configured for this tag
            if (!IsLevelConfigured(level, setpoint)) continue;

            var alarmKey     = AlarmRuntimeState.BuildKey(tagId, level);
            var currentState = _stateManager.GetState(alarmKey);
            var inAlarmZone  = IsInAlarmZone(value, level, setpoint);

            if (inAlarmZone)
            {
                // ── Value is in alarm zone ──────────────────────────
                var isAlreadyActive = currentState?.State is AlarmState4.ActiveUnack or AlarmState4.ActiveAck;

                if (!isAlreadyActive)
                {
                    // Check ISA-18.2 suppression (H suppressed by HH, L by LL)
                    if (AlarmSuppressionEngine.IsSuppressed(level, tagId, allStates))
                    {
                        _delayTracker.Cancel(alarmKey);  // Clear any pending delay if suppressed
                        continue;
                    }

                    // Check onset delay — returns true when delay elapsed or zero
                    if (_delayTracker.TryStartOrCheck(alarmKey, level, value, setpoint.OnsetDelaySeconds))
                    {
                        await _stateManager.RaiseAsync(tagId, level, value,
                            GetSetpointForLevel(level, setpoint),
                            setpoint.AlarmPriority, ts, ct);
                    }
                }
                // If already active — no action (alarm stays until RTN)
            }
            else
            {
                // ── Value is outside alarm zone ──────────────────────
                // Cancel any pending onset delay
                if (_delayTracker.IsPending(alarmKey))
                    _delayTracker.Cancel(alarmKey);

                // If alarm is active, check asymmetric hysteresis (deadband for exit)
                if (currentState?.State is AlarmState4.ActiveUnack or AlarmState4.ActiveAck)
                {
                    if (HasExitedAlarmZone(value, level, setpoint))
                    {
                        await _stateManager.MarkRtnAsync(tagId, level, value, ts, ct);
                    }
                }
            }
        }
    }

    // =========================================================
    // ALARM LEVEL HELPERS (pure functions — no side effects)
    // =========================================================

    private static bool IsLevelConfigured(AlarmLevel level, AlarmSetpoint sp) => level switch
    {
        AlarmLevel.HighHigh => sp.HhLimit.HasValue,
        AlarmLevel.High     => sp.HLimit.HasValue,
        AlarmLevel.LowLow   => sp.LlLimit.HasValue,
        AlarmLevel.Low      => sp.LLimit.HasValue,
        _                   => false,
    };

    private static bool IsInAlarmZone(double value, AlarmLevel level, AlarmSetpoint sp) => level switch
    {
        AlarmLevel.HighHigh => sp.HhLimit.HasValue && value >= sp.HhLimit.Value,
        AlarmLevel.High     => sp.HLimit.HasValue  && value >= sp.HLimit.Value,
        AlarmLevel.LowLow   => sp.LlLimit.HasValue && value <= sp.LlLimit.Value,
        AlarmLevel.Low      => sp.LLimit.HasValue  && value <= sp.LLimit.Value,
        _                   => false,
    };

    /// <summary>
    /// Returns true when value has cleared the setpoint by the full deadband (asymmetric hysteresis).
    /// Prevents chatter when value oscillates near the threshold.
    /// </summary>
    private static bool HasExitedAlarmZone(double value, AlarmLevel level, AlarmSetpoint sp)
    {
        var db = sp.AlarmDeadband;
        return level switch
        {
            AlarmLevel.HighHigh => sp.HhLimit.HasValue && value < (sp.HhLimit.Value - db),
            AlarmLevel.High     => sp.HLimit.HasValue  && value < (sp.HLimit.Value  - db),
            AlarmLevel.LowLow   => sp.LlLimit.HasValue && value > (sp.LlLimit.Value + db),
            AlarmLevel.Low      => sp.LLimit.HasValue  && value > (sp.LLimit.Value  + db),
            _                   => true,
        };
    }

    private static double? GetSetpointForLevel(AlarmLevel level, AlarmSetpoint sp) => level switch
    {
        AlarmLevel.HighHigh => sp.HhLimit,
        AlarmLevel.High     => sp.HLimit,
        AlarmLevel.LowLow   => sp.LlLimit,
        AlarmLevel.Low      => sp.LLimit,
        _                   => null,
    };

    private static bool IsGoodQuality(string quality) =>
        quality is "Good" or "G" or "GOOD";

    // =========================================================
    // MQTT PUBLISH (fire-and-forget via TransitionOccurred event)
    // =========================================================

    private void OnTransitionOccurred(object? sender, AlarmTransitionEvent evt)
    {
        if (_mqttPublisher == null) return;
        _ = PublishTransitionAsync(evt);
    }

    private async Task PublishTransitionAsync(AlarmTransitionEvent evt)
    {
        if (_mqttPublisher == null) return;

        var transition = evt.ToState switch
        {
            AlarmState4.ActiveUnack => "ACTIVE_UNACK",
            AlarmState4.ActiveAck   => "ACTIVE_ACK",
            AlarmState4.RtnUnack    => "RTN_UNACK",
            AlarmState4.None        => "CLEARED",
            _                       => "UNKNOWN",
        };

        var topic = evt.ToState switch
        {
            AlarmState4.ActiveUnack => $"{_alarmConfig.MqttAlarmTopic}/raised",
            AlarmState4.ActiveAck   => $"{_alarmConfig.MqttAlarmTopic}/ack",
            AlarmState4.RtnUnack    => $"{_alarmConfig.MqttAlarmTopic}/rtn",
            AlarmState4.None        => $"{_alarmConfig.MqttAlarmTopic}/cleared",
            _                       => _alarmConfig.MqttAlarmTopic,
        };

        var payload = JsonSerializer.Serialize(new
        {
            alarm_key      = evt.AlarmKey,
            occurrence_id  = evt.OccurrenceId,
            transition      = transition,
            event_type     = evt.EventType,          // Issue 7: explicit event type string
            new_state      = transition,              // Issue 7: alias for HMI consumers
            tag_id         = evt.TagId,
            level          = evt.Level.ToString(),
            event_id       = evt.EventId,
            transition_seq = evt.TransitionSeq,      // Issue 1: global monotonic sequence
            value          = evt.Value,
            setpoint       = evt.SetpointValue,
            @operator      = evt.Operator,
            timestamp      = evt.Timestamp,
        }, _json);

        try
        {
            await _mqttPublisher.PublishJsonAsync(topic, payload, CancellationToken.None);
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "AlarmEvaluationService: MQTT publish failed for {Key} — evaluation continues", evt.AlarmKey);
        }
    }

    // =========================================================
    // MQTT INIT
    // =========================================================

    private void InitialiseMqttPublisher()
    {
        if (!_mqttTransportConfig.Enabled)
        {
            _logger.LogInformation("AlarmEvaluationService: MQTT disabled — alarm events written to DB only");
            return;
        }

        var mqttConfig = new MqttTransportConfig
        {
            BrokerHost  = _mqttTransportConfig.BrokerHost,
            BrokerPort  = _mqttTransportConfig.BrokerPort,
            ClientId    = $"cereveate-{_alarmConfig.MqttClientIdSuffix}-{Environment.MachineName}",
            Username    = _mqttTransportConfig.Username,
            Password    = _mqttTransportConfig.Password,
            TopicPrefix = string.Empty,
        };
        _mqttPublisher = new MqttPublisher(mqttConfig,
            _logger as ILogger<MqttPublisher> ??
            Microsoft.Extensions.Logging.Abstractions.NullLogger<MqttPublisher>.Instance);

        _logger.LogInformation("AlarmEvaluationService: MQTT publisher ready (broker={Host}:{Port})",
            _mqttTransportConfig.BrokerHost, _mqttTransportConfig.BrokerPort);
    }

    // =========================================================
    // TEST RAISE — callable from AlarmDiagnosticsController
    // =========================================================

    /// <summary>
    /// Forces a raise for a tag+value for diagnostic purposes.
    /// Returns null on success, error message on failure.
    /// </summary>
    public async Task<string?> TestRaiseAlarmAsync(string tagId, double value, CancellationToken ct = default)
    {
        var setpoint = _setpointCache.GetSetpoint(tagId);
        if (setpoint == null)
            return $"Tag '{tagId}' not found in setpoint cache ({_setpointCache.Count} tags loaded)";

        // Determine highest applicable level
        AlarmLevel? level = null;
        foreach (var l in _allLevels)
        {
            if (IsInAlarmZone(value, l, setpoint)) { level = l; break; }
        }

        if (level == null)
            return $"Value {value} is within normal range for tag '{tagId}' (H={setpoint.HLimit}, L={setpoint.LLimit})";

        var alarmKey = AlarmRuntimeState.BuildKey(tagId, level.Value);
        _stateManager.RemoveState(alarmKey);  // Allow re-raise for test

        var raised = await _stateManager.RaiseAsync(
            tagId, level.Value, value,
            GetSetpointForLevel(level.Value, setpoint),
            setpoint.AlarmPriority,
            DateTimeOffset.UtcNow, ct);

        return raised ? null : $"RaiseAsync returned false for tag '{tagId}' — check logs (circuit breaker or DB error)";
    }

    // =========================================================
    // DIAGNOSTICS — callable from AlarmDiagnosticsController
    // =========================================================

    public AlarmEvalDiagnostics GetDiagnostics()
    {
        var alarmTagIds = _setpointCache.GetAllAlarmTagIds();
        var poolEntries = _tagPool.GetTagValues(alarmTagIds);
        var (raised, acked, rtn, cleared) = _stateManager.GetCounters();

        var tagDetails = alarmTagIds.Select(id =>
        {
            var pool    = poolEntries.FirstOrDefault(e => string.Equals(e.TagId, id, StringComparison.OrdinalIgnoreCase));
            var sp      = _setpointCache.GetSetpoint(id);

            double? numVal = null;
            if (pool != null && double.TryParse(pool.Value, NumberStyles.Any, CultureInfo.InvariantCulture, out var d))
                numVal = d;

            string? determinedLevel = null;
            if (numVal.HasValue && sp != null)
            {
                foreach (var l in _allLevels)
                {
                    if (IsInAlarmZone(numVal.Value, l, sp)) { determinedLevel = l.ToString(); break; }
                }
            }

            // Highest active state across all levels for this tag
            AlarmRuntimeState? activeState = null;
            foreach (var l in _allLevels)
            {
                var s = _stateManager.GetState(AlarmRuntimeState.BuildKey(id, l));
                if (s?.State != AlarmState4.None && s?.State != null)
                { activeState = s; break; }
            }

            return new AlarmTagDiag
            {
                TagId            = id,
                InPool           = pool != null,
                PoolValue        = pool?.Value,
                PoolQuality      = pool?.Quality,
                IsStale          = pool?.IsStale,
                IsGoodQuality    = pool != null && IsGoodQuality(pool.Quality),
                NumericValue     = numVal,
                DeterminedLevel  = determinedLevel,
                HhLimit          = sp?.HhLimit,
                HLimit           = sp?.HLimit,
                LLimit           = sp?.LLimit,
                LlLimit          = sp?.LlLimit,
                AlarmDeadband    = sp?.AlarmDeadband,
                RuntimeActiveLevel = activeState?.State.ToString(),
                RuntimeEventId   = activeState?.CurrentEventId,
            };
        }).ToList();

        return new AlarmEvalDiagnostics
        {
            ServiceEnabled     = _alarmConfig.Enabled,
            LastDbError        = "",  // Moved to AlarmStateManager — logged there
            SetpointCacheCount = _setpointCache.Count,
            SetpointCacheInit  = _setpointCache.IsInitialized,
            EvaluationCycles   = Interlocked.Read(ref _evaluationCycles),
            AlarmsRaised       = raised,
            RtnTransitions     = rtn,
            ConsecutiveDbFail  = _stateManager.ConsecutiveDbFailures,
            CircuitOpen        = _stateManager.CircuitOpen,
            MaxDbFailures      = _alarmConfig.MaxConsecutiveDbFailures,
            TagPoolTotalCount  = _tagPool.GetCachedTagCount(),
            Tags               = tagDetails,
        };
    }

    // =========================================================
    // DISPOSE
    // =========================================================

    public override void Dispose()
    {
        _mqttPublisher?.Dispose();
        base.Dispose();
    }
}

// ─── Diagnostics DTOs ──────────────────────────────────────────────────────

public sealed class AlarmEvalDiagnostics
{
    public bool   ServiceEnabled     { get; init; }
    public string LastDbError        { get; init; } = "";
    public int    SetpointCacheCount { get; init; }
    public bool   SetpointCacheInit  { get; init; }
    public long   EvaluationCycles   { get; init; }
    public long   AlarmsRaised       { get; init; }
    public long   RtnTransitions     { get; init; }
    public int    ConsecutiveDbFail  { get; init; }
    public bool   CircuitOpen        { get; init; }
    public int    MaxDbFailures      { get; init; }
    public int    TagPoolTotalCount  { get; init; }
    public string LastDbErrorContext { get; init; } = "";
    public List<AlarmTagDiag> Tags   { get; init; } = [];
}

public sealed class AlarmTagDiag
{
    public string  TagId              { get; init; } = "";
    public bool    InPool             { get; init; }
    public string? PoolValue          { get; init; }
    public string? PoolQuality        { get; init; }
    public bool?   IsStale            { get; init; }
    public bool    IsGoodQuality      { get; init; }
    public double? NumericValue       { get; init; }
    public string? DeterminedLevel    { get; init; }
    public double? HhLimit            { get; init; }
    public double? HLimit             { get; init; }
    public double? LLimit             { get; init; }
    public double? LlLimit            { get; init; }
    public double? AlarmDeadband      { get; init; }
    public string? RuntimeActiveLevel { get; init; }
    public long?   RuntimeEventId     { get; init; }
}
