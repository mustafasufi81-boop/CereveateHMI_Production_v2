using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Npgsql;
using OpcDaWebBrowser.Services.AlarmEvaluation.Models;
using OpcDaWebBrowser.Services.AlarmEvaluation.Services;
using OpcDaWebBrowser.Services.HistorianIngest.Config;

namespace OpcDaWebBrowser.Controllers;

/// <summary>
/// REST API for the Phase 1 ISA-18.2 alarm system.
/// C# is the SOLE authority over historian_events (append-only journal) and alarm_active (runtime state).
///
/// GET  /api/alarms/active          — runtime operational state from alarm_active
/// GET  /api/alarms/history         — immutable transition journal from historian_events
/// POST /api/alarms/{key}/ack       — operator acknowledge → AlarmStateManager → both tables
/// POST /api/alarms/{key}/clear     — operator clear      → AlarmStateManager → both tables
///
/// Flask HMI proxies all alarm mutations here. It no longer writes alarm tables directly.
/// Flask retains ownership of alarm_audit_trail (operator action notes log).
/// </summary>
[ApiController]
[Route("api/alarms")]
[AllowAnonymous]
public class AlarmsController : ControllerBase
{
    private readonly AlarmStateManager _stateManager;
    private readonly HistorianConfig   _dbConfig;
    private readonly ILogger<AlarmsController> _logger;

    public AlarmsController(
        AlarmStateManager stateManager,
        HistorianConfig dbConfig,
        ILogger<AlarmsController> logger)
    {
        _stateManager = stateManager;
        _dbConfig     = dbConfig;
        _logger       = logger;
    }

    // =========================================================
    // GET /api/alarms/active
    // Returns all rows in alarm_active (non-cleared alarms).
    // HMI should poll this every 2-5 seconds.
    // =========================================================

