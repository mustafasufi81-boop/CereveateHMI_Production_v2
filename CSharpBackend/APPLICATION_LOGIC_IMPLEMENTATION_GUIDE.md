# Application Logic Implementation Guide

**Status**: Database enforcement complete ✅, application logic pending ⏸️  
**Policy Document**: EVENT_ALARM_POLICY.md  
**SQL Script**: OPERATIONAL_HARDENING.sql (deployed)

---

## Overview

The database now enforces all critical operational policies via constraints, tables, functions, and views. However, some policy rules require application-level logic (business rules that can't be expressed in SQL constraints). This guide provides implementation templates for the pending C# application logic.

---

## 1. Alarm Deduplication (5-Minute Window)

**Policy**: EVENT_ALARM_POLICY.md Section 2  
**Status**: ⏸️ PENDING  
**Location**: `HistorianIngestHostedService.cs` or alarm generation service

### Implementation

```csharp
using System;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.EntityFrameworkCore;

public class AlarmDeduplicationService
{
    private readonly HistorianDbContext _db;
    private readonly ILogger<AlarmDeduplicationService> _logger;

    public AlarmDeduplicationService(HistorianDbContext db, ILogger<AlarmDeduplicationService> logger)
    {
        _db = db;
        _logger = logger;
    }

    /// <summary>
    /// Check if alarm already exists within 5-minute window.
    /// Per EVENT_ALARM_POLICY.md Section 2: alarm_identity = (tag_id, alarm_type, round_down(time, 5 min))
    /// </summary>
    public async Task<HistorianEvent?> FindExistingAlarmAsync(
        string tagId, 
        string alarmType, 
        DateTime alarmTime)
    {
        // Define 5-minute window
        var windowStart = alarmTime.AddMinutes(-5);
        var windowEnd = alarmTime.AddMinutes(5);

        // Query for existing active alarm
        var existingAlarm = await _db.HistorianEvents
            .Where(e => e.TagId == tagId)
            .Where(e => e.EventType == alarmType)
            .Where(e => e.Time >= windowStart)
            .Where(e => e.Time <= windowEnd)
            .Where(e => e.AlarmState == "ACTIVE")
            .OrderByDescending(e => e.Time)
            .FirstOrDefaultAsync();

        return existingAlarm;
    }

    /// <summary>
    /// Insert or update alarm with deduplication logic.
    /// </summary>
    public async Task<HistorianEvent> RaiseAlarmAsync(
        string tagId,
        string alarmType,
        double actualValue,
        double setpoint,
        string severity,
        string message,
        DateTime alarmTime)
    {
        // Check for existing alarm within 5-min window
        var existingAlarm = await FindExistingAlarmAsync(tagId, alarmType, alarmTime);

        if (existingAlarm != null)
        {
            // UPDATE existing alarm (bump severity, update value)
            _logger.LogDebug(
                "Deduplicating alarm {AlarmType} for {TagId} (existing alarm_id={AlarmId})",
                alarmType, tagId, existingAlarm.EventId);

            existingAlarm.AlarmActualValue = actualValue;
            existingAlarm.Time = alarmTime; // Update to latest time
            
            // Bump severity if new alarm is worse
            if (GetSeverityLevel(severity) > GetSeverityLevel(existingAlarm.Severity))
            {
                existingAlarm.Severity = severity;
            }

            // Recalculate priority (severity changed)
            existingAlarm.AlarmPriority = CalculateAlarmPriority(existingAlarm);

            await _db.SaveChangesAsync();
            return existingAlarm;
        }
        else
        {
            // INSERT new alarm
            var newAlarm = new HistorianEvent
            {
                Time = alarmTime,
                TagId = tagId,
                EventType = alarmType,
                Message = message,
                Severity = severity,
                AlarmState = "ACTIVE",
                AlarmSetpoint = setpoint,
                AlarmActualValue = actualValue,
                AlarmPriority = 0, // Will be calculated below
                Details = null
            };

            // Calculate dynamic priority
            newAlarm.AlarmPriority = CalculateAlarmPriority(newAlarm);

            _db.HistorianEvents.Add(newAlarm);
            await _db.SaveChangesAsync();

            _logger.LogInformation(
                "Raised new alarm {AlarmType} for {TagId} (alarm_id={AlarmId}, priority={Priority})",
                alarmType, tagId, newAlarm.EventId, newAlarm.AlarmPriority);

            return newAlarm;
        }
    }

    /// <summary>
    /// Map severity string to numeric level for comparison.
    /// </summary>
    private int GetSeverityLevel(string severity)
    {
        return severity?.ToUpper() switch
        {
            "LOW" => 1,
            "MEDIUM" => 2,
            "HIGH" => 3,
            "URGENT" => 4,
            "CRITICAL" => 5,
            _ => 0
        };
    }

    /// <summary>
    /// Calculate dynamic alarm priority (implemented below).
    /// </summary>
    private int CalculateAlarmPriority(HistorianEvent alarm)
    {
        // See section 2 below
        return AlarmPriorityCalculator.Calculate(alarm, _db);
    }
}
```

### Testing

```csharp
// Test alarm deduplication
var service = new AlarmDeduplicationService(db, logger);

// Raise first alarm
var alarm1 = await service.RaiseAlarmAsync(
    "TURBINE_SPEED", "ALARM_HIGH", 3650, 3600, "HIGH", "Speed exceeded", DateTime.Now);

// Raise duplicate alarm 2 minutes later (should UPDATE, not INSERT)
var alarm2 = await service.RaiseAlarmAsync(
    "TURBINE_SPEED", "ALARM_HIGH", 3700, 3600, "CRITICAL", "Speed still high", DateTime.Now.AddMinutes(2));

// Verify: alarm1.EventId == alarm2.EventId (same alarm)
// Verify: alarm2.AlarmActualValue == 3700 (updated)
// Verify: alarm2.Severity == "CRITICAL" (bumped)
```

### Performance

- **Query**: O(log n) with index on `(tag_id, event_type, time, alarm_state)`
- **Impact**: ~2ms per alarm check
- **Recommended Index**:
  ```sql
  CREATE INDEX idx_events_dedup ON historian_raw.historian_events 
      (tag_id, event_type, time, alarm_state) 
      WHERE event_type LIKE 'ALARM_%';
  ```

---

## 2. Dynamic Priority Calculation

**Policy**: EVENT_ALARM_POLICY.md Section 5  
**Status**: ⏸️ PENDING  
**Location**: `AlarmPriorityCalculator.cs` (new service)

### Implementation

```csharp
using System;
using System.Linq;

public static class AlarmPriorityCalculator
{
    /// <summary>
    /// Calculate dynamic alarm priority based on severity + operational context.
    /// Per EVENT_ALARM_POLICY.md Section 5:
    /// - Severity = intrinsic risk (1-5, fixed)
    /// - Priority = operational urgency (1-5, dynamic)
    /// </summary>
    public static int Calculate(HistorianEvent alarm, HistorianDbContext db)
    {
        // Start with base severity
        int basePriority = GetSeverityLevel(alarm.Severity);

        // Factor 1: Equipment criticality
        var equipmentCriticality = GetEquipmentCriticality(alarm.TagId, db);
        if (equipmentCriticality == "HIGH") basePriority++;
        if (equipmentCriticality == "LOW") basePriority--;

        // Factor 2: Process state (running equipment more critical than stopped)
        var processState = GetProcessState(alarm.TagId, db);
        if (processState == "RUNNING") basePriority++;
        if (processState == "STOPPED") basePriority--;

        // Factor 3: Alarm flooding (many alarms = likely spurious)
        var recentAlarmCount = GetRecentAlarmCount(alarm.TagId, db, minutes: 10);
        if (recentAlarmCount > 10) basePriority--; // Likely sensor malfunction

        // Factor 4: Time of day (night shift has fewer operators)
        var hour = DateTime.Now.Hour;
        if (hour >= 0 && hour < 6) basePriority--; // Night shift

        // Factor 5: Cascading alarms (parent alarm already exists)
        if (alarm.ParentAlarmId != null) basePriority--; // Secondary alarm

        // Clamp to 1-5 range
        return Math.Clamp(basePriority, 1, 5);
    }

    private static int GetSeverityLevel(string severity)
    {
        return severity?.ToUpper() switch
        {
            "LOW" => 1,
            "MEDIUM" => 2,
            "HIGH" => 3,
            "URGENT" => 4,
            "CRITICAL" => 5,
            _ => 2 // Default to MEDIUM
        };
    }

    private static string GetEquipmentCriticality(string tagId, HistorianDbContext db)
    {
        // Query equipment_hierarchy table (future enhancement)
        // For now, use simple heuristics
        if (tagId.StartsWith("TURBINE_")) return "HIGH";
        if (tagId.StartsWith("GENERATOR_")) return "HIGH";
        if (tagId.StartsWith("AUX_")) return "LOW";
        return "MEDIUM";
    }

    private static string GetProcessState(string tagId, HistorianDbContext db)
    {
        // Query latest value to infer state
        // Example: If TURBINE_SPEED > 0, state = RUNNING
        var latestValue = db.HistorianLatestValue
            .Where(v => v.TagId == tagId)
            .Select(v => v.ValueDouble)
            .FirstOrDefault();

        if (tagId.Contains("SPEED") && latestValue > 0) return "RUNNING";
        if (tagId.Contains("SPEED") && latestValue == 0) return "STOPPED";
        return "UNKNOWN";
    }

    private static int GetRecentAlarmCount(string tagId, HistorianDbContext db, int minutes)
    {
        var cutoff = DateTime.Now.AddMinutes(-minutes);
        return db.HistorianEvents
            .Where(e => e.TagId == tagId)
            .Where(e => e.EventType.StartsWith("ALARM_"))
            .Where(e => e.Time >= cutoff)
            .Count();
    }
}
```

### Testing

```csharp
// Test priority calculation
var alarm = new HistorianEvent
{
    TagId = "TURBINE_SPEED",
    EventType = "ALARM_HIGH",
    Severity = "HIGH", // Base priority = 3
    AlarmActualValue = 3700,
    Time = DateTime.Now
};

var priority = AlarmPriorityCalculator.Calculate(alarm, db);

// Expected adjustments:
// +1 (TURBINE_ = HIGH criticality)
// +1 (RUNNING state)
// -0 (no alarm flooding)
// -0 (daytime)
// = 3 + 1 + 1 = 5 (clamped to max)
Assert.AreEqual(5, priority);
```

### Future Enhancements

Add equipment_hierarchy table:
```sql
CREATE TABLE historian_meta.equipment_hierarchy (
    equipment_id TEXT PRIMARY KEY,
    equipment_name TEXT,
    equipment_type TEXT,
    criticality TEXT CHECK (criticality IN ('LOW', 'MEDIUM', 'HIGH')),
    parent_equipment_id TEXT,
    tag_prefix TEXT
);

INSERT INTO equipment_hierarchy VALUES
    ('TURBINE_1', 'Main Turbine', 'TURBINE', 'HIGH', NULL, 'TURBINE_%'),
    ('GENERATOR_1', 'Main Generator', 'GENERATOR', 'HIGH', 'TURBINE_1', 'GENERATOR_%');
```

---

## 3. Alarm Suppression Check

**Policy**: EVENT_ALARM_POLICY.md Section 4  
**Status**: ⏸️ PENDING  
**Location**: `AlarmSuppressionService.cs` (new service)

### Implementation

```csharp
using System;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.EntityFrameworkCore;

public class AlarmSuppressionService
{
    private readonly HistorianDbContext _db;
    private readonly ILogger<AlarmSuppressionService> _logger;

    public AlarmSuppressionService(HistorianDbContext db, ILogger<AlarmSuppressionService> logger)
    {
        _db = db;
        _logger = logger;
    }

    /// <summary>
    /// Check if alarm should be suppressed based on schedule.
    /// Per EVENT_ALARM_POLICY.md Section 4: 3 types of suppression.
    /// </summary>
    public async Task<(bool IsSuppressed, string Reason)> ShouldSuppressAlarmAsync(
        string tagId,
        string alarmType,
        DateTime alarmTime)
    {
        // Type 1: Time-based suppression (scheduled)
        var timeBasedSuppression = await CheckTimeBasedSuppressionAsync(alarmType, tagId, alarmTime);
        if (timeBasedSuppression.IsSuppressed)
        {
            return timeBasedSuppression;
        }

        // Type 2: Manual suppression (operator/engineer)
        var manualSuppression = await CheckManualSuppressionAsync(tagId, alarmType);
        if (manualSuppression.IsSuppressed)
        {
            return manualSuppression;
        }

        // Type 3: Maintenance window (system-wide)
        var maintenanceWindow = CheckMaintenanceWindow();
        if (maintenanceWindow.IsSuppressed)
        {
            return maintenanceWindow;
        }

        return (false, null); // Not suppressed
    }

    /// <summary>
    /// Check alarm_suppression_schedule table.
    /// </summary>
    private async Task<(bool IsSuppressed, string Reason)> CheckTimeBasedSuppressionAsync(
        string alarmType,
        string tagId,
        DateTime alarmTime)
    {
        var currentTime = alarmTime.TimeOfDay;
        var currentDayOfWeek = (int)alarmTime.DayOfWeek; // 0=Sunday, 6=Saturday

        var schedule = await _db.AlarmSuppressionSchedule
            .Where(s => s.Enabled)
            .Where(s => EF.Functions.Like(alarmType, s.AlarmTypePattern))
            .Where(s => s.TagIdPattern == null || EF.Functions.Like(tagId, s.TagIdPattern))
            .Where(s => s.DaysOfWeek.Contains(currentDayOfWeek))
            .Where(s => currentTime >= s.SuppressStart && currentTime <= s.SuppressEnd)
            .FirstOrDefaultAsync();

        if (schedule != null)
        {
            _logger.LogDebug(
                "Alarm {AlarmType} suppressed by schedule {ScheduleId}: {Reason}",
                alarmType, schedule.ScheduleId, schedule.Reason);

            return (true, $"Scheduled suppression: {schedule.Reason}");
        }

        return (false, null);
    }

    /// <summary>
    /// Check for manual operator suppression.
    /// </summary>
    private async Task<(bool IsSuppressed, string Reason)> CheckManualSuppressionAsync(
        string tagId,
        string alarmType)
    {
        // Check if alarm was manually suppressed (and not expired)
        var suppressedAlarm = await _db.HistorianEvents
            .Where(e => e.TagId == tagId)
            .Where(e => e.EventType == alarmType)
            .Where(e => e.AlarmState == "SUPPRESSED")
            .Where(e => e.Time >= DateTime.Now.AddHours(-24)) // Max 24-hour suppression
            .OrderByDescending(e => e.Time)
            .FirstOrDefaultAsync();

        if (suppressedAlarm != null)
        {
            _logger.LogDebug(
                "Alarm {AlarmType} manually suppressed (alarm_id={AlarmId})",
                alarmType, suppressedAlarm.EventId);

            return (true, $"Manual suppression by {suppressedAlarm.AcknowledgedBy}");
        }

        return (false, null);
    }

    /// <summary>
    /// Check for maintenance window (system-wide suppression).
    /// </summary>
    private (bool IsSuppressed, string Reason) CheckMaintenanceWindow()
    {
        // Check configuration or global flag
        // For now, hardcode (replace with config check)
        bool isMaintenanceMode = false; // TODO: Load from config or API

        if (isMaintenanceMode)
        {
            return (true, "System in maintenance mode");
        }

        return (false, null);
    }
}
```

### API Endpoints (for manual suppression)

```csharp
[ApiController]
[Route("api/alarms")]
public class AlarmSuppressionController : ControllerBase
{
    private readonly HistorianDbContext _db;
    private readonly ILogger<AlarmSuppressionController> _logger;

    [HttpPost("{alarmId}/suppress")]
    [Authorize(Roles = "Engineer,Admin")] // Requires engineer role
    public async Task<IActionResult> SuppressAlarm(
        long alarmId,
        [FromBody] SuppressAlarmRequest request)
    {
        var alarm = await _db.HistorianEvents.FindAsync(alarmId);
        if (alarm == null) return NotFound();

        if (alarm.AlarmState != "ACTIVE")
            return BadRequest("Only ACTIVE alarms can be suppressed");

        // Validate max suppression duration (24 hours)
        if (request.DurationMinutes > 1440)
            return BadRequest("Max suppression duration: 24 hours");

        // Update alarm state
        alarm.AlarmState = "SUPPRESSED";
        alarm.AcknowledgedBy = User.Identity.Name; // Track who suppressed
        alarm.AcknowledgedAt = DateTime.Now;

        // Log suppression event
        _db.HistorianEvents.Add(new HistorianEvent
        {
            Time = DateTime.Now,
            TagId = alarm.TagId,
            EventType = "AUDIT_ALARM_SUPPRESSED",
            Message = $"Alarm {alarmId} suppressed by {User.Identity.Name} for {request.DurationMinutes} min",
            Severity = "INFO",
            Details = JsonSerializer.Serialize(new
            {
                alarm_id = alarmId,
                user_id = User.Identity.Name,
                duration_min = request.DurationMinutes,
                reason = request.Reason
            })
        });

        await _db.SaveChangesAsync();

        _logger.LogInformation(
            "Alarm {AlarmId} suppressed by {User} for {Duration} min: {Reason}",
            alarmId, User.Identity.Name, request.DurationMinutes, request.Reason);

        return Ok();
    }

    [HttpGet("suppression-schedule")]
    [Authorize(Roles = "Engineer,Admin")]
    public async Task<IActionResult> GetSuppressionSchedule()
    {
        var schedules = await _db.AlarmSuppressionSchedule
            .Where(s => s.Enabled)
            .OrderBy(s => s.SuppressStart)
            .ToListAsync();

        return Ok(schedules);
    }

    [HttpPost("maintenance-mode")]
    [Authorize(Roles = "Admin")]
    public async Task<IActionResult> SetMaintenanceMode([FromBody] MaintenanceModeRequest request)
    {
        // Set global flag (store in config or database)
        // TODO: Implement maintenance mode flag persistence

        _logger.LogWarning(
            "Maintenance mode {Action} by {User}",
            request.Enabled ? "ENABLED" : "DISABLED",
            User.Identity.Name);

        return Ok();
    }
}

public class SuppressAlarmRequest
{
    public int DurationMinutes { get; set; }
    public string Reason { get; set; }
}

public class MaintenanceModeRequest
{
    public bool Enabled { get; set; }
    public string Reason { get; set; }
}
```

### Testing

```csharp
// Test time-based suppression
var service = new AlarmSuppressionService(db, logger);

// Night shift suppression (00:00-06:00)
var nightAlarm = new DateTime(2024, 12, 10, 2, 30, 0); // Tuesday 02:30 AM
var (isSuppressed, reason) = await service.ShouldSuppressAlarmAsync(
    "TURBINE_SPEED", "ALARM_LOW", nightAlarm);

Assert.IsTrue(isSuppressed);
Assert.AreEqual("Scheduled suppression: Night shift - operators absent", reason);

// Daytime alarm (not suppressed)
var dayAlarm = new DateTime(2024, 12, 10, 14, 30, 0); // Tuesday 02:30 PM
var (isSuppressed2, reason2) = await service.ShouldSuppressAlarmAsync(
    "TURBINE_SPEED", "ALARM_LOW", dayAlarm);

Assert.IsFalse(isSuppressed2);
```

---

## 4. Alarm Acknowledgment with Authentication

**Policy**: EVENT_ALARM_POLICY.md Section 9  
**Status**: ⏸️ PENDING  
**Location**: `AlarmAcknowledgmentController.cs` (API endpoint)

### Implementation

```csharp
[ApiController]
[Route("api/alarms")]
public class AlarmAcknowledgmentController : ControllerBase
{
    private readonly HistorianDbContext _db;
    private readonly ILogger<AlarmAcknowledgmentController> _logger;

    [HttpPost("{alarmId}/acknowledge")]
    [Authorize(Roles = "Operator,Engineer,Admin")] // Requires authentication
    public async Task<IActionResult> AcknowledgeAlarm(
        long alarmId,
        [FromBody] AcknowledgeAlarmRequest request)
    {
        // Call database function (validates state, logs acknowledgment)
        var result = await _db.Database
            .ExecuteSqlInterpolatedAsync($@"
                SELECT acknowledge_alarm(
                    {alarmId}, 
                    {User.Identity.Name}, 
                    {request.Notes}
                )");

        if (result > 0)
        {
            _logger.LogInformation(
                "Alarm {AlarmId} acknowledged by {User}: {Notes}",
                alarmId, User.Identity.Name, request.Notes);

            return Ok(new { success = true, message = "Alarm acknowledged" });
        }
        else
        {
            return BadRequest(new { success = false, message = "Alarm not found or already acknowledged" });
        }
    }

    [HttpGet("active")]
    [Authorize(Roles = "Operator,Engineer,Admin")]
    public async Task<IActionResult> GetActiveAlarms()
    {
        // Query vw_active_alarms view (per EVENT_ALARM_POLICY.md Section 9)
        var alarms = await _db.VwActiveAlarms
            .OrderByDescending(a => a.AlarmPriority)
            .ThenBy(a => a.RaisedAt)
            .Take(100) // Limit to top 100
            .ToListAsync();

        return Ok(alarms);
    }
}

public class AcknowledgeAlarmRequest
{
    public string Notes { get; set; }
}
```

### Testing

```csharp
// Test authentication enforcement
var client = new HttpClient();

// Anonymous request (should fail)
var response1 = await client.PostAsync("/api/alarms/123/acknowledge", content);
Assert.AreEqual(HttpStatusCode.Unauthorized, response1.StatusCode);

// Authenticated request (should succeed)
client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", operatorToken);
var response2 = await client.PostAsync("/api/alarms/123/acknowledge", content);
Assert.AreEqual(HttpStatusCode.OK, response2.StatusCode);
```

---

## 5. Rate-Limited Event Logging

**Policy**: Smart validation trigger (OPERATIONAL_HARDENING.sql)  
**Status**: ⏸️ PENDING  
**Location**: `DataLoggingService.cs` or validation service

### Implementation

```csharp
public class RateLimitedEventLogger
{
    private readonly HistorianDbContext _db;
    private readonly ILogger<RateLimitedEventLogger> _logger;

    /// <summary>
    /// Log event with rate limiting (don't log every sample).
    /// Per smart validation trigger: Max 1 log per 5 min per tag per event type.
    /// </summary>
    public async Task LogEventAsync(
        string tagId,
        string eventType,
        string message,
        string severity,
        object details = null)
    {
        // Check last logged time for this tag + event type
        var lastLogged = await _db.HistorianEvents
            .Where(e => e.TagId == tagId)
            .Where(e => e.EventType == eventType)
            .OrderByDescending(e => e.Time)
            .Select(e => e.Time)
            .FirstOrDefaultAsync();

        // Rate limit: Only log if last log >5 min ago
        if (lastLogged != default && (DateTime.Now - lastLogged).TotalMinutes < 5)
        {
            // Skip logging (rate limited)
            _logger.LogTrace(
                "Event {EventType} for {TagId} rate-limited (last logged {LastLogged})",
                eventType, tagId, lastLogged);
            return;
        }

        // Log event
        var eventLog = new HistorianEvent
        {
            Time = DateTime.Now,
            TagId = tagId,
            EventType = eventType,
            Message = message,
            Severity = severity,
            Details = details != null ? JsonSerializer.Serialize(details) : null
        };

        // Separate transaction (best-effort, don't block ingestion)
        try
        {
            using (var transaction = await _db.Database.BeginTransactionAsync())
            {
                _db.HistorianEvents.Add(eventLog);
                await _db.SaveChangesAsync();
                await transaction.CommitAsync();
            }
        }
        catch (Exception ex)
        {
            // Log failure but don't propagate (resilience rule)
            _logger.LogWarning(ex, "Event logging failed (ingestion continues): {EventType}", eventType);
        }
    }
}
```

### Usage in Validation

```csharp
// In data validation service
foreach (var sample in samples)
{
    if (sample.ValueText.Length > 1000)
    {
        // Truncate value
        sample.ValueText = sample.ValueText.Substring(0, 1000);
        sample.Quality = "U"; // Uncertain (modified)

        // Log warning (rate-limited)
        await eventLogger.LogEventAsync(
            sample.TagId,
            "DATA_QUALITY_OVERSIZED_VALUE",
            $"Value truncated from {originalLength} to 1000 chars",
            "LOW",
            new { original_length = originalLength, truncated_length = 1000 }
        );
    }
}
```

---

## 6. Integration with Existing Services

### HistorianIngestHostedService.cs

Add alarm deduplication + suppression check:

```csharp
public class HistorianIngestHostedService : BackgroundService
{
    private readonly AlarmDeduplicationService _alarmDedup;
    private readonly AlarmSuppressionService _alarmSuppression;
    private readonly RateLimitedEventLogger _eventLogger;

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            // Read OPC tag values
            var tagValues = await _opcService.GetActiveConnection()?.ReadTagValues();

            foreach (var tag in tagValues)
            {
                // Check for alarm conditions
                if (tag.Value > tag.HighLimit)
                {
                    // Check if alarm should be suppressed
                    var (isSuppressed, reason) = await _alarmSuppression.ShouldSuppressAlarmAsync(
                        tag.TagId, "ALARM_HIGH", DateTime.Now);

                    if (isSuppressed)
                    {
                        _logger.LogDebug("Alarm suppressed: {Reason}", reason);
                        continue; // Skip alarm
                    }

                    // Raise alarm (with deduplication)
                    await _alarmDedup.RaiseAlarmAsync(
                        tag.TagId,
                        "ALARM_HIGH",
                        tag.Value,
                        tag.HighLimit,
                        "HIGH",
                        $"Value {tag.Value} exceeded limit {tag.HighLimit}",
                        DateTime.Now
                    );
                }
            }

            await Task.Delay(1000, stoppingToken); // Poll every 1 sec
        }
    }
}
```

---

## 7. Deployment Steps

### Step 1: Database Deployment (COMPLETE) ✅

```bash
psql -f OPERATIONAL_HARDENING.sql
```

### Step 2: Application Code Changes (PENDING) ⏸️

1. **Add new services**:
   - `AlarmDeduplicationService.cs`
   - `AlarmPriorityCalculator.cs`
   - `AlarmSuppressionService.cs`
   - `RateLimitedEventLogger.cs`

2. **Add API controllers**:
   - `AlarmAcknowledgmentController.cs`
   - `AlarmSuppressionController.cs`

3. **Update existing services**:
   - `HistorianIngestHostedService.cs` (add alarm deduplication + suppression)
   - `DataLoggingService.cs` (add rate-limited event logging)

4. **Add authentication**:
   - Configure JWT or cookie authentication
   - Define roles: Operator, Engineer, Admin
   - Require `[Authorize]` on alarm endpoints

5. **Register services** (Program.cs):
   ```csharp
   builder.Services.AddScoped<AlarmDeduplicationService>();
   builder.Services.AddScoped<AlarmSuppressionService>();
   builder.Services.AddScoped<RateLimitedEventLogger>();
   ```

### Step 3: Testing

1. **Unit tests**:
   - Test alarm deduplication (5-min window)
   - Test priority calculation (severity + context)
   - Test suppression schedule matching
   - Test rate-limited logging

2. **Integration tests**:
   - Test API authentication
   - Test alarm acknowledgment workflow
   - Test alarm flooding scenario (verify deduplication)
   - Test night shift suppression

3. **Load tests**:
   - 100 alarms/sec (verify deduplication prevents DB overload)
   - 1000 tags × 1 sample/sec (verify event logging doesn't block ingestion)

### Step 4: Production Deployment

1. Deploy database changes (already done)
2. Deploy application changes (code + config)
3. Restart C# services
4. Monitor logs for errors
5. Verify alarm acknowledgment working
6. Verify suppression schedule working
7. Verify storage growth (truncation + retention working)

---

## 8. Monitoring & Validation

### Key Metrics

1. **Alarm Deduplication Rate**:
   - Query: `SELECT COUNT(*) FROM historian_events WHERE event_type LIKE 'ALARM_%' AND time > now() - INTERVAL '1 hour'`
   - Expected: <100 alarms/hour (vs >1000/hour without deduplication)

2. **Alarm Acknowledgment SLA**:
   - Query: `SELECT AVG(EXTRACT(EPOCH FROM (acknowledged_at - time))/60) FROM historian_events WHERE alarm_state = 'ACKNOWLEDGED'`
   - Target: <60 minutes average

3. **Suppression Effectiveness**:
   - Query: `SELECT COUNT(*) FROM historian_events WHERE alarm_state = 'SUPPRESSED' AND time > now() - INTERVAL '1 day'`
   - Expected: ~10-20% of alarms suppressed (night shifts + maintenance)

4. **Event Logging Rate**:
   - Query: `SELECT COUNT(*) FROM historian_events WHERE event_type = 'DATA_QUALITY_OVERSIZED_VALUE' AND time > now() - INTERVAL '1 hour'`
   - Expected: <60/hour (vs >3600/hour without rate limiting)

### Dashboards

1. **Operator Dashboard** (HMI):
   - Query: `SELECT * FROM vw_active_alarms ORDER BY alarm_priority DESC LIMIT 20`
   - Chart: Alarm count by priority (stacked bar)
   - Chart: Alarm acknowledgment trend (line)

2. **Engineer Dashboard** (troubleshooting):
   - Query: `SELECT * FROM vw_data_quality WHERE time > now() - INTERVAL '1 day'`
   - Chart: Data quality warnings by tag (bar)
   - Chart: Oversized values trend (line)

3. **IT Dashboard** (infrastructure):
   - Query: `SELECT * FROM vw_system_events WHERE time > now() - INTERVAL '1 day'`
   - Chart: System events by type (pie)
   - Chart: Ingestion rate (line)

4. **Root Cause Dashboard** (analysis):
   - Query: `SELECT * FROM vw_events_timeline WHERE time > now() - INTERVAL '1 hour'`
   - Chart: Event timeline (Gantt-style)
   - Filter: By event category (SYSTEM, ALARM, DATA_QUALITY)

---

## 9. Success Criteria

### Application Logic Complete When:

- [x] Database enforcement deployed (COMPLETE)
- [ ] Alarm deduplication implemented (5-min window check)
- [ ] Dynamic priority calculation implemented (severity + context)
- [ ] Alarm suppression implemented (3 types: scheduled, manual, maintenance)
- [ ] Authentication added to alarm endpoints (JWT/cookie)
- [ ] Rate-limited event logging implemented
- [ ] Unit tests passing (>80% coverage)
- [ ] Integration tests passing (alarm workflow end-to-end)
- [ ] API documentation updated (Swagger)

### Production Ready When:

- [ ] All application logic tests passing
- [ ] Deployed to production
- [ ] Operators trained on new workflow
- [ ] 1-week burn-in complete
- [ ] No alarm acknowledgment failures
- [ ] No ingestion blocks (resilience validated)
- [ ] Storage growth predictable (truncation + retention working)
- [ ] Event type distribution correct (90% ALARM_*, 5% SYSTEM_*, 5% others)

---

## 10. Next Steps

### This Week

1. Implement `AlarmDeduplicationService.cs` (2 hours)
2. Implement `AlarmPriorityCalculator.cs` (2 hours)
3. Implement `AlarmSuppressionService.cs` (2 hours)
4. Add `AlarmAcknowledgmentController.cs` API (1 hour)
5. Add `AlarmSuppressionController.cs` API (1 hour)
6. Update `HistorianIngestHostedService.cs` integration (2 hours)
7. Add authentication (JWT setup) (2 hours)
8. Write unit tests (4 hours)
9. Write integration tests (4 hours)

**Total Effort**: ~20 hours (2-3 days)

### Next Week

1. Deploy to production
2. Monitor for issues
3. Collect baseline metrics
4. 1-week burn-in validation

### After Burn-In

1. Design analytics layer (equipment states, MTBF/MTTR, OEE)
2. Implement StateDetectionService
3. Implement OEE calculator
4. Create analytics dashboards

---

## References

- **EVENT_ALARM_POLICY.md**: Policy framework (10 sections)
- **OPERATIONAL_HARDENING.sql**: Database enforcement (deployed)
- **OPERATIONAL_HARDENING_POLICY_ENFORCEMENT.md**: Policy enforcement summary

---

**Status**: Database complete ✅, application logic pending ⏸️ (20 hours estimated)
