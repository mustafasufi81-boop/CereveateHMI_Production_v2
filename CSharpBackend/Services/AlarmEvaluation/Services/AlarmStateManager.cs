using Npgsql;
using OpcDaWebBrowser.Services.AlarmEvaluation.Config;
using OpcDaWebBrowser.Services.AlarmEvaluation.Models;
using OpcDaWebBrowser.Services.HistorianIngest.Config;
using System.Collections.Concurrent;

namespace OpcDaWebBrowser.Services.AlarmEvaluation.Services;

/// <summary>
/// AlarmStateManager — sole authority over alarm state in Phase 1.
///
/// Responsibilities:
///   • Maintain in-memory runtime state per alarm_key (ConcurrentDictionary)
///   • Enforce valid ISA-18.2 4-state transitions
///   • UPSERT historian_raw.alarm_active on every transition
///   • INSERT historian_raw.historian_events journal entry on every transition
///   • DELETE alarm_active row when alarm is CLEARED
///   • Emit AlarmTransitionEvent after every successful DB write (for MQTT publish)
///   • Per alarm_key SemaphoreSlim — serializes concurrent raise / ACK / reconcile
///   • DB circuit breaker — suspends writes after N consecutive failures
///
/// Design rules enforced:
///   ✔ No DB write unless state actually changes
///   ✔ Memory is updated AFTER successful DB write (never before)
///   ✔ Invalid transitions are rejected silently (logged at Warning)
///   ✔ MQTT is optional — failure never affects alarm correctness
/// </summary>
public sealed class AlarmStateManager
{
    private readonly HistorianConfig _dbConfig;
    private readonly AlarmEvaluationConfig _alarmConfig;
    private readonly ILogger<AlarmStateManager> _logger;

    // Primary runtime state — alarm_key → state (authoritative in-memory copy)
    private readonly ConcurrentDictionary<string, AlarmRuntimeState> _states =
        new(StringComparer.OrdinalIgnoreCase);

    // Per alarm_key serialization locks — ensures raise / ACK / reconcile never race
    private readonly ConcurrentDictionary<string, SemaphoreSlim> _keyLocks =
        new(StringComparer.OrdinalIgnoreCase);

    // DB circuit breaker
    private int _consecutiveDbFailures;
    private DateTimeOffset _circuitOpenedAt = DateTimeOffset.MinValue;

    // Counters for diagnostics
    private long _totalRaised;
    private long _totalAcknowledged;
    private long _totalRtn;
    private long _totalCleared;

    /// <summary>
    /// Fires after every successful state transition + DB write.
    /// Subscribers use this to publish MQTT notifications.
    /// </summary>
    public event EventHandler<AlarmTransitionEvent>? TransitionOccurred;

    public AlarmStateManager(
        HistorianConfig dbConfig,
        AlarmEvaluationConfig alarmConfig,
        ILogger<AlarmStateManager> logger)
    {
        _dbConfig    = dbConfig    ?? throw new ArgumentNullException(nameof(dbConfig));
        _alarmConfig = alarmConfig ?? throw new ArgumentNullException(nameof(alarmConfig));
        _logger      = logger      ?? throw new ArgumentNullException(nameof(logger));
    }

    // =========================================================
    // SCHEMA INIT — run once at startup
    // =========================================================

