using Npgsql;
using OpcDaWebBrowser.Services.AlarmEvaluation.Config;
using OpcDaWebBrowser.Services.AlarmEvaluation.Models;
using OpcDaWebBrowser.Services.HistorianIngest.Config;
using PlcGateway.Transport;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Globalization;
using System.Text.Json;

namespace OpcDaWebBrowser.Services.AlarmEvaluation.Services;

/// <summary>
/// Production-grade interlock evaluation engine — mirrors AlarmEvaluationService exactly.
///
/// Responsibilities:
///   1. Read tag values from TagValuesPoolService every EvaluationIntervalMs
///   2. For each tag with interlock_type set in tag_master:
///        value > 0.5 (true/1) → SATISFIED
///        value ≤ 0.5 (false/0) → VIOLATED
///   3. On state transition: INSERT new row in historian_raw.interlock_state_tracking
///      (each transition = new row, with previous_state + state_duration_seconds)
///   4. On state transition: publish MQTT event to opc/interlocks/events
///
/// Design rules enforced (identical to AlarmEvaluationService):
///   ✔ No hardcoded values — all from AlarmEvaluationConfig
///   ✔ Stale OPC values are skipped — no false violations during connection loss
///   ✔ Bad quality values are skipped
///   ✔ DB writes only on state transitions (not every poll cycle)
///   ✔ Circuit breaker: DB failures stop writes temporarily, evaluation continues
///   ✔ Startup recovery: loads latest state per tag from DB so restart does not duplicate
///   ✔ Runtime state refresh: picks up operator BYPASS/DISABLE actions
///   ✔ MQTT is optional — service continues if broker is down
///   ✔ BYPASSED/DISABLED tags are skipped — operator decision is respected
/// </summary>
public sealed class InterlockEvaluationService : BackgroundService
{
    private readonly TagValuesPoolService _tagPool;
    private readonly HistorianConfig _dbConfig;
    private readonly AlarmEvaluationConfig _config;
    private readonly OpcMqttTransportConfig _mqttTransportConfig;
    private readonly ILogger<InterlockEvaluationService> _logger;

    // In-memory interlock state per tag — single writer (this service)
    private readonly ConcurrentDictionary<string, InterlockRuntimeState> _runtimeStates =
        new(StringComparer.OrdinalIgnoreCase);

    // Interlock config loaded from tag_master — atomic snapshot swap on refresh
    private volatile IReadOnlyDictionary<string, InterlockConfig> _configSnapshot =
        new Dictionary<string, InterlockConfig>(StringComparer.OrdinalIgnoreCase);

    // Dedicated MQTT publisher — separate client ID from alarm and OPC data publishers
    private MqttPublisher? _mqttPublisher;

    // DB circuit breaker
    private int _consecutiveDbFailures;
    private DateTimeOffset _circuitOpenedAt = DateTimeOffset.MinValue;

    // Diagnostics
    private long _violationsRecorded;
    private long _satisfiedTransitions;
    private long _evaluationCycles;

    // Timers
    private Timer? _configRefreshTimer;
    private Timer? _stateRefreshTimer;

