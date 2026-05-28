using Npgsql;
using OpcDaWebBrowser.Services.AlarmEvaluation.Models;
using OpcDaWebBrowser.Services.HistorianIngest.Config;
using PlcGateway.Services;
using System.Globalization;

namespace OpcDaWebBrowser.Services.AlarmEvaluation.Services;

/// <summary>
/// Startup live-value reconciliation — called ONCE after OPC connects and before the
/// evaluation loop starts.
///
/// Algorithm:
///   1. Load all non-CLEARED rows from historian_raw.alarm_active
///   2. For each row get the current live value from TagValuesPoolService
///   3. If value is STILL in the alarm zone → restore AlarmRuntimeState (alarm stays active)
///   4. If value returned to normal → UPDATE alarm_active to RTN_UNACK, do NOT restore as active
///   5. If no live value (OPC offline / stale) → conservative: keep alarm active
///   6. All RTN updates committed in ONE transaction
///
/// This completely eliminates stale ACTIVE row blocking without time-based cleanup.
/// MQTT is NOT published during reconciliation — one summary log at the end.
/// </summary>
public sealed class AlarmReconciliationService
{
    private readonly HistorianConfig _dbConfig;
    private readonly TagValuesPoolService _tagPool;
    private readonly PlcTagValuesPoolService _plcTagPool;
    private readonly AlarmSetpointCacheService _setpointCache;
    private readonly AlarmStateManager _stateManager;
    private readonly ILogger<AlarmReconciliationService> _logger;

    public AlarmReconciliationService(
        HistorianConfig dbConfig,
        TagValuesPoolService tagPool,
        PlcTagValuesPoolService plcTagPool,
        AlarmSetpointCacheService setpointCache,
        AlarmStateManager stateManager,
        ILogger<AlarmReconciliationService> logger)
    {
        _dbConfig      = dbConfig      ?? throw new ArgumentNullException(nameof(dbConfig));
        _tagPool       = tagPool       ?? throw new ArgumentNullException(nameof(tagPool));
        _plcTagPool    = plcTagPool    ?? throw new ArgumentNullException(nameof(plcTagPool));
        _setpointCache = setpointCache ?? throw new ArgumentNullException(nameof(setpointCache));
        _stateManager  = stateManager  ?? throw new ArgumentNullException(nameof(stateManager));
        _logger        = logger        ?? throw new ArgumentNullException(nameof(logger));
    }

    // =========================================================
    // MAIN ENTRY POINT
    // =========================================================

    public async Task ReconcileAsync(CancellationToken ct)
    {
        _logger.LogInformation("AlarmReconciliationService: starting startup reconciliation");

        List<AlarmActiveRow> dbRows;
        try
        {
            dbRows = await LoadAlarmActiveRowsAsync(ct);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "AlarmReconciliationService: failed to load alarm_active — skipping reconciliation (alarms may re-raise on this session)");
            return;
        }

        if (dbRows.Count == 0)
        {
            _logger.LogInformation("AlarmReconciliationService: no active alarms in DB — nothing to reconcile");
            return;
        }

        _logger.LogInformation("AlarmReconciliationService: {Count} active alarm rows found", dbRows.Count);

        // Fetch live values for all relevant tag IDs — check OPC pool first, then PLC pool
        var tagIds    = dbRows.Select(r => r.TagId).Distinct(StringComparer.OrdinalIgnoreCase).ToList();
        var tagValues = _tagPool.GetTagValues(tagIds);
        var valueMap  = tagValues.ToDictionary(v => v.TagId, StringComparer.OrdinalIgnoreCase);

        // For tags not found in OPC pool, check PLC pool and record their source
        var missingIds = tagIds.Where(id => !valueMap.ContainsKey(id)).ToList();
        // plcSourceIds: tags confirmed to live in PlcTagValuesPool — set TagSource.Plc on restored state
        var plcSourceIds = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        if (missingIds.Count > 0)
        {
            var plcEntries = _plcTagPool.GetTagValues(missingIds, plcId: null);
            foreach (var plc in plcEntries)
            {
                var tagName = plc.TagName.Length > 0 ? plc.TagName : plc.Address;
                // Wrap as TagValueCacheEntry so the rest of reconcile logic works uniformly
                valueMap[tagName] = new TagValueCacheEntry
                {
                    TagId     = tagName,
                    Value     = plc.Value?.ToString() ?? "",
                    Quality   = plc.ComputedQuality == PlcTagQuality.Good ? "Good" : "Bad",
                    Timestamp = plc.Timestamp,
                    UpdatedAt = plc.ComputedQuality == PlcTagQuality.Good ? plc.CachedAt : DateTime.UtcNow.AddSeconds(-60),
                };
                plcSourceIds.Add(tagName);
            }
        }

        var toRestoreActive = new List<AlarmActiveRow>();
        var toMarkRtn       = new List<AlarmActiveRow>();
        var opcOfflineKept  = 0;