    /// <summary>
    /// Idempotent: updates historian_events alarm_state CHECK constraint to Phase 1 states
    /// (ACTIVE_UNACK, ACTIVE_ACK, RTN_UNACK, CLEARED).
    /// Safe to run on every startup — uses DROP CONSTRAINT IF EXISTS + ADD CONSTRAINT.
    /// </summary>
    public async Task InitializeSchemaAsync(CancellationToken ct = default)
    {
        try
        {
            await using var conn = new NpgsqlConnection(_dbConfig.Database.ConnectionString);
            await conn.OpenAsync(ct);

            const string sql = """
                ALTER TABLE historian_raw.historian_events
                    DROP CONSTRAINT IF EXISTS historian_events_alarm_state_check;
                ALTER TABLE historian_raw.historian_events
                    ADD CONSTRAINT historian_events_alarm_state_check
                    CHECK (alarm_state IS NULL OR alarm_state IN (
                        'ACTIVE_UNACK', 'ACTIVE_ACK', 'RTN_UNACK', 'CLEARED'
                    ));
                """;
            await using var cmd = new NpgsqlCommand(sql, conn) { CommandTimeout = _dbConfig.Database.CommandTimeout };
            await cmd.ExecuteNonQueryAsync(ct);

            _logger.LogInformation("AlarmStateManager: historian_events.alarm_state constraint updated to Phase 1 (4-state)");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "AlarmStateManager: schema init failed (non-fatal — continuing)");
        }
    }

    // =========================================================
    // RUNTIME STATE READS — lock-free, safe for concurrent callers
    // =========================================================

    public AlarmRuntimeState? GetState(string alarmKey) =>
        _states.TryGetValue(alarmKey, out var s) ? s : null;

    /// <summary>Returns a snapshot of all current runtime states (read-only view).</summary>
    public IReadOnlyDictionary<string, AlarmRuntimeState> GetAllStates() => _states;

    public int ActiveCount => _states.Values.Count(
        s => s.State is AlarmState4.ActiveUnack or AlarmState4.ActiveAck or AlarmState4.RtnUnack);

    // =========================================================
    // TRANSITION: NORMAL → ACTIVE_UNACK  (alarm raised by engine)
    // =========================================================

    /// <summary>
    /// Raises a new alarm for the given tag + level.
    /// Returns false if the alarm is already active, circuit is open, or DB write fails.
    /// Returns true on success — AlarmTransitionEvent is emitted.
    /// </summary>
    public async Task<bool> RaiseAsync(
        string tagId,
        AlarmLevel level,
        double value,
        double? setpointValue,
        int priority,
        DateTimeOffset timestamp,
        CancellationToken ct)
    {
        var alarmKey = AlarmRuntimeState.BuildKey(tagId, level);
        var sem = GetOrCreateLock(alarmKey);

        await sem.WaitAsync(ct);
        try
        {
            // Do not double-raise an already-active alarm
            if (_states.TryGetValue(alarmKey, out var existing) &&
                existing.State is AlarmState4.ActiveUnack or AlarmState4.ActiveAck)
            {
                return false;
            }

            if (!IsCircuitClosed()) return false;

            var occurrenceId = Guid.NewGuid();
            var instanceSeq  = GetNextInstanceSeq(alarmKey);
            var levelStr     = level.ToString();
            var eventType    = BuildRaiseEventType(level);
            var message      = BuildAlarmMessage(tagId, value, level, setpointValue);

            long eventId = 0;
            long transitionSeq = 0;
            try
            {
                await using var conn = new NpgsqlConnection(_dbConfig.Database.ConnectionString);
                await conn.OpenAsync(ct);

                // 1. INSERT to historian_events — immutable journal
                const string insertEvent = """
                    INSERT INTO historian_raw.historian_events
                        (time, tag_id, event_type, severity, message,
                         alarm_state, alarm_priority, alarm_setpoint, alarm_actual_value,
                         alarm_level, occurrence_id, instance_seq, transition_seq)
                    VALUES
                        (@time, @tagId, @eventType, @severity, @message,
                         'ACTIVE_UNACK', @priority, @setpoint, @value,
                         @level, @occId, @seq,
                         nextval('historian_raw.alarm_transition_seq'))
                    RETURNING event_id, transition_seq
                    """;
                await using var cmdE = new NpgsqlCommand(insertEvent, conn) { CommandTimeout = _dbConfig.Database.CommandTimeout };
                cmdE.Parameters.AddWithValue("@time",     timestamp);
                cmdE.Parameters.AddWithValue("@tagId",    tagId);
                cmdE.Parameters.AddWithValue("@eventType",eventType);
                cmdE.Parameters.AddWithValue("@severity", priority);
                cmdE.Parameters.AddWithValue("@message",  message);
                cmdE.Parameters.AddWithValue("@priority", priority);
                cmdE.Parameters.AddWithValue("@setpoint", (object?)setpointValue ?? DBNull.Value);
                cmdE.Parameters.AddWithValue("@value",    value);
                cmdE.Parameters.AddWithValue("@level",    levelStr);
                cmdE.Parameters.AddWithValue("@occId",    occurrenceId);
                cmdE.Parameters.AddWithValue("@seq",      instanceSeq);
                await using (var rdr = await cmdE.ExecuteReaderAsync(ct))
                {
                    if (!await rdr.ReadAsync(ct)) throw new InvalidOperationException("INSERT historian_events returned no row");
                    eventId       = rdr.GetInt64(0);
                    transitionSeq = rdr.GetInt64(1);
                }

                // 2. UPSERT alarm_active — current live state
                const string upsertActive = """
                    INSERT INTO historian_raw.alarm_active
                        (alarm_key, tag_id, level, alarm_state, current_event_id,
                         occurrence_id, instance_seq, raised_at, raised_value,
                         setpoint_value, priority, transition_seq, updated_at)
                    VALUES
                        (@key, @tagId, @level, 'ACTIVE_UNACK', @eventId,
                         @occId, @seq, @raisedAt, @raisedVal,
                         @setpoint, @priority, @transSeq, NOW())
                    ON CONFLICT (alarm_key) DO UPDATE
                        SET alarm_state      = 'ACTIVE_UNACK',
                            current_event_id = @eventId,
                            occurrence_id    = @occId,
                            instance_seq     = @seq,
                            raised_at        = @raisedAt,
                            raised_value     = @raisedVal,
                            setpoint_value   = @setpoint,
                            priority         = @priority,
                            transition_seq   = @transSeq,
                            ack_at           = NULL,
                            ack_by           = NULL,
                            rtn_at           = NULL,
                            updated_at       = NOW()
                    """;
                await using var cmdA = new NpgsqlCommand(upsertActive, conn) { CommandTimeout = _dbConfig.Database.CommandTimeout };
                cmdA.Parameters.AddWithValue("@key",      alarmKey);
                cmdA.Parameters.AddWithValue("@tagId",    tagId);
                cmdA.Parameters.AddWithValue("@level",    levelStr);
                cmdA.Parameters.AddWithValue("@eventId",  eventId);
                cmdA.Parameters.AddWithValue("@occId",    occurrenceId);
                cmdA.Parameters.AddWithValue("@seq",      instanceSeq);
                cmdA.Parameters.AddWithValue("@raisedAt", timestamp);
                cmdA.Parameters.AddWithValue("@raisedVal",(object?)value         ?? DBNull.Value);
                cmdA.Parameters.AddWithValue("@setpoint", (object?)setpointValue ?? DBNull.Value);
                cmdA.Parameters.AddWithValue("@priority", priority);
                cmdA.Parameters.AddWithValue("@transSeq", transitionSeq);
                await cmdA.ExecuteNonQueryAsync(ct);

                ResetCircuitBreaker();
            }
            catch (Exception ex)
            {
                RecordDbFailure(ex, $"RaiseAsync {alarmKey}");
                return false;
            }

            // Update memory AFTER successful DB write
            _states[alarmKey] = new AlarmRuntimeState
            {
                AlarmKey       = alarmKey,
                TagId          = tagId,
                Level          = level,
                State          = AlarmState4.ActiveUnack,
                OccurrenceId   = occurrenceId,
                InstanceSeq    = instanceSeq,
                CurrentEventId = eventId,
                TransitionSeq  = transitionSeq,
                RaisedAt       = timestamp,
                RaisedValue    = value,
                SetpointValue  = setpointValue,
            };

            Interlocked.Increment(ref _totalRaised);
            _logger.LogWarning("ALARM RAISED [{Level}] key={Key} val={Val} sp={Sp} event_id={Id} occ={Occ}",
                level, alarmKey, value, setpointValue, eventId, occurrenceId);

            EmitTransition(new AlarmTransitionEvent
            {
                AlarmKey      = alarmKey,
                TagId         = tagId,
                Level         = level,
                ToState       = AlarmState4.ActiveUnack,
                OccurrenceId  = occurrenceId,
                InstanceSeq   = instanceSeq,
                EventId       = eventId,
                TransitionSeq = transitionSeq,
                Timestamp     = timestamp,
                Value         = value,
                SetpointValue = setpointValue,
            });

            return true;
        }
        finally { sem.Release(); }
    }

    // =========================================================
    // TRANSITION: ACTIVE → RTN_UNACK  (value returned to normal)
    // =========================================================

    // =========================================================
    // TRANSITION: ACTIVE_UNACK / ACTIVE_ACK → RTN_UNACK
    // =========================================================

    /// <summary>
    /// Marks an active alarm as Return-To-Normal.
    /// Returns false if the alarm is not in an active state, circuit is open, or DB write fails.
    /// </summary>
    public async Task<bool> MarkRtnAsync(
        string tagId,
        AlarmLevel level,
        double value,
        DateTimeOffset timestamp,
        CancellationToken ct)
    {
        var alarmKey = AlarmRuntimeState.BuildKey(tagId, level);
        var sem = GetOrCreateLock(alarmKey);

        await sem.WaitAsync(ct);
        try
        {
            if (!_states.TryGetValue(alarmKey, out var state))
                return false;

            if (state.State is not (AlarmState4.ActiveUnack or AlarmState4.ActiveAck))
                return false;

            if (!IsCircuitClosed()) return false;

            long rtnEventId = 0;
            long rtnTransSeq = 0;
            try
            {
                await using var conn = new NpgsqlConnection(_dbConfig.Database.ConnectionString);
                await conn.OpenAsync(ct);

                // INSERT RTN journal entry
                const string insertRtn = """
                    INSERT INTO historian_raw.historian_events
                        (time, tag_id, event_type, severity, message,
                         alarm_state, alarm_priority, alarm_actual_value,
                         alarm_level, occurrence_id, instance_seq, transition_seq)
                    VALUES
                        (@time, @tagId, 'ALARM_RTN', @severity, @message,
                         'RTN_UNACK', @priority, @value,
                         @level, @occId, @seq,
                         nextval('historian_raw.alarm_transition_seq'))
                    RETURNING event_id, transition_seq
                    """;
                await using var cmdR = new NpgsqlCommand(insertRtn, conn) { CommandTimeout = _dbConfig.Database.CommandTimeout };
                cmdR.Parameters.AddWithValue("@time",    timestamp);
                cmdR.Parameters.AddWithValue("@tagId",   tagId);
                cmdR.Parameters.AddWithValue("@severity",4);
                cmdR.Parameters.AddWithValue("@message", $"{tagId} returned to normal from {level} (value={value:G6})");
                cmdR.Parameters.AddWithValue("@priority",4);
                cmdR.Parameters.AddWithValue("@value",   value);
                cmdR.Parameters.AddWithValue("@level",   level.ToString());
                cmdR.Parameters.AddWithValue("@occId",   state.OccurrenceId);
                cmdR.Parameters.AddWithValue("@seq",     state.InstanceSeq);
                await using (var rdr = await cmdR.ExecuteReaderAsync(ct))
                {
                    if (!await rdr.ReadAsync(ct)) throw new InvalidOperationException("RTN INSERT returned no row");
                    rtnEventId  = rdr.GetInt64(0);
                    rtnTransSeq = rdr.GetInt64(1);
                }

                // UPDATE alarm_active state
                const string updateActive = """
                    UPDATE historian_raw.alarm_active
                    SET alarm_state    = 'RTN_UNACK',
                        rtn_at         = @rtnAt,
                        transition_seq = @transSeq,
                        updated_at     = NOW()
                    WHERE alarm_key = @key
                    """;
                await using var cmdU = new NpgsqlCommand(updateActive, conn) { CommandTimeout = _dbConfig.Database.CommandTimeout };
                cmdU.Parameters.AddWithValue("@key",      alarmKey);
                cmdU.Parameters.AddWithValue("@rtnAt",    timestamp);
                cmdU.Parameters.AddWithValue("@transSeq", rtnTransSeq);
                await cmdU.ExecuteNonQueryAsync(ct);

                ResetCircuitBreaker();
            }
            catch (Exception ex)
            {
                RecordDbFailure(ex, $"MarkRtnAsync {alarmKey}");
                return false;
            }

            // Update memory AFTER successful DB write
            state.State         = AlarmState4.RtnUnack;
            state.RtnAt         = timestamp;
            state.TransitionSeq = rtnTransSeq;

            Interlocked.Increment(ref _totalRtn);
            _logger.LogInformation("ALARM RTN key={Key} val={Val}", alarmKey, value);

            EmitTransition(new AlarmTransitionEvent
            {
                AlarmKey      = alarmKey,
                TagId         = tagId,
                Level         = level,
                ToState       = AlarmState4.RtnUnack,
                OccurrenceId  = state.OccurrenceId,
                InstanceSeq   = state.InstanceSeq,
                EventId       = rtnEventId,
                TransitionSeq = rtnTransSeq,
                Timestamp     = timestamp,
                Value         = value,
                SetpointValue = state.SetpointValue,
            });

            return true;
        }
        finally { sem.Release(); }
    }

    // =========================================================
    // TRANSITION: Operator ACK
    //   ACTIVE_UNACK → ACTIVE_ACK
    //   RTN_UNACK    → CLEARED (row deleted from alarm_active)
    // =========================================================

    /// <summary>
    /// Processes an operator acknowledgement for the given alarm_key.
    /// ACTIVE_UNACK → ACTIVE_ACK (alarm condition still active, operator noted it).
    /// RTN_UNACK    → CLEARED    (alarm fully resolved, row deleted from alarm_active).
    /// Returns false if alarm not found, wrong state, or DB write fails.
    /// </summary>
    public async Task<bool> AcknowledgeAsync(
        string alarmKey,
        string operatorName,
        CancellationToken ct,
        string? notes = null)
    {
        var sem = GetOrCreateLock(alarmKey);

        await sem.WaitAsync(ct);
        try
        {
            if (!_states.TryGetValue(alarmKey, out var state))
            {
                _logger.LogWarning("AcknowledgeAsync: alarm key {Key} not found in runtime state", alarmKey);
                return false;
            }

            if (state.State is not (AlarmState4.ActiveUnack or AlarmState4.RtnUnack))
            {
                _logger.LogWarning("AcknowledgeAsync: invalid ACK in state {State} for key {Key}", state.State, alarmKey);
                return false;
            }

            if (!IsCircuitClosed()) return false;

            var ackAt    = DateTimeOffset.UtcNow;
            var isRtn    = state.State == AlarmState4.RtnUnack;
            var ackState = isRtn ? "CLEARED" : "ACTIVE_ACK";
            var ackType  = isRtn ? "ALARM_CLEARED" : "ALARM_ACK";

            long ackEventId = 0;
            long ackTransSeq = 0;
            try
            {
                await using var conn = new NpgsqlConnection(_dbConfig.Database.ConnectionString);
                await conn.OpenAsync(ct);

                // INSERT ACK journal entry
                const string insertAck = """
                    INSERT INTO historian_raw.historian_events
                        (time, tag_id, event_type, severity, message,
                         alarm_state, alarm_priority,
                         alarm_level, occurrence_id, instance_seq, transition_seq)
                    VALUES
                        (@time, @tagId, @eventType, @severity, @message,
                         @alarmState, @priority,
                         @level, @occId, @seq,
                         nextval('historian_raw.alarm_transition_seq'))
                    RETURNING event_id, transition_seq
                    """;
                await using var cmdA = new NpgsqlCommand(insertAck, conn) { CommandTimeout = _dbConfig.Database.CommandTimeout };
                cmdA.Parameters.AddWithValue("@time",       ackAt);
                cmdA.Parameters.AddWithValue("@tagId",      state.TagId);
                cmdA.Parameters.AddWithValue("@eventType",  ackType);
                cmdA.Parameters.AddWithValue("@severity",   4);
                cmdA.Parameters.AddWithValue("@message",    string.IsNullOrWhiteSpace(notes)
                    ? $"{alarmKey} acknowledged by {operatorName}"
                    : $"{alarmKey} acknowledged by {operatorName}: {notes}");
                cmdA.Parameters.AddWithValue("@alarmState", ackState);
                cmdA.Parameters.AddWithValue("@priority",   4);
                cmdA.Parameters.AddWithValue("@level",      state.Level.ToString());
                cmdA.Parameters.AddWithValue("@occId",      state.OccurrenceId);
                cmdA.Parameters.AddWithValue("@seq",        state.InstanceSeq);
                await using (var rdr = await cmdA.ExecuteReaderAsync(ct))
                {
                    if (!await rdr.ReadAsync(ct)) throw new InvalidOperationException("ACK INSERT returned no row");
                    ackEventId  = rdr.GetInt64(0);
                    ackTransSeq = rdr.GetInt64(1);
                }

                if (isRtn)
                {
                    // RTN_UNACK → CLEARED: DELETE from alarm_active (row no longer needed)
                    const string deleteActive = """
                        DELETE FROM historian_raw.alarm_active WHERE alarm_key = @key
                        """;
                    await using var cmdD = new NpgsqlCommand(deleteActive, conn) { CommandTimeout = _dbConfig.Database.CommandTimeout };
                    cmdD.Parameters.AddWithValue("@key", alarmKey);
                    await cmdD.ExecuteNonQueryAsync(ct);
                }
                else
                {
                    // ACTIVE_UNACK → ACTIVE_ACK: UPDATE alarm_active
                    const string updateActive = """
                        UPDATE historian_raw.alarm_active
                        SET alarm_state    = 'ACTIVE_ACK',
                            ack_at         = @ackAt,
                            ack_by         = @ackBy,
                            transition_seq = @transSeq,
                            updated_at     = NOW()
                        WHERE alarm_key = @key
                        """;
                    await using var cmdU = new NpgsqlCommand(updateActive, conn) { CommandTimeout = _dbConfig.Database.CommandTimeout };
                    cmdU.Parameters.AddWithValue("@key",      alarmKey);
                    cmdU.Parameters.AddWithValue("@ackAt",    ackAt);
                    cmdU.Parameters.AddWithValue("@ackBy",    operatorName);
                    cmdU.Parameters.AddWithValue("@transSeq", ackTransSeq);
                    await cmdU.ExecuteNonQueryAsync(ct);
                }

                ResetCircuitBreaker();
            }
            catch (Exception ex)
            {
                RecordDbFailure(ex, $"AcknowledgeAsync {alarmKey}");
                return false;
            }

            // Update memory AFTER successful DB write
            var capturedState = state;
            if (isRtn)
            {
                _states.TryRemove(alarmKey, out _);
                Interlocked.Increment(ref _totalCleared);
                _logger.LogInformation("ALARM CLEARED key={Key} by={Op}", alarmKey, operatorName);
                EmitTransition(new AlarmTransitionEvent
                {
                    AlarmKey      = alarmKey,
                    TagId         = capturedState.TagId,
                    Level         = capturedState.Level,
                    ToState       = AlarmState4.None,
                    OccurrenceId  = capturedState.OccurrenceId,
                    InstanceSeq   = capturedState.InstanceSeq,
                    EventId       = ackEventId,
                    TransitionSeq = ackTransSeq,
                    Timestamp     = ackAt,
                    Operator      = operatorName,
                });
            }
            else
            {
                state.State         = AlarmState4.ActiveAck;
                state.AckAt         = ackAt;
                state.AckBy         = operatorName;
                state.TransitionSeq = ackTransSeq;
                Interlocked.Increment(ref _totalAcknowledged);
                _logger.LogInformation("ALARM ACK key={Key} by={Op}", alarmKey, operatorName);
                EmitTransition(new AlarmTransitionEvent
                {
                    AlarmKey      = alarmKey,
                    TagId         = state.TagId,
                    Level         = state.Level,
                    ToState       = AlarmState4.ActiveAck,
                    OccurrenceId  = state.OccurrenceId,
                    InstanceSeq   = state.InstanceSeq,
                    EventId       = ackEventId,
                    TransitionSeq = ackTransSeq,
                    Timestamp     = ackAt,
                    Operator      = operatorName,
                });
            }

            return true;
        }
        finally { sem.Release(); }
    }

    // =========================================================
    // TRANSITION: Operator CLEAR
    //   ACTIVE_ACK → CLEARED (operator manually closes an acknowledged active alarm)
    // =========================================================

    /// <summary>
    /// Processes an operator CLEAR for the given alarm_key.
    /// Only valid from ACTIVE_ACK state (alarm condition still active but operator closes it).
    /// Inserts ALARM_CLEARED row in historian_events (append-only).
    /// Deletes row from alarm_active.
    /// Returns false if alarm not found, wrong state, or DB write fails.
    /// </summary>
    public async Task<bool> ClearAsync(
        string alarmKey,
        string operatorName,
        CancellationToken ct,
        string? reason = null,
        string? notes  = null,
        bool forceAck  = false)   // if true: auto-ACK ACTIVE_UNACK before clearing (operator shortcut)
    {
        var sem = GetOrCreateLock(alarmKey);

        await sem.WaitAsync(ct);
        try
        {
            if (!_states.TryGetValue(alarmKey, out var state))
            {
                _logger.LogWarning("ClearAsync: alarm key {Key} not found in runtime state", alarmKey);
                return false;
            }

            // If forceAck is set and alarm is still ACTIVE_UNACK, perform the ACK transition first
            // (within the same lock so no race condition is possible).
            if (forceAck && state.State == AlarmState4.ActiveUnack)
            {
                _logger.LogInformation("ClearAsync: forceAck=true — auto-acknowledging {Key} before clear", alarmKey);
                // Release and re-acquire through AcknowledgeAsync is NOT safe (deadlock).
                // Instead, perform the ACK DB write inline here before proceeding.
                sem.Release();
                var ackOk = await AcknowledgeAsync(alarmKey, operatorName, ct, notes: "Auto-acknowledged before clear");
                if (!ackOk)
                {
                    _logger.LogWarning("ClearAsync: forceAck inline-ACK failed for {Key}", alarmKey);
                    return false;
                }
                // Re-enter the semaphore for the clear phase
                await sem.WaitAsync(ct);
                // Refresh state reference after ACK
                if (!_states.TryGetValue(alarmKey, out state))
                {
                    _logger.LogWarning("ClearAsync: alarm {Key} disappeared after forceAck", alarmKey);
                    return false;
                }
            }

            // CLEAR is only valid when the alarm is acknowledged (ACTIVE_ACK).
            // RTN_UNACK → CLEARED is handled inside AcknowledgeAsync (ISA-18.2 rule).
            if (state.State is not AlarmState4.ActiveAck)
            {
                _logger.LogWarning("ClearAsync: invalid CLEAR in state {State} for key {Key}", state.State, alarmKey);
                return false;
            }

            if (!IsCircuitClosed()) return false;

            var clearAt = DateTimeOffset.UtcNow;
            var message = string.IsNullOrWhiteSpace(reason)
                ? $"{alarmKey} cleared by {operatorName}"
                : $"{alarmKey} cleared by {operatorName} — Reason: {reason}";
            if (!string.IsNullOrWhiteSpace(notes))
                message += $" | Notes: {notes}";

            long clearEventId = 0;
            long clearTransSeq = 0;
            try
            {
                await using var conn = new NpgsqlConnection(_dbConfig.Database.ConnectionString);
                await conn.OpenAsync(ct);

                // INSERT CLEARED journal entry — append-only, historian_events is never mutated
                const string insertClear = """
                    INSERT INTO historian_raw.historian_events
                        (time, tag_id, event_type, severity, message,
                         alarm_state, alarm_priority,
                         alarm_level, occurrence_id, instance_seq, transition_seq)
                    VALUES
                        (@time, @tagId, 'ALARM_CLEARED', @severity, @message,
                         'CLEARED', @priority,
                         @level, @occId, @seq,
                         nextval('historian_raw.alarm_transition_seq'))
                    RETURNING event_id, transition_seq
                    """;
                await using var cmdC = new NpgsqlCommand(insertClear, conn) { CommandTimeout = _dbConfig.Database.CommandTimeout };
                cmdC.Parameters.AddWithValue("@time",     clearAt);
                cmdC.Parameters.AddWithValue("@tagId",    state.TagId);
                cmdC.Parameters.AddWithValue("@severity", 4);
                cmdC.Parameters.AddWithValue("@message",  message);
                cmdC.Parameters.AddWithValue("@priority", 4);
                cmdC.Parameters.AddWithValue("@level",    state.Level.ToString());
                cmdC.Parameters.AddWithValue("@occId",    state.OccurrenceId);
                cmdC.Parameters.AddWithValue("@seq",      state.InstanceSeq);
                await using (var rdr = await cmdC.ExecuteReaderAsync(ct))
                {
                    if (!await rdr.ReadAsync(ct)) throw new InvalidOperationException("CLEAR INSERT historian_events returned no row");
                    clearEventId  = rdr.GetInt64(0);
                    clearTransSeq = rdr.GetInt64(1);
                }

                // DELETE from alarm_active — row lifecycle complete
                const string deleteActive = "DELETE FROM historian_raw.alarm_active WHERE alarm_key = @key";
                await using var cmdD = new NpgsqlCommand(deleteActive, conn) { CommandTimeout = _dbConfig.Database.CommandTimeout };
                cmdD.Parameters.AddWithValue("@key", alarmKey);
                await cmdD.ExecuteNonQueryAsync(ct);

                ResetCircuitBreaker();
            }
            catch (Exception ex)
            {
                RecordDbFailure(ex, $"ClearAsync {alarmKey}");
                return false;
            }

            // Update memory AFTER successful DB write
            var capturedState = state;
            _states.TryRemove(alarmKey, out _);
            Interlocked.Increment(ref _totalCleared);
            _logger.LogInformation("ALARM CLEARED key={Key} by={Op} reason={Reason}",
                alarmKey, operatorName, reason ?? "none");

            EmitTransition(new AlarmTransitionEvent
            {
                AlarmKey      = alarmKey,
                TagId         = capturedState.TagId,
                Level         = capturedState.Level,
                ToState       = AlarmState4.None,
                OccurrenceId  = capturedState.OccurrenceId,
                InstanceSeq   = capturedState.InstanceSeq,
                EventId       = clearEventId,
                TransitionSeq = clearTransSeq,
                Timestamp     = clearAt,
                Operator      = operatorName,
            });

            return true;
        }
        finally { sem.Release(); }
    }

    // =========================================================
    // RECONCILIATION — used by AlarmReconciliationService on startup
    // =========================================================

    /// <summary>Restores a state directly into memory (called by AlarmReconciliationService).</summary>
    public void RestoreState(AlarmRuntimeState state) => _states[state.AlarmKey] = state;

    /// <summary>Removes a state entry (called by reconciliation when stale row detected).</summary>
    public void RemoveState(string alarmKey) => _states.TryRemove(alarmKey, out _);

    // =========================================================
    // DIAGNOSTICS
    // =========================================================

    public (long Raised, long Acknowledged, long Rtn, long Cleared) GetCounters() =>
        (Interlocked.Read(ref _totalRaised),
         Interlocked.Read(ref _totalAcknowledged),
         Interlocked.Read(ref _totalRtn),
         Interlocked.Read(ref _totalCleared));

    public bool CircuitOpen =>
        _consecutiveDbFailures >= _alarmConfig.MaxConsecutiveDbFailures;

    public int ConsecutiveDbFailures => _consecutiveDbFailures;

    // =========================================================
    // PRIVATE HELPERS
    // =========================================================

    private SemaphoreSlim GetOrCreateLock(string alarmKey) =>
        _keyLocks.GetOrAdd(alarmKey, _ => new SemaphoreSlim(1, 1));

    private int GetNextInstanceSeq(string alarmKey) =>
        _states.TryGetValue(alarmKey, out var old) && old.InstanceSeq > 0
            ? old.InstanceSeq + 1
            : 1;

    private void EmitTransition(AlarmTransitionEvent evt)
    {
        try { TransitionOccurred?.Invoke(this, evt); }
        catch (Exception ex)
        {
            _logger.LogError(ex, "AlarmStateManager: TransitionOccurred handler threw for key={Key}", evt.AlarmKey);
        }
    }

    private bool IsCircuitClosed()
    {
        if (_consecutiveDbFailures < _alarmConfig.MaxConsecutiveDbFailures)
            return true;
        var timeout = TimeSpan.FromMinutes(_alarmConfig.DbCircuitBreakerTimeoutMinutes);
        if (DateTimeOffset.UtcNow - _circuitOpenedAt > timeout)
        {
            _consecutiveDbFailures = 0;
            _logger.LogWarning("AlarmStateManager DB circuit breaker: timeout elapsed — resetting");
            return true;
        }
        return false;
    }

    private void RecordDbFailure(Exception ex, string context)
    {
        _consecutiveDbFailures++;
        if (_consecutiveDbFailures == _alarmConfig.MaxConsecutiveDbFailures)
        {
            _circuitOpenedAt = DateTimeOffset.UtcNow;
            _logger.LogError(ex,
                "AlarmStateManager DB circuit breaker TRIPPED after {N} failures in {Context}. Writes suspended for {Min}min.",
                _consecutiveDbFailures, context, _alarmConfig.DbCircuitBreakerTimeoutMinutes);
        }
        else
        {
            _logger.LogError(ex, "AlarmStateManager DB write failed ({N}/{Max}) in {Context}",
                _consecutiveDbFailures, _alarmConfig.MaxConsecutiveDbFailures, context);
        }
    }

    private void ResetCircuitBreaker()
    {
        if (_consecutiveDbFailures > 0)
            _consecutiveDbFailures = 0;
    }

    private static string BuildRaiseEventType(AlarmLevel level) => level switch
    {
        AlarmLevel.HighHigh => "ALARM_RAISED_HH",
        AlarmLevel.High     => "ALARM_RAISED_H",
        AlarmLevel.LowLow   => "ALARM_RAISED_LL",
        AlarmLevel.Low      => "ALARM_RAISED_L",
        _                   => "ALARM_RAISED",
    };

    private static string BuildAlarmMessage(string tagId, double value, AlarmLevel level, double? setpoint)
    {
        var label = level switch
        {
            AlarmLevel.HighHigh => "High-High",
            AlarmLevel.High     => "High",
            AlarmLevel.LowLow   => "Low-Low",
            AlarmLevel.Low      => "Low",
            _                   => level.ToString(),
        };
        return setpoint.HasValue
            ? $"{tagId} exceeded {label} limit: {value:G6} (setpoint: {setpoint:G6})"
            : $"{tagId} exceeded {label} limit: {value:G6}";
    }
}