    [HttpGet("active")]
    public async Task<IActionResult> GetActive()
    {
        try
        {
            await using var conn = new NpgsqlConnection(_dbConfig.Database.ConnectionString);
            await conn.OpenAsync();

            const string sql = """
                SELECT
                    alarm_key, tag_id, level, alarm_state,
                    current_event_id, occurrence_id, instance_seq,
                    raised_at, raised_value, setpoint_value,
                    ack_at, ack_by, rtn_at, priority, updated_at
                FROM historian_raw.alarm_active
                ORDER BY
                    CASE alarm_state
                        WHEN 'ACTIVE_UNACK' THEN 1
                        WHEN 'ACTIVE_ACK'   THEN 2
                        WHEN 'RTN_UNACK'    THEN 3
                        ELSE 4
                    END,
                    raised_at DESC
                """;

            await using var cmd = new NpgsqlCommand(sql, conn) { CommandTimeout = _dbConfig.Database.CommandTimeout };
            await using var rdr = await cmd.ExecuteReaderAsync();

            var alarms = new List<object>();
            while (await rdr.ReadAsync())
            {
                alarms.Add(new
                {
                    alarm_key        = rdr.GetString(0),
                    tag_id           = rdr.GetString(1),
                    level            = rdr.GetString(2),
                    alarm_state      = rdr.GetString(3),
                    current_event_id = rdr.IsDBNull(4)  ? (long?)null : rdr.GetInt64(4),
                    occurrence_id    = rdr.GetGuid(5),
                    instance_seq     = rdr.GetInt32(6),
                    raised_at        = rdr.GetFieldValue<DateTimeOffset>(7),
                    raised_value     = rdr.IsDBNull(8)  ? (double?)null : rdr.GetDouble(8),
                    setpoint_value   = rdr.IsDBNull(9)  ? (double?)null : rdr.GetDouble(9),
                    ack_at           = rdr.IsDBNull(10) ? (DateTimeOffset?)null : rdr.GetFieldValue<DateTimeOffset>(10),
                    ack_by           = rdr.IsDBNull(11) ? null : rdr.GetString(11),
                    rtn_at           = rdr.IsDBNull(12) ? (DateTimeOffset?)null : rdr.GetFieldValue<DateTimeOffset>(12),
                    priority         = rdr.IsDBNull(13) ? (int?)null : rdr.GetInt32(13),
                    updated_at       = rdr.GetFieldValue<DateTimeOffset>(14),
                });
            }

            return Ok(new { count = alarms.Count, alarms });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "AlarmsController.GetActive failed");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    // =========================================================
    // GET /api/alarms/history?limit=200&tagId=optional
    // Returns transition journal from historian_events.
    // =========================================================

    [HttpGet("history")]
    public async Task<IActionResult> GetHistory(
        [FromQuery] int limit = 200,
        [FromQuery] string? tagId = null,
        [FromQuery] string? fromDate = null,
        [FromQuery] string? toDate = null)
    {
        try
        {
            await using var conn = new NpgsqlConnection(_dbConfig.Database.ConnectionString);
            await conn.OpenAsync();

            var conditions = new List<string>
            {
                "alarm_state IS NOT NULL",
                "alarm_state IN ('ACTIVE_UNACK','ACTIVE_ACK','RTN_UNACK','CLEARED')"
            };

            if (!string.IsNullOrWhiteSpace(tagId))
                conditions.Add("tag_id = @tagId");
            if (!string.IsNullOrWhiteSpace(fromDate) && DateTimeOffset.TryParse(fromDate, out var from))
                conditions.Add("time >= @from");
            if (!string.IsNullOrWhiteSpace(toDate) && DateTimeOffset.TryParse(toDate, out var to))
                conditions.Add("time <= @to");

            var where = string.Join(" AND ", conditions);
            var sql = $"""
                SELECT
                    event_id, time, tag_id, event_type, alarm_state,
                    alarm_level, occurrence_id, instance_seq,
                    alarm_actual_value, alarm_setpoint, alarm_priority, message
                FROM historian_raw.historian_events
                WHERE {where}
                ORDER BY time DESC
                LIMIT @limit
                """;

            await using var cmd = new NpgsqlCommand(sql, conn) { CommandTimeout = _dbConfig.Database.CommandTimeout };
            cmd.Parameters.AddWithValue("@limit", Math.Clamp(limit, 1, 5000));
            if (!string.IsNullOrWhiteSpace(tagId))  cmd.Parameters.AddWithValue("@tagId", tagId);
            if (!string.IsNullOrWhiteSpace(fromDate) && DateTimeOffset.TryParse(fromDate, out var fromP))
                cmd.Parameters.AddWithValue("@from", fromP);
            if (!string.IsNullOrWhiteSpace(toDate) && DateTimeOffset.TryParse(toDate, out var toP))
                cmd.Parameters.AddWithValue("@to", toP);

            await using var rdr = await cmd.ExecuteReaderAsync();
            var events = new List<object>();
            while (await rdr.ReadAsync())
            {
                events.Add(new
                {
                    event_id           = rdr.GetInt64(0),
                    time               = rdr.GetFieldValue<DateTimeOffset>(1),
                    tag_id             = rdr.GetString(2),
                    event_type         = rdr.GetString(3),
                    alarm_state        = rdr.IsDBNull(4)  ? null : rdr.GetString(4),
                    alarm_level        = rdr.IsDBNull(5)  ? null : rdr.GetString(5),
                    occurrence_id      = rdr.IsDBNull(6)  ? (Guid?)null : rdr.GetGuid(6),
                    instance_seq       = rdr.IsDBNull(7)  ? (int?)null : rdr.GetInt32(7),
                    alarm_actual_value = rdr.IsDBNull(8)  ? (double?)null : rdr.GetDouble(8),
                    alarm_setpoint     = rdr.IsDBNull(9)  ? (double?)null : rdr.GetDouble(9),
                    alarm_priority     = rdr.IsDBNull(10) ? (int?)null : rdr.GetInt32(10),
                    message            = rdr.IsDBNull(11) ? null : rdr.GetString(11),
                });
            }

            return Ok(new { count = events.Count, events });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "AlarmsController.GetHistory failed");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    // =========================================================
    // POST /api/alarms/{key}/ack
    // Body: { "operator": "john" }
    // =========================================================

    [HttpPost("{key}/ack")]
    public async Task<IActionResult> Acknowledge(
        string key,
        [FromBody] AckRequest? body)
    {
        var operatorName = body?.Operator?.Trim();
        if (string.IsNullOrEmpty(operatorName))
            return BadRequest(new { error = "operator name is required in request body: { \"operator\": \"name\" }" });

        // Decode URL-encoded alarm_key (e.g. "Random.Real4%3AHigh" → "Random.Real4:High")
        var alarmKey = Uri.UnescapeDataString(key);

        _logger.LogInformation("ACK request: key={Key} operator={Op}", alarmKey, operatorName);

        // Capture pre-ACK state BEFORE calling AcknowledgeAsync (RTN_UNACK becomes CLEARED)
        var preAckState = _stateManager.GetState(alarmKey);
        var wasRtnUnack = preAckState?.State == AlarmState4.RtnUnack;

        var success = await _stateManager.AcknowledgeAsync(
            alarmKey, operatorName, HttpContext.RequestAborted, notes: body?.Notes);

        if (!success)
        {
            // Check why — is the alarm even known?
            var state = _stateManager.GetState(alarmKey);
            if (state == null)
                return NotFound(new { error = $"Alarm '{alarmKey}' not found in active alarm list", reason = "ALARM_NOT_FOUND" });

            return Conflict(new
            {
                error         = $"Cannot acknowledge alarm in state '{state.State}' — only ACTIVE_UNACK and RTN_UNACK can be acknowledged",
                reason        = "INVALID_STATE",
                alarm_key     = alarmKey,
                current_state = state.State.ToString(),
            });
        }

        // ISA-18.2: RTN_UNACK + ACK → CLEARED (row deleted). ACTIVE_UNACK + ACK → ACTIVE_ACK.
        return Ok(new
        {
            success          = true,
            alarm_key        = alarmKey,
            acknowledged_by  = operatorName,
            event_type       = wasRtnUnack ? "ALARM_CLEARED" : "ALARM_ACKNOWLEDGED",
            new_state        = wasRtnUnack ? "CLEARED"      : "ACTIVE_ACK",
        });
    }

    // =========================================================
    // POST /api/alarms/{key}/clear
    // Body: { "operator": "john", "reason": "Manually closed", "notes": "..." }
    // Only valid from ACTIVE_ACK state.
    // RTN_UNACK → CLEARED is handled automatically via ACK (ISA-18.2).
    // =========================================================

    [HttpPost("{key}/clear")]
    public async Task<IActionResult> Clear(
        string key,
        [FromBody] ClearRequest? body)
    {
        var operatorName = body?.Operator?.Trim();
        if (string.IsNullOrEmpty(operatorName))
            return BadRequest(new { error = "operator name is required in request body: { \"operator\": \"name\" }" });

        var alarmKey = Uri.UnescapeDataString(key);

        _logger.LogInformation("CLEAR request: key={Key} operator={Op} reason={Reason}",
            alarmKey, operatorName, body?.Reason ?? "none");

        // forceAck=false: operator MUST acknowledge before clearing.
        // Allowing forceAck=true caused auto-ACK+clear even when value was still high,
        // generating phantom CLEARED rows immediately followed by a new ACTIVE_UNACK.
        try
        {
        var success = await _stateManager.ClearAsync(
            alarmKey, operatorName, HttpContext.RequestAborted,
            reason:   body?.Reason,
            notes:    body?.Notes,
            forceAck: false);

        if (!success)
        {
            var state = _stateManager.GetState(alarmKey);
            if (state == null)
                return NotFound(new { error = $"Alarm '{alarmKey}' not found in active alarm list", reason = "ALARM_NOT_FOUND" });

            return Conflict(new
            {
                error         = $"Cannot clear alarm in state '{state.State}' — alarm must be acknowledged first",
                reason        = "INVALID_STATE",
                alarm_key     = alarmKey,
                current_state = state.State.ToString(),
            });
        }

        return Ok(new { success = true, alarm_key = alarmKey, cleared_by = operatorName, event_type = "ALARM_CLEARED", new_state = "CLEARED" });
        }
        catch (AlarmClearBlockedException blocked)
        {
            _logger.LogWarning("CLEAR BLOCKED (value still high): {Key} live={Live:F3} sp={SP:F3}",
                blocked.AlarmKey, blocked.LiveValue, blocked.Setpoint);
            return UnprocessableEntity(new
            {
                success       = false,
                error         = blocked.Message,
                reason        = "VALUE_STILL_VIOLATING",
                alarm_key     = blocked.AlarmKey,
                tag_id        = blocked.TagId,
                live_value    = blocked.LiveValue,
                setpoint      = blocked.Setpoint,
                is_high_alarm = blocked.IsHighAlarm,
            });
        }
    }

    // =========================================================
    // GET /api/alarms/health
    // Returns alarm engine status — used by React to show
    // "alarm engine offline" banner when C# is unreachable.
    // Always returns 200 if C# is running.
    // =========================================================

    [HttpGet("health")]
    public IActionResult Health()
    {
        var states     = _stateManager.GetAllStates();
        var activeCount = states.Values.Count(s =>
            s.State is AlarmState4.ActiveUnack or AlarmState4.ActiveAck or AlarmState4.RtnUnack);
        var unackCount  = states.Values.Count(s =>
            s.State is AlarmState4.ActiveUnack or AlarmState4.RtnUnack);

        return Ok(new
        {
            status          = "ok",
            engine          = "AlarmStateManager",
            active_count    = activeCount,
            unack_count     = unackCount,
            timestamp       = DateTimeOffset.UtcNow,
        });
    }

    // ─── Request DTOs ─────────────────────────────────────────
    public sealed class AckRequest
    {
        public string? Operator { get; set; }
        public string? Notes    { get; set; }
    }

    public sealed class ClearRequest
    {
        public string? Operator { get; set; }
        public string? Reason   { get; set; }
        public string? Notes    { get; set; }
    }
}