        foreach (var row in dbRows)
        {
            // If OPC has no live value or value is stale/bad → conservative: keep alarm active
            if (!valueMap.TryGetValue(row.TagId, out var live) ||
                live.IsStale ||
                !IsGoodQuality(live.Quality) ||
                !double.TryParse(live.Value, NumberStyles.Any, CultureInfo.InvariantCulture, out double liveVal))
            {
                toRestoreActive.Add(row);
                opcOfflineKept++;
                continue;
            }

            var setpoint = _setpointCache.GetSetpoint(row.TagId);
            if (setpoint == null)
            {
                // Setpoint removed — keep alarm as-is (operator will clear)
                toRestoreActive.Add(row);
                continue;
            }

            // Check if the alarm condition is still valid for this level
            bool stillActive = row.Level switch
            {
                AlarmLevel.HighHigh => setpoint.HhLimit.HasValue && liveVal >= setpoint.HhLimit.Value,
                AlarmLevel.High     => setpoint.HLimit.HasValue  && liveVal >= setpoint.HLimit.Value,
                AlarmLevel.LowLow   => setpoint.LlLimit.HasValue && liveVal <= setpoint.LlLimit.Value,
                AlarmLevel.Low      => setpoint.LLimit.HasValue  && liveVal <= setpoint.LLimit.Value,
                _                   => false,
            };

            if (stillActive)
                toRestoreActive.Add(row);
            else
                toMarkRtn.Add(row);
        }

        // Restore active alarms into memory — with correct TagSource so guards never go blind
        foreach (var row in toRestoreActive)
        {
            var source = plcSourceIds.Contains(row.TagId) ? TagSource.Plc : TagSource.OpcDa;
            RestoreActiveState(row, source);
        }

        // Bulk RTN update in one transaction
        var rtnCount = 0;
        if (toMarkRtn.Count > 0)
            rtnCount = await BulkMarkRtnAsync(toMarkRtn, plcSourceIds, ct);