    private static readonly JsonSerializerOptions _jsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase
    };

    // State constants — match the DB CHECK constraint
    private const string StateSatisfied = "SATISFIED";
    private const string StateViolated  = "VIOLATED";
    private const string StateBypassed  = "BYPASSED";
    private const string StateDisabled  = "DISABLED";

    public InterlockEvaluationService(
        TagValuesPoolService tagPool,
        HistorianConfig dbConfig,
        AlarmEvaluationConfig config,
        OpcMqttTransportConfig mqttTransportConfig,
        ILogger<InterlockEvaluationService> logger)
    {
        _tagPool             = tagPool             ?? throw new ArgumentNullException(nameof(tagPool));
        _dbConfig            = dbConfig            ?? throw new ArgumentNullException(nameof(dbConfig));
        _config              = config              ?? throw new ArgumentNullException(nameof(config));
        _mqttTransportConfig = mqttTransportConfig ?? throw new ArgumentNullException(nameof(mqttTransportConfig));
        _logger              = logger              ?? throw new ArgumentNullException(nameof(logger));
    }

    // =========================================================
    // BACKGROUND SERVICE ENTRY POINT
    // =========================================================

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!_config.InterlockEnabled)
        {
            _logger.LogWarning("InterlockEvaluationService is DISABLED (AlarmEvaluation:InterlockEnabled=false). No interlocks will be evaluated.");
            return;
        }

        _logger.LogInformation("InterlockEvaluationService starting (interval={Interval}ms)", _config.EvaluationIntervalMs);

        // Step 1: Load interlock tag configs from DB
        await LoadInterlockConfigsAsync(stoppingToken);
        _logger.LogInformation("InterlockEvaluationService: interlock config loaded — {Count} tags", _configSnapshot.Count);

        if (_configSnapshot.Count == 0)
        {
            _logger.LogWarning("InterlockEvaluationService: no tags with interlock_type found in tag_master. " +
                               "Set interlock_type column on tags to enable evaluation.");
        }

        // Step 2: Startup recovery — load latest interlock state per tag from DB
        //         Without this, a service restart would re-INSERT for every tag on first cycle
        await LoadLatestStatesFromDbAsync(stoppingToken);
        _logger.LogInformation("InterlockEvaluationService: runtime state loaded — {Count} tags recovered", _runtimeStates.Count);

        // Step 3: Start config refresh timer (picks up new interlock tags added to tag_master)
        var configRefreshInterval = TimeSpan.FromSeconds(_config.SetpointCacheRefreshIntervalSeconds);
        _configRefreshTimer = new Timer(
            _ => _ = SafeRefreshConfigAsync(),
            null,
            configRefreshInterval,
            configRefreshInterval);

        // Step 4: Start state refresh timer (picks up operator BYPASS/DISABLE)
        var stateRefreshInterval = TimeSpan.FromSeconds(_config.RuntimeStateRefreshIntervalSeconds);
        _stateRefreshTimer = new Timer(
            _ => _ = SafeRefreshRuntimeStatesAsync(),
            null,
            stateRefreshInterval,
            stateRefreshInterval);

        // Step 5: Initialise MQTT publisher (optional)
        InitialiseMqttPublisher();

        // Step 6: Main evaluation loop
        _logger.LogInformation("InterlockEvaluationService: entering evaluation loop");
        while (!stoppingToken.IsCancellationRequested)
        {
            var sw = Stopwatch.StartNew();
            try
            {
                await EvaluateCycleAsync(stoppingToken);
                Interlocked.Increment(ref _evaluationCycles);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "InterlockEvaluationService: unhandled exception in evaluation cycle");
            }

            var elapsed = (int)sw.ElapsedMilliseconds;
            var delay   = Math.Max(0, _config.EvaluationIntervalMs - elapsed);
            if (delay > 0)
                await Task.Delay(delay, stoppingToken).ConfigureAwait(false);
        }

        _logger.LogInformation("InterlockEvaluationService stopped. Violations={V}, Satisfied={S}, Cycles={C}",
            _violationsRecorded, _satisfiedTransitions, _evaluationCycles);
    }

    // =========================================================
    // EVALUATION CYCLE
    // =========================================================

    private async Task EvaluateCycleAsync(CancellationToken ct)
    {
        var interlockTagIds = _configSnapshot.Keys.ToList();
        if (interlockTagIds.Count == 0)
            return;

        var tagValues = _tagPool.GetTagValues(interlockTagIds);
        if (tagValues.Count == 0)
            return;

        foreach (var entry in tagValues)
        {
            if (ct.IsCancellationRequested) break;

            // Skip stale — OPC connection lost, do not record false violations
            if (entry.IsStale)
                continue;

            // Skip bad quality — uncertain values must not drive interlock state
            if (!IsGoodQuality(entry.Quality))
                continue;

            var interlockCfg = _configSnapshot.TryGetValue(entry.TagId, out var cfg) ? cfg : null;
            if (interlockCfg == null)
                continue;

            // Check in-memory state — skip BYPASSED/DISABLED (operator decision, not our call)
            _runtimeStates.TryGetValue(entry.TagId, out var currentState);
            if (currentState?.CurrentState is StateBypassed or StateDisabled)
                continue;

            // Determine new interlock state from value
            // boolean: value > 0.5 = true = SATISFIED (permissive met)
            //          value ≤ 0.5 = false = VIOLATED (permissive not met)
            // numeric: same threshold — matches HMI Python logic
            if (!double.TryParse(entry.Value, NumberStyles.Any, CultureInfo.InvariantCulture, out var numericValue))
                continue;

            var newState = numericValue > 0.5 ? StateSatisfied : StateViolated;

            await ProcessInterlockTransitionAsync(entry.TagId, newState, interlockCfg, entry.Timestamp, ct);
        }
    }

    // =========================================================
    // STATE MACHINE CORE
    // =========================================================

    private async Task ProcessInterlockTransitionAsync(
        string tagId, string newState, InterlockConfig cfg,
        DateTime timestamp, CancellationToken ct)
    {
        _runtimeStates.TryGetValue(tagId, out var currentState);
        var previousState = currentState?.CurrentState;

        // First evaluation cycle for this tag — always write to establish baseline
        bool isFirstEval = previousState == null;

        // No change since last write — nothing to do
        if (!isFirstEval && previousState == newState)
            return;

        // Calculate how long we were in the previous state
        int? durationSeconds = null;
        if (currentState?.StateEnteredAt != null)
        {
            durationSeconds = (int)(DateTimeOffset.UtcNow - currentState.StateEnteredAt.Value).TotalSeconds;
        }

        await WriteInterlockStateAsync(tagId, newState, previousState, durationSeconds, cfg, timestamp, ct);
    }

    // =========================================================
    // DB ACTION — INSERT STATE TRANSITION ROW
    // =========================================================

    private async Task WriteInterlockStateAsync(
        string tagId, string newState, string? previousState, int? durationSeconds,
        InterlockConfig cfg, DateTime timestamp, CancellationToken ct)
    {
        if (!IsCircuitClosed()) return;

        var eventTime = new DateTimeOffset(DateTime.SpecifyKind(timestamp, DateTimeKind.Utc), TimeSpan.Zero);

        long eventId;
        try
        {
            await using var conn = new NpgsqlConnection(_dbConfig.Database.ConnectionString);
            await conn.OpenAsync(ct);

            // Each state change = one new INSERT row (same pattern as HMI Python InterlockDAO)
            // previous_state + state_duration_seconds allow full audit trail reconstruction
            const string insertSql = """
                INSERT INTO historian_raw.interlock_state_tracking
                    (event_time, interlock_tag_id, interlock_type, interlock_state,
                     previous_state, state_duration_seconds, affected_equipment, metadata)
                VALUES
                    (@eventTime, @tagId, @interlockType, @interlockState,
                     @previousState, @durationSeconds, @equipment, @metadata::jsonb)
                RETURNING interlock_event_id
                """;

            var metadataJson = JsonSerializer.Serialize(new
            {
                evaluated_by = _config.SystemActorName,
                evaluation_timestamp = DateTimeOffset.UtcNow,
            }, _jsonOptions);

            await using var cmd = new NpgsqlCommand(insertSql, conn)
            {
                CommandTimeout = _dbConfig.Database.CommandTimeout
            };
            cmd.Parameters.AddWithValue("@eventTime",       eventTime);
            cmd.Parameters.AddWithValue("@tagId",           tagId);
            cmd.Parameters.AddWithValue("@interlockType",   cfg.InterlockType);
            cmd.Parameters.AddWithValue("@interlockState",  newState);
            cmd.Parameters.AddWithValue("@previousState",   (object?)previousState ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@durationSeconds", (object?)durationSeconds ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@equipment",       (object?)cfg.AffectedEquipment ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@metadata",        metadataJson);

            eventId = (long)(await cmd.ExecuteScalarAsync(ct)
                ?? throw new InvalidOperationException("INSERT did not return interlock_event_id"));

            ResetCircuitBreaker();
        }
        catch (Exception ex)
        {
            RecordDbFailure(ex, $"WriteInterlockStateAsync for tag {tagId}");
            return;
        }

        // Update in-memory state — only after successful DB write
        _runtimeStates[tagId] = new InterlockRuntimeState
        {
            TagId            = tagId,
            CurrentState     = newState,
            LastEventId      = eventId,
            StateEnteredAt   = DateTimeOffset.UtcNow,
            InterlockType    = cfg.InterlockType,
            AffectedEquipment = cfg.AffectedEquipment,
        };

        // Counters
        if (newState == StateViolated)
            Interlocked.Increment(ref _violationsRecorded);
        else if (newState == StateSatisfied)
            Interlocked.Increment(ref _satisfiedTransitions);

        var logLevel = newState == StateViolated ? LogLevel.Warning : LogLevel.Information;
        _logger.Log(logLevel,
            "INTERLOCK {State} [{Type}] tag={Tag} prev={Prev} event_id={Id}",
            newState, cfg.InterlockType, tagId, previousState ?? "NONE", eventId);

        // Publish MQTT — fire-and-forget, does not block evaluation loop
        _ = PublishInterlockEventAsync(tagId, newState, previousState, cfg, eventId, eventTime, ct);
    }

    // =========================================================
    // STARTUP RECOVERY — load latest state per tag from DB
    // =========================================================

    /// <summary>
    /// Loads the most recent interlock state row per tag from DB.
    /// Prevents re-inserting a VIOLATED→SATISFIED transition on every service restart.
    /// </summary>
    private async Task LoadLatestStatesFromDbAsync(CancellationToken ct)
    {
        if (_configSnapshot.Count == 0) return;

        try
        {
            await using var conn = new NpgsqlConnection(_dbConfig.Database.ConnectionString);
            await conn.OpenAsync(ct);

            // DISTINCT ON keeps only the most recent row per tag (ordered by event_time DESC)
            const string sql = """
                SELECT DISTINCT ON (interlock_tag_id)
                    interlock_event_id,
                    interlock_tag_id,
                    interlock_state,
                    event_time
                FROM historian_raw.interlock_state_tracking
                WHERE interlock_tag_id = ANY(@tagIds)
                ORDER BY interlock_tag_id, event_time DESC
                """;

            await using var cmd = new NpgsqlCommand(sql, conn)
            {
                CommandTimeout = _dbConfig.Database.CommandTimeout
            };
            cmd.Parameters.AddWithValue("@tagIds", _configSnapshot.Keys.ToArray());

            await using var rdr = await cmd.ExecuteReaderAsync(ct);
            var loaded = 0;

            while (await rdr.ReadAsync(ct))
            {
                var tagId       = rdr.GetString(1);
                var state       = rdr.GetString(2);
                var eventTime   = rdr.GetFieldValue<DateTimeOffset>(3);
                var eventId     = rdr.GetInt64(0);

                _configSnapshot.TryGetValue(tagId, out var cfg);

                _runtimeStates[tagId] = new InterlockRuntimeState
                {
                    TagId            = tagId,
                    CurrentState     = state,
                    LastEventId      = eventId,
                    StateEnteredAt   = eventTime,
                    InterlockType    = cfg?.InterlockType ?? string.Empty,
                    AffectedEquipment = cfg?.AffectedEquipment,
                };
                loaded++;
            }

            _logger.LogInformation("Startup recovery: loaded {Count} interlock states from DB", loaded);
        }
        catch (Exception ex)
        {
            // Non-fatal — service continues, may re-insert baseline on first cycle
            _logger.LogError(ex, "InterlockEvaluationService: startup state recovery failed — first cycle will re-establish baseline");
        }
    }

    // =========================================================
    // CONFIG REFRESH — picks up new interlock tags added to tag_master
    // =========================================================

    private async Task SafeRefreshConfigAsync()
    {
        try
        {
            await LoadInterlockConfigsAsync(CancellationToken.None);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "InterlockEvaluationService: config refresh failed — retaining previous config ({Count} tags)", _configSnapshot.Count);
        }
    }

    private async Task LoadInterlockConfigsAsync(CancellationToken ct)
    {
        await using var conn = new NpgsqlConnection(_dbConfig.Database.ConnectionString);
        await conn.OpenAsync(ct);

        // Load all tags with an interlock_type set — regardless of alarm_enabled flag
        // Columns: tag_id, interlock_type, equipment (for affected_equipment field)
        const string sql = """
            SELECT
                tag_id,
                interlock_type,
                COALESCE(equipment, tag_name, tag_id) AS affected_equipment
            FROM historian_meta.tag_master
            WHERE interlock_type IS NOT NULL
              AND interlock_type <> ''
              AND tag_id IS NOT NULL
            ORDER BY tag_id
            """;

        await using var cmd = new NpgsqlCommand(sql, conn)
        {
            CommandTimeout = _dbConfig.Database.CommandTimeout
        };
        await using var rdr = await cmd.ExecuteReaderAsync(ct);

        var fresh = new Dictionary<string, InterlockConfig>(StringComparer.OrdinalIgnoreCase);
        while (await rdr.ReadAsync(ct))
        {
            var tagId = rdr.GetString(0);
            fresh[tagId] = new InterlockConfig
            {
                TagId             = tagId,
                InterlockType     = rdr.GetString(1),
                AffectedEquipment = rdr.IsDBNull(2) ? null : rdr.GetString(2),
            };
        }

        // Atomic swap — same pattern as AlarmSetpointCacheService
        _configSnapshot = fresh;

        _logger.LogInformation("InterlockEvaluationService: config refreshed — {Count} interlock tags", fresh.Count);
    }

    // =========================================================
    // RUNTIME STATE REFRESH — picks up operator BYPASS/DISABLE
    // =========================================================

    private async Task SafeRefreshRuntimeStatesAsync()
    {
        try
        {
            await RefreshRuntimeStatesFromDbAsync(CancellationToken.None);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "InterlockEvaluationService: runtime state refresh failed");
        }
    }

    /// <summary>
    /// Reconciles in-memory states with DB latest rows.
    /// If operator BYPASSED or DISABLED a tag, this picks it up so evaluation skips it.
    /// </summary>
    private async Task RefreshRuntimeStatesFromDbAsync(CancellationToken ct)
    {
        var trackedIds = _runtimeStates.Keys.ToList();
        if (trackedIds.Count == 0) return;

        try
        {
            await using var conn = new NpgsqlConnection(_dbConfig.Database.ConnectionString);
            await conn.OpenAsync(ct);

            const string sql = """
                SELECT DISTINCT ON (interlock_tag_id)
                    interlock_tag_id,
                    interlock_state,
                    event_time,
                    interlock_event_id
                FROM historian_raw.interlock_state_tracking
                WHERE interlock_tag_id = ANY(@tagIds)
                ORDER BY interlock_tag_id, event_time DESC
                """;

            await using var cmd = new NpgsqlCommand(sql, conn)
            {
                CommandTimeout = _dbConfig.Database.CommandTimeout
            };
            cmd.Parameters.AddWithValue("@tagIds", trackedIds.ToArray());

            await using var rdr = await cmd.ExecuteReaderAsync(ct);
            while (await rdr.ReadAsync(ct))
            {
                var tagId    = rdr.GetString(0);
                var dbState  = rdr.GetString(1);
                var dbTime   = rdr.GetFieldValue<DateTimeOffset>(2);
                var dbId     = rdr.GetInt64(3);

                _runtimeStates.TryGetValue(tagId, out var mem);
                if (mem == null) continue;

                // Sync only if DB has a newer/different state than memory
                // (e.g. operator wrote BYPASSED via HMI while C# had VIOLATED)
                if (dbState != mem.CurrentState)
                {
                    _runtimeStates[tagId] = new InterlockRuntimeState
                    {
                        TagId             = tagId,
                        CurrentState      = dbState,
                        LastEventId       = dbId,
                        StateEnteredAt    = dbTime,
                        InterlockType     = mem.InterlockType,
                        AffectedEquipment = mem.AffectedEquipment,
                    };

                    if (dbState is StateBypassed or StateDisabled)
                        _logger.LogInformation(
                            "Runtime refresh: tag={Tag} state={State} (operator action) — evaluation suspended for this tag",
                            tagId, dbState);
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "InterlockEvaluationService.RefreshRuntimeStatesFromDbAsync failed");
        }
    }

    // =========================================================
    // MQTT PUBLISH (fire-and-forget, never blocks evaluation loop)
    // =========================================================

    private async Task PublishInterlockEventAsync(
        string tagId, string newState, string? previousState,
        InterlockConfig cfg, long eventId, DateTimeOffset eventTime, CancellationToken ct)
    {
        if (_mqttPublisher == null) return;

        var payload = JsonSerializer.Serialize(new
        {
            event_id          = eventId,
            tag_id            = tagId,
            interlock_type    = cfg.InterlockType,
            interlock_state   = newState,
            previous_state    = previousState,
            affected_equipment = cfg.AffectedEquipment,
            event_time        = eventTime,
            timestamp         = DateTimeOffset.UtcNow,
        }, _jsonOptions);

        try
        {
            await _mqttPublisher.PublishJsonAsync(_config.MqttInterlockTopic, payload, ct);
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "Interlock MQTT publish failed for tag {Tag} — evaluation continues", tagId);
        }
    }

    // =========================================================
    // CIRCUIT BREAKER — identical pattern to AlarmEvaluationService
    // =========================================================

    private bool IsCircuitClosed()
    {
        if (_consecutiveDbFailures < _config.MaxConsecutiveDbFailures)
            return true;

        var timeout = TimeSpan.FromMinutes(_config.DbCircuitBreakerTimeoutMinutes);
        if (DateTimeOffset.UtcNow - _circuitOpenedAt > timeout)
        {
            _logger.LogWarning("InterlockEvaluationService DB circuit breaker: timeout elapsed — attempting reset");
            _consecutiveDbFailures = 0;
            return true;
        }

        return false;
    }

    private void RecordDbFailure(Exception ex, string context)
    {
        _consecutiveDbFailures++;
        if (_consecutiveDbFailures == _config.MaxConsecutiveDbFailures)
        {
            _circuitOpenedAt = DateTimeOffset.UtcNow;
            _logger.LogError(ex,
                "InterlockEvaluationService DB circuit breaker TRIPPED after {N} failures in {Context}. Writes suspended for {Min} minutes.",
                _consecutiveDbFailures, context, _config.DbCircuitBreakerTimeoutMinutes);
        }
        else
        {
            _logger.LogError(ex, "InterlockEvaluationService DB write failed ({N}/{Max}) in {Context}",
                _consecutiveDbFailures, _config.MaxConsecutiveDbFailures, context);
        }
    }

    private void ResetCircuitBreaker()
    {
        if (_consecutiveDbFailures > 0)
        {
            _logger.LogInformation("InterlockEvaluationService DB circuit breaker reset after successful write");
            _consecutiveDbFailures = 0;
        }
    }

    // =========================================================
    // MQTT INITIALISATION
    // =========================================================

    private void InitialiseMqttPublisher()
    {
        if (!_mqttTransportConfig.Enabled)
        {
            _logger.LogInformation("InterlockEvaluationService: MQTT disabled — interlock events will only be written to DB");
            return;
        }

        var mqttConfig = new MqttTransportConfig
        {
            BrokerHost  = _mqttTransportConfig.BrokerHost,
            BrokerPort  = _mqttTransportConfig.BrokerPort,
            ClientId    = $"cereveate-{_config.MqttInterlockClientIdSuffix}-{Environment.MachineName}",
            Username    = _mqttTransportConfig.Username,
            Password    = _mqttTransportConfig.Password,
            TopicPrefix = string.Empty,  // Interlock topics are absolute — no prefix
        };

        _mqttPublisher = new MqttPublisher(mqttConfig,
            _logger as ILogger<MqttPublisher> ?? Microsoft.Extensions.Logging.Abstractions.NullLogger<MqttPublisher>.Instance);

        _logger.LogInformation(
            "InterlockEvaluationService: MQTT publisher initialised (broker={Host}:{Port}, topic={Topic})",
            _mqttTransportConfig.BrokerHost, _mqttTransportConfig.BrokerPort,
            _config.MqttInterlockTopic);
    }

    // =========================================================
    // HELPERS
    // =========================================================

    private static bool IsGoodQuality(string quality) =>
        quality is "Good" or "G" or "GOOD";

    // =========================================================
    // DISPOSE
    // =========================================================

    public override void Dispose()
    {
        _configRefreshTimer?.Dispose();
        _stateRefreshTimer?.Dispose();
        _mqttPublisher?.Dispose();
        base.Dispose();
    }
}
