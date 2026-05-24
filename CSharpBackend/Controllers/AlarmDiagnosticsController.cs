using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Npgsql;
using OpcDaWebBrowser.Services.AlarmEvaluation.Services;
using OpcDaWebBrowser.Services.HistorianIngest.Config;

namespace OpcDaWebBrowser.Controllers;

/// <summary>
/// Diagnostic endpoint for alarm evaluation pipeline.
/// GET /api/alarm-diagnostics — returns live state of AlarmEvaluationService.
/// Use this to diagnose why alarms are not being raised.
/// </summary>
[ApiController]
[Route("api/alarm-diagnostics")]
[AllowAnonymous]
public class AlarmDiagnosticsController : ControllerBase
{
    private readonly AlarmEvaluationService _alarmService;
    private readonly HistorianConfig _dbConfig;
    private readonly ILogger<AlarmDiagnosticsController> _logger;

    public AlarmDiagnosticsController(
        AlarmEvaluationService alarmService,
        HistorianConfig dbConfig,
        ILogger<AlarmDiagnosticsController> logger)
    {
        _alarmService = alarmService;
        _dbConfig     = dbConfig;
        _logger       = logger;
    }

    [HttpGet]
    public ActionResult<AlarmEvalDiagnostics> Get()
    {
        try { return Ok(_alarmService.GetDiagnostics()); }
        catch (Exception ex) { return StatusCode(500, new { error = ex.Message }); }
    }

    /// POST /api/alarm-diagnostics/test-insert
    /// Fires the exact same INSERTs the C# alarm service uses — step by step.
    /// Returns exact DB error at each step. Cleans up test row after.
    [HttpPost("test-insert")]
    public async Task<IActionResult> TestInsert()
    {
        var steps = new List<string>();
        try
        {
            await using var conn = new NpgsqlConnection(_dbConfig.Database.ConnectionString);
            await conn.OpenAsync();
            steps.Add("DB connection: OK");

            // STEP 1 — exact historian_events INSERT (same as RaiseAlarmAsync)
            long eventId = 0;
            try
            {
                const string sql = """
                    INSERT INTO historian_raw.historian_events
                        (time, tag_id, event_type, severity, message,
                         alarm_state, alarm_priority, alarm_setpoint, alarm_actual_value)
                    VALUES
                        (@time, @tagId, @eventType, @severity, @message,
                         'ACTIVE_UNACK', @priority, @setpoint, @actualValue)
                    RETURNING event_id
                    """;
                await using var cmd = new NpgsqlCommand(sql, conn);
                cmd.Parameters.AddWithValue("@time",        DateTimeOffset.UtcNow);
                cmd.Parameters.AddWithValue("@tagId",       "TEST.DiagTag");
                cmd.Parameters.AddWithValue("@eventType",   "ALARM_RAISED_H");
                cmd.Parameters.AddWithValue("@severity",    1);
                cmd.Parameters.AddWithValue("@message",     "Diagnostic test - safe to delete");
                cmd.Parameters.AddWithValue("@priority",    1);
                cmd.Parameters.AddWithValue("@setpoint",    20000.0);
                cmd.Parameters.AddWithValue("@actualValue", 23000.0);
                eventId = (long)(await cmd.ExecuteScalarAsync() ?? 0);
                steps.Add($"historian_events INSERT: OK  event_id={eventId}");
            }
            catch (Exception ex)
            {
                steps.Add($"historian_events INSERT FAILED: {ex.Message}");
                return Ok(new { status = "FAILED_STEP1", steps });
            }

            // STEP 2 — exact alarm_audit_trail INSERT (same as RaiseAlarmAsync)
            try
            {
                const string auditSql = """
                    INSERT INTO historian_raw.alarm_audit_trail
                        (event_id, tag_id, event_type, action_type, performed_by,
                         previous_state, new_state, alarm_priority, alarm_actual_value, alarm_setpoint)
                    VALUES
                        (@eventId, @tagId, @eventType, 'RAISED', 'DIAG_TEST',
                         'NORMAL', 'ACTIVE', @priority, @actualValue, @setpoint)
                    """;
                await using var cmd = new NpgsqlCommand(auditSql, conn);
                cmd.Parameters.AddWithValue("@eventId",     eventId);
                cmd.Parameters.AddWithValue("@tagId",       "TEST.DiagTag");
                cmd.Parameters.AddWithValue("@eventType",   "ALARM_RAISED_H");
                cmd.Parameters.AddWithValue("@priority",    1);
                cmd.Parameters.AddWithValue("@actualValue", 23000.0);
                cmd.Parameters.AddWithValue("@setpoint",    20000.0);
                await cmd.ExecuteNonQueryAsync();
                steps.Add("alarm_audit_trail INSERT: OK");
            }
            catch (Exception ex)
            {
                steps.Add($"alarm_audit_trail INSERT FAILED: {ex.Message}");
            }

            // STEP 3 — cleanup test row
            await using var del = new NpgsqlCommand(
                "DELETE FROM historian_raw.historian_events WHERE tag_id='TEST.DiagTag'", conn);
            await del.ExecuteNonQueryAsync();
            steps.Add("Cleanup: test row deleted");

            return Ok(new { status = "SUCCESS", steps });
        }
        catch (Exception ex)
        {
            steps.Add($"OUTER ERROR: {ex.GetType().Name}: {ex.Message}");
            return Ok(new { status = "FAILED", steps });
        }
    }

    /// POST /api/alarm-diagnostics/test-raise?tagId=Random.Real4&value=23000
    /// Calls the REAL AlarmEvaluationService.RaiseAlarmAsync path end-to-end.
    /// Returns exact error if it fails.
    [HttpPost("test-raise")]
    public async Task<IActionResult> TestRaise([FromQuery] string tagId = "Random.Real4", [FromQuery] double value = 23000)
    {
        var before = _alarmService.GetDiagnostics().AlarmsRaised;
        var error  = await _alarmService.TestRaiseAlarmAsync(tagId, value);
        var after  = _alarmService.GetDiagnostics().AlarmsRaised;
        if (error != null)
            return Ok(new { success = false, error });
        return Ok(new { success = true, rowInserted = after > before, alarmsTotal = after });
    }
}