        var plcRestoredCount = toRestoreActive.Count(r => plcSourceIds.Contains(r.TagId));
        var opcRestoredCount = toRestoreActive.Count - plcRestoredCount;
        _logger.LogInformation(
            "AlarmReconciliationService: complete — restored_active={A} (opc={O}, plc={P}), auto_rtn={R}, offline_kept={Off}",
            toRestoreActive.Count, opcRestoredCount, plcRestoredCount, rtnCount, opcOfflineKept);
    }

    // =========================================================
    // PRIVATE HELPERS
    // =========================================================

    private void RestoreActiveState(AlarmActiveRow row, TagSource source = TagSource.Unknown)
    {
        var state = new AlarmRuntimeState
        {
            AlarmKey       = row.AlarmKey,
            TagId          = row.TagId,
            Level          = row.Level,
            State          = ParseAlarmState(row.AlarmStateStr),
            Source         = source,     // directed pool lookup — no blind search after restart
            OccurrenceId   = row.OccurrenceId,
            InstanceSeq    = row.InstanceSeq,
            CurrentEventId = row.CurrentEventId,
            RaisedAt       = row.RaisedAt,
            RaisedValue    = row.RaisedValue,
            SetpointValue  = row.SetpointValue,
            AckAt          = row.AckAt,
            AckBy          = row.AckBy,
            RtnAt          = row.RtnAt,
        };
        _stateManager.RestoreState(state);
        _logger.LogInformation(
            "AlarmReconciliationService: restored {Key} state={State} source={Source}",
            row.AlarmKey, state.State, source);
    }

    private async Task<int> BulkMarkRtnAsync(List<AlarmActiveRow> rows, HashSet<string> plcSourceIds, CancellationToken ct)
    {
        try
        {
            await using var conn = new NpgsqlConnection(_dbConfig.Database.ConnectionString);
            await conn.OpenAsync(ct);
            await using var tx = await conn.BeginTransactionAsync(ct);

            var now   = DateTimeOffset.UtcNow;
            var count = 0;

            foreach (var row in rows)
            {
                const string sql = """
                    UPDATE historian_raw.alarm_active
                    SET alarm_state = 'RTN_UNACK',
                        rtn_at      = @rtnAt,
                        updated_at  = NOW()
                    WHERE alarm_key  = @key
                      AND alarm_state IN ('ACTIVE_UNACK', 'ACTIVE_ACK')
                    """;
                await using var cmd = new NpgsqlCommand(sql, conn, tx) { CommandTimeout = _dbConfig.Database.CommandTimeout };
                cmd.Parameters.AddWithValue("@key",   row.AlarmKey);
                cmd.Parameters.AddWithValue("@rtnAt", now);
                var affected = await cmd.ExecuteNonQueryAsync(ct);

                if (affected > 0)
                {
                    count++;
                    // Restore in memory as RTN_UNACK so operator can acknowledge
                    var source = plcSourceIds.Contains(row.TagId) ? TagSource.Plc : TagSource.OpcDa;
                    _stateManager.RestoreState(new AlarmRuntimeState
                    {
                        AlarmKey       = row.AlarmKey,
                        TagId          = row.TagId,
                        Level          = row.Level,
                        State          = AlarmState4.RtnUnack,
                        Source         = source,   // directed pool lookup — no blind search after restart
                        OccurrenceId   = row.OccurrenceId,
                        InstanceSeq    = row.InstanceSeq,
                        CurrentEventId = row.CurrentEventId,
                        RaisedAt       = row.RaisedAt,
                        RaisedValue    = row.RaisedValue,
                        SetpointValue  = row.SetpointValue,
                        AckAt          = row.AckAt,
                        AckBy          = row.AckBy,
                        RtnAt          = now,
                    });
                }
            }

            await tx.CommitAsync(ct);
            return count;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "AlarmReconciliationService.BulkMarkRtnAsync failed");
            return 0;
        }
    }

    private async Task<List<AlarmActiveRow>> LoadAlarmActiveRowsAsync(CancellationToken ct)
    {
        await using var conn = new NpgsqlConnection(_dbConfig.Database.ConnectionString);
        await conn.OpenAsync(ct);

        const string sql = """
            SELECT alarm_key, tag_id, level, alarm_state,
                   current_event_id, occurrence_id, instance_seq,
                   raised_at, raised_value, setpoint_value,
                   ack_at, ack_by, rtn_at
            FROM historian_raw.alarm_active
            WHERE alarm_state IN ('ACTIVE_UNACK', 'ACTIVE_ACK', 'RTN_UNACK')
            ORDER BY raised_at DESC
            """;
        await using var cmd = new NpgsqlCommand(sql, conn) { CommandTimeout = _dbConfig.Database.CommandTimeout };
        await using var rdr = await cmd.ExecuteReaderAsync(ct);

        var rows = new List<AlarmActiveRow>();
        while (await rdr.ReadAsync(ct))
        {
            var levelStr = rdr.GetString(2);
            var level    = ParseLevel(levelStr);
            if (level == AlarmLevel.None)
            {
                _logger.LogWarning("AlarmReconciliationService: skipping unknown alarm level '{Level}' for key {Key}", levelStr, rdr.GetString(0));
                continue;
            }

            rows.Add(new AlarmActiveRow
            {
                AlarmKey       = rdr.GetString(0),
                TagId          = rdr.GetString(1),
                Level          = level,
                AlarmStateStr  = rdr.GetString(3),
                CurrentEventId = rdr.IsDBNull(4)  ? null : rdr.GetInt64(4),
                OccurrenceId   = rdr.GetGuid(5),
                InstanceSeq    = rdr.GetInt32(6),
                RaisedAt       = rdr.GetFieldValue<DateTimeOffset>(7),
                RaisedValue    = rdr.IsDBNull(8)  ? null : rdr.GetDouble(8),
                SetpointValue  = rdr.IsDBNull(9)  ? null : rdr.GetDouble(9),
                AckAt          = rdr.IsDBNull(10) ? null : rdr.GetFieldValue<DateTimeOffset>(10),
                AckBy          = rdr.IsDBNull(11) ? null : rdr.GetString(11),
                RtnAt          = rdr.IsDBNull(12) ? null : rdr.GetFieldValue<DateTimeOffset>(12),
            });
        }
        return rows;
    }

    private static AlarmLevel ParseLevel(string s) => s switch
    {
        "HighHigh" => AlarmLevel.HighHigh,
        "High"     => AlarmLevel.High,
        "LowLow"   => AlarmLevel.LowLow,
        "Low"      => AlarmLevel.Low,
        _          => AlarmLevel.None,
    };

    private static AlarmState4 ParseAlarmState(string s) => s switch
    {
        "ACTIVE_UNACK" => AlarmState4.ActiveUnack,
        "ACTIVE_ACK"   => AlarmState4.ActiveAck,
        "RTN_UNACK"    => AlarmState4.RtnUnack,
        _              => AlarmState4.ActiveUnack,
    };

    private static bool IsGoodQuality(string quality) =>
        quality is "Good" or "G" or "GOOD";

    // ─── Internal DTO ────────────────────────────────────────
    private sealed class AlarmActiveRow
    {
        public required string     AlarmKey       { get; init; }
        public required string     TagId          { get; init; }
        public required AlarmLevel Level          { get; init; }
        public required string     AlarmStateStr  { get; init; }
        public long?               CurrentEventId { get; init; }
        public required Guid       OccurrenceId   { get; init; }
        public required int        InstanceSeq    { get; init; }
        public required DateTimeOffset RaisedAt   { get; init; }
        public double?             RaisedValue    { get; init; }
        public double?             SetpointValue  { get; init; }
        public DateTimeOffset?     AckAt          { get; init; }
        public string?             AckBy          { get; init; }
        public DateTimeOffset?     RtnAt          { get; init; }
    }
}
