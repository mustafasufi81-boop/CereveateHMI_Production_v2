# ALARM & TRIP SYSTEM - Implementation Plan

**Project**: Real-Time Alarm Generation & Trip Detection  
**Version**: 1.0  
**Date**: December 22, 2025  
**Status**: Planning Phase  
**Prerequisites**: OPERATIONAL_HARDENING.sql deployed

---

## Executive Summary

Implement end-to-end alarm and trip detection system that:
1. Analyzes historical signal data to establish baseline ranges
2. Generates real-time alarms when signals exceed configured thresholds
3. Detects trip events by correlating alarms with equipment state changes
4. Provides web UI for operators to monitor and acknowledge alarms

**Estimated Timeline**: 3-4 weeks (1 developer)  
**Complexity**: Medium-High (requires C# services + UI development)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    OPC DA Server (Real-time data)               │
└────────────────────┬────────────────────────────────────────────┘
                     │ TagValuesUpdated event
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│              OpcDaService (Existing - No changes)                │
└────┬────────────────────────────────┬────────────────────────────┘
     │                                │
     │                                │
     ▼                                ▼
┌────────────────────────┐   ┌──────────────────────────┐
│ HistorianIngestService │   │ AlarmGenerationService   │ ← NEW
│   (Existing - DB log)  │   │  (Compare vs thresholds) │
└────────────────────────┘   └─────────┬────────────────┘
                                       │ Alarm detected
                                       ▼
                            ┌──────────────────────────┐
                            │ historian_events (table) │
                            │  - ALARM_HIGH_HIGH       │
                            │  - ALARM_HIGH            │
                            │  - ALARM_LOW             │
                            │  - ALARM_LOW_LOW         │
                            └─────────┬────────────────┘
                                      │
                                      ▼
                            ┌──────────────────────────┐
                            │  TripDetectionService    │ ← NEW
                            │  (Alarm + Equipment stop)│
                            └─────────┬────────────────┘
                                      │ Trip detected
                                      ▼
                            ┌──────────────────────────┐
                            │ trip_event_tracking      │
                            │  (table)                 │
                            └─────────┬────────────────┘
                                      │
                                      ▼
                            ┌──────────────────────────┐
                            │    Web UI Dashboard      │ ← NEW
                            │  - Active Alarms         │
                            │  - Trip History          │
                            │  - Acknowledgment        │
                            └──────────────────────────┘
```

---

## Phase 1: Database Foundation & Analysis

### 1.1 Prerequisites (Already Complete ✅)
- `OPERATIONAL_HARDENING.sql` deployed
- Tables exist:
  - `historian_meta.tag_master` (with alarm columns)
  - `historian_raw.historian_timeseries` (signal data)
  - `historian_raw.historian_events` (alarm storage)
  - `historian_raw.trip_event_tracking` (trip storage)
- Functions exist:
  - `update_tag_value_ranges()` - Calculate observed min/max
  - `suggest_alarm_thresholds()` - Auto-generate thresholds
  - `apply_suggested_alarm_thresholds()` - Apply to tag_master

### 1.2 Data Analysis Scripts (NEW - SQL Scripts)

**File**: `scripts/01_analyze_signal_ranges.sql`
```sql
-- Analyze last 7 days of data for all enabled tags
SELECT update_tag_value_ranges();

-- View observed ranges
SELECT 
    tag_id,
    tag_name,
    observed_min_value,
    observed_max_value,
    observation_sample_count,
    ROUND((observed_max_value - observed_min_value)::numeric, 2) AS value_range
FROM historian_meta.tag_master
WHERE observation_sample_count > 1000  -- Sufficient data
ORDER BY tag_id;
```

**File**: `scripts/02_generate_suggested_thresholds.sql`
```sql
-- Get AI-suggested alarm thresholds
SELECT 
    tag_id,
    observed_min,
    observed_max,
    suggested_low_low,   -- min - 5%
    suggested_low,       -- min - 10%
    suggested_high,      -- max + 10%
    suggested_high_high, -- max + 15%
    sample_count,
    recommendation
FROM suggest_alarm_thresholds()
ORDER BY tag_id;
```

**File**: `scripts/03_configure_alarms_auto.sql`
```sql
-- Auto-apply suggested thresholds for all tags with sufficient data
DO $$
DECLARE
    v_tag RECORD;
BEGIN
    FOR v_tag IN 
        SELECT tag_id 
        FROM historian_meta.tag_master 
        WHERE observation_sample_count > 1000 
          AND data_type = 'Double'
    LOOP
        PERFORM apply_suggested_alarm_thresholds(
            v_tag.tag_id, 
            3,    -- Priority: 3 (Medium)
            2.0   -- Deadband: 2.0 units
        );
        RAISE NOTICE 'Applied thresholds for: %', v_tag.tag_id;
    END LOOP;
END $$;
```

**File**: `scripts/04_configure_alarms_manual.sql`
```sql
-- Manual alarm configuration for critical equipment
UPDATE historian_meta.tag_master 
SET 
    -- User-configured limits (production use)
    alarm_hh_limit = 100.0,
    alarm_h_limit = 90.0,
    alarm_l_limit = 10.0,
    alarm_ll_limit = 5.0,
    
    -- Configuration
    alarm_enabled = TRUE,
    alarm_priority = 4,  -- Urgent
    alarm_deadband = 2.0,
    
    -- Equipment context
    trip_category = 'SAFETY_TRIP',
    equipment_criticality = 4,
    associated_equipment = 'TURBINE_01'
WHERE tag_id IN ('Random.Real4', 'Random.Int4');

-- Verify configuration
SELECT 
    tag_id, 
    alarm_hh_limit, alarm_h_limit, alarm_l_limit, alarm_ll_limit,
    alarm_priority, alarm_enabled, trip_category
FROM historian_meta.tag_master
WHERE alarm_enabled = true;
```

**Deliverables**:
- ✅ 4 SQL scripts for threshold configuration
- ✅ Verification queries to check setup

**Effort**: 4 hours  
**Dependencies**: OPERATIONAL_HARDENING.sql deployed

---

## Phase 2: Alarm Generation Service (C# Backend)

### 2.1 Service Design

**Purpose**: Monitor real-time tag values and generate alarms when thresholds crossed

**File**: `Services/AlarmGeneration/AlarmGenerationService.cs`

**Key Features**:
- Subscribe to `OpcDaService.TagValuesUpdated` event
- Maintain in-memory cache of alarm thresholds (from `tag_master`)
- Compare incoming values against thresholds
- Insert alarm events into `historian_events` table
- Implement deadband logic (prevent alarm oscillation)
- Support alarm states: ACTIVE → ACKNOWLEDGED → CLEARED

**Algorithm**:
```
FOR EACH tag value update:
    1. Get alarm config from cache (tag_master)
    2. IF alarm_enabled = false → SKIP
    3. Compare value vs thresholds:
       IF value > alarm_hh_limit → Generate ALARM_HIGH_HIGH (Priority 5)
       IF value > alarm_h_limit  → Generate ALARM_HIGH (Priority 4)
       IF value < alarm_ll_limit → Generate ALARM_LOW_LOW (Priority 5)
       IF value < alarm_l_limit  → Generate ALARM_LOW (Priority 4)
    4. Check deadband (prevent duplicate alarms within 5 min)
    5. Insert into historian_events table
    6. Broadcast via SignalR hub (for real-time UI)
```

### 2.2 Implementation Structure

**New Files**:
```
Services/
├── AlarmGeneration/
│   ├── AlarmGenerationService.cs         (Main service)
│   ├── AlarmThresholdCache.cs            (In-memory cache of tag_master)
│   ├── AlarmDeduplicationCache.cs        (5-min window tracking)
│   ├── Models/
│   │   ├── AlarmConfiguration.cs         (Tag alarm config)
│   │   ├── AlarmEvent.cs                 (Alarm event data)
│   │   └── AlarmState.cs                 (ACTIVE/ACKNOWLEDGED/CLEARED)
│   └── Interfaces/
│       └── IAlarmGenerationService.cs
```

**Integration Points**:
- **Register in Program.cs**:
  ```csharp
  builder.Services.AddSingleton<AlarmGenerationService>();
  builder.Services.AddHostedService(p => p.GetRequiredService<AlarmGenerationService>());
  ```
- **Subscribe to OPC events**: Wire into existing `OpcDaService.TagValuesUpdated`
- **Database writes**: Use Npgsql to insert into `historian_events`
- **SignalR broadcast**: Notify connected clients of new alarms

### 2.3 Pseudo-Code

```csharp
public class AlarmGenerationService : BackgroundService
{
    private readonly OpcDaService _opcService;
    private readonly IDbConnection _dbConnection;
    private readonly AlarmThresholdCache _thresholdCache;
    private readonly AlarmDeduplicationCache _deduplicationCache;
    private readonly IHubContext<AlarmHub> _hubContext;

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        // Load alarm configurations from tag_master
        await _thresholdCache.LoadFromDatabase();
        
        // Subscribe to tag updates
        _opcService.TagValuesUpdated += OnTagValuesUpdated;
        
        // Refresh cache every 5 minutes
        using var timer = new PeriodicTimer(TimeSpan.FromMinutes(5));
        while (await timer.WaitForNextTickAsync(stoppingToken))
        {
            await _thresholdCache.Refresh();
        }
    }

    private async Task OnTagValuesUpdated(object sender, TagValuesEventArgs e)
    {
        foreach (var tagValue in e.TagValues)
        {
            var alarmConfig = _thresholdCache.GetConfig(tagValue.TagId);
            
            if (alarmConfig == null || !alarmConfig.AlarmEnabled)
                continue;

            // Check for threshold violations
            var alarms = CheckThresholds(tagValue, alarmConfig);
            
            foreach (var alarm in alarms)
            {
                // Deduplication: Skip if alarm raised recently
                if (_deduplicationCache.WasRecentlyRaised(alarm))
                    continue;
                
                // Insert alarm event
                await InsertAlarmEvent(alarm);
                
                // Broadcast to UI
                await _hubContext.Clients.All.SendAsync("AlarmRaised", alarm);
                
                // Track for deduplication
                _deduplicationCache.Track(alarm);
            }
        }
    }

    private List<AlarmEvent> CheckThresholds(TagValue value, AlarmConfiguration config)
    {
        var alarms = new List<AlarmEvent>();
        double currentValue = value.ValueNum ?? 0;
        
        // High-High alarm (Critical)
        if (config.AlarmHhLimit.HasValue && currentValue > config.AlarmHhLimit.Value)
        {
            alarms.Add(new AlarmEvent
            {
                TagId = value.TagId,
                EventType = "ALARM_HIGH_HIGH",
                Severity = 5,
                Message = $"Value {currentValue:F2} exceeded HIGH-HIGH limit {config.AlarmHhLimit:F2}",
                AlarmState = "ACTIVE",
                AlarmPriority = 5,
                AlarmSetpoint = config.AlarmHhLimit.Value,
                AlarmActualValue = currentValue
            });
        }
        
        // High alarm (Urgent)
        else if (config.AlarmHLimit.HasValue && currentValue > config.AlarmHLimit.Value)
        {
            alarms.Add(new AlarmEvent
            {
                TagId = value.TagId,
                EventType = "ALARM_HIGH",
                Severity = 4,
                Message = $"Value {currentValue:F2} exceeded HIGH limit {config.AlarmHLimit:F2}",
                AlarmState = "ACTIVE",
                AlarmPriority = 4,
                AlarmSetpoint = config.AlarmHLimit.Value,
                AlarmActualValue = currentValue
            });
        }
        
        // Low alarm (Medium)
        else if (config.AlarmLLimit.HasValue && currentValue < config.AlarmLLimit.Value)
        {
            alarms.Add(new AlarmEvent
            {
                TagId = value.TagId,
                EventType = "ALARM_LOW",
                Severity = 3,
                Message = $"Value {currentValue:F2} below LOW limit {config.AlarmLLimit:F2}",
                AlarmState = "ACTIVE",
                AlarmPriority = 3,
                AlarmSetpoint = config.AlarmLLimit.Value,
                AlarmActualValue = currentValue
            });
        }
        
        // Low-Low alarm (Critical)
        else if (config.AlarmLlLimit.HasValue && currentValue < config.AlarmLlLimit.Value)
        {
            alarms.Add(new AlarmEvent
            {
                TagId = value.TagId,
                EventType = "ALARM_LOW_LOW",
                Severity = 5,
                Message = $"Value {currentValue:F2} below LOW-LOW limit {config.AlarmLlLimit:F2}",
                AlarmState = "ACTIVE",
                AlarmPriority = 5,
                AlarmSetpoint = config.AlarmLlLimit.Value,
                AlarmActualValue = currentValue
            });
        }
        
        return alarms;
    }

    private async Task InsertAlarmEvent(AlarmEvent alarm)
    {
        await _dbConnection.ExecuteAsync(@"
            INSERT INTO historian_raw.historian_events 
                (time, tag_id, event_type, severity, message, 
                 alarm_state, alarm_priority, alarm_setpoint, alarm_actual_value)
            VALUES 
                (now(), @TagId, @EventType, @Severity, @Message,
                 @AlarmState, @AlarmPriority, @AlarmSetpoint, @AlarmActualValue)
        ", alarm);
    }
}
```

**Deliverables**:
- ✅ AlarmGenerationService.cs (500+ lines)
- ✅ AlarmThresholdCache.cs (200 lines)
- ✅ AlarmDeduplicationCache.cs (150 lines)
- ✅ Model classes (100 lines)
- ✅ Unit tests (300 lines)

**Effort**: 40-60 hours (1 week)  
**Dependencies**: Phase 1 complete

---

## Phase 3: Trip Detection Service (C# Backend)

### 3.1 Service Design

**Purpose**: Detect trip events by correlating active alarms with equipment state changes

**File**: `Services/TripDetection/TripDetectionService.cs`

**Key Features**:
- Monitor equipment RUN status tags (e.g., TURBINE_RUN_STATUS)
- Track equipment state transitions (RUNNING → STOPPED)
- Correlate recent alarms (within 2-second window before stop)
- Determine trip category based on alarm priority
- Insert trip events into `trip_event_tracking` table

**Algorithm**:
```
FOR EACH equipment status update:
    IF (Equipment transitions from RUNNING → STOPPED):
        1. Query active alarms in last 2 seconds for this equipment
        2. IF alarms exist:
            - SELECT highest priority alarm
            - INSERT into trip_event_tracking:
                - trip_time = stop time
                - initiating_alarm_id = alarm event_id
                - trip_category = based on alarm priority
                  (Priority 5 → EMERGENCY_TRIP)
                  (Priority 4 → SAFETY_TRIP)
                  (Priority 3 → PROCESS_TRIP)
            - UPDATE alarm event with trip linkage
        3. ELSE:
            - LOG: Normal operator shutdown (no trip)
```

### 3.2 Implementation Structure

**New Files**:
```
Services/
├── TripDetection/
│   ├── TripDetectionService.cs           (Main service)
│   ├── EquipmentStateTracker.cs          (Track RUN/STOP states)
│   ├── AlarmTripCorrelator.cs            (Link alarms to trips)
│   ├── Models/
│   │   ├── EquipmentState.cs             (Equipment operational state)
│   │   ├── TripEvent.cs                  (Trip event data)
│   │   └── TripConfiguration.cs          (Equipment mappings)
│   └── Interfaces/
│       └── ITripDetectionService.cs
```

**Configuration** (appsettings.json):
```json
{
  "TripDetection": {
    "CorrelationWindowSeconds": 2,
    "EquipmentMappings": [
      {
        "EquipmentId": "TURBINE_01",
        "RunStatusTagId": "TURBINE_01_RUN_STATUS",
        "TripTagId": "TURBINE_01_TRIP_STATUS",
        "RatedCapacityMW": 270.0,
        "MonitoredAlarmTags": [
          "TURBINE_01_BEARING_TEMP",
          "TURBINE_01_VIBRATION",
          "TURBINE_01_LUBE_OIL_PRESSURE"
        ]
      }
    ]
  }
}
```

### 3.3 Pseudo-Code

```csharp
public class TripDetectionService : BackgroundService
{
    private readonly OpcDaService _opcService;
    private readonly IDbConnection _dbConnection;
    private readonly EquipmentStateTracker _stateTracker;
    private readonly IConfiguration _config;

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _opcService.TagValuesUpdated += OnTagValuesUpdated;
        
        while (!stoppingToken.IsCancellationRequested)
        {
            await Task.Delay(100, stoppingToken);  // 100ms scan rate
        }
    }

    private async Task OnTagValuesUpdated(object sender, TagValuesEventArgs e)
    {
        foreach (var tagValue in e.TagValues)
        {
            var equipment = GetEquipmentForTag(tagValue.TagId);
            if (equipment == null) continue;

            // Update equipment state
            bool wasRunning = _stateTracker.IsRunning(equipment.EquipmentId);
            bool isRunning = tagValue.ValueNum > 0.5;  // RUN=1, STOP=0
            
            _stateTracker.UpdateState(equipment.EquipmentId, isRunning);

            // Detect transition: RUNNING → STOPPED
            if (wasRunning && !isRunning)
            {
                await HandleEquipmentStop(equipment, DateTime.UtcNow);
            }
        }
    }

    private async Task HandleEquipmentStop(EquipmentConfiguration equipment, DateTime stopTime)
    {
        // Query recent alarms (2-second window)
        var recentAlarms = await _dbConnection.QueryAsync<AlarmRecord>(@"
            SELECT event_id, tag_id, event_type, alarm_priority, time
            FROM historian_raw.historian_events
            WHERE alarm_state = 'ACTIVE'
              AND time >= @StartTime
              AND tag_id = ANY(@MonitoredTags)
            ORDER BY alarm_priority DESC, time DESC
        ", new {
            StartTime = stopTime.AddSeconds(-2),
            MonitoredTags = equipment.MonitoredAlarmTags
        });

        if (recentAlarms.Any())
        {
            // TRIP DETECTED
            var initiatingAlarm = recentAlarms.First();
            
            var tripCategory = DetermineTripCategory(initiatingAlarm.AlarmPriority);
            
            await InsertTripEvent(new TripEvent
            {
                TripTime = stopTime,
                TripTagId = equipment.TripTagId,
                TripCategory = tripCategory,
                EquipmentAffected = equipment.EquipmentId,
                InitiatingAlarmId = initiatingAlarm.EventId,
                RootCauseTagId = initiatingAlarm.TagId,
                ProductionLossMw = equipment.RatedCapacityMW
            });
            
            _logger.LogWarning(
                "TRIP DETECTED: {Equipment} stopped due to {Alarm} (Priority {Priority})",
                equipment.EquipmentId, 
                initiatingAlarm.EventType, 
                initiatingAlarm.AlarmPriority
            );
        }
        else
        {
            // Normal shutdown
            _logger.LogInformation(
                "Normal shutdown: {Equipment} stopped (no active alarms)",
                equipment.EquipmentId
            );
        }
    }

    private string DetermineTripCategory(int alarmPriority)
    {
        return alarmPriority switch
        {
            5 => "EMERGENCY_TRIP",
            >= 4 => "SAFETY_TRIP",
            _ => "PROCESS_TRIP"
        };
    }

    private async Task InsertTripEvent(TripEvent tripEvent)
    {
        await _dbConnection.ExecuteAsync(@"
            INSERT INTO historian_raw.trip_event_tracking 
                (trip_time, trip_tag_id, trip_category, equipment_affected,
                 initiating_alarm_id, root_cause_tag_id, production_loss_mw)
            VALUES 
                (@TripTime, @TripTagId, @TripCategory, @EquipmentAffected,
                 @InitiatingAlarmId, @RootCauseTagId, @ProductionLossMw)
        ", tripEvent);
    }
}
```

**Deliverables**:
- ✅ TripDetectionService.cs (400+ lines)
- ✅ EquipmentStateTracker.cs (200 lines)
- ✅ AlarmTripCorrelator.cs (150 lines)
- ✅ Configuration models (100 lines)
- ✅ Unit tests (250 lines)

**Effort**: 30-40 hours (5-6 days)  
**Dependencies**: Phase 2 complete

---

## Phase 4: Web UI Dashboard (Frontend)

### 4.1 UI Design

**Purpose**: Provide operators with real-time alarm monitoring and trip analysis interface

**Pages**:
1. **Active Alarms Dashboard** (`/alarms/active`)
2. **Alarm History** (`/alarms/history`)
3. **Trip History** (`/trips/history`)
4. **Trip Causality Viewer** (`/trips/{id}/causality`)
5. **Alarm Configuration** (`/admin/alarms/config`)

### 4.2 Active Alarms Dashboard

**Layout**:
```
┌─────────────────────────────────────────────────────────────┐
│  Active Alarms Dashboard              Last Update: 14:35:22  │
├─────────────────────────────────────────────────────────────┤
│  Summary:  🔴 Critical: 2  🟠 Urgent: 5  🟡 Medium: 12      │
├─────────────────────────────────────────────────────────────┤
│ Priority │ Tag ID          │ Value  │ Limit  │ Duration │ Action │
├──────────┼─────────────────┼────────┼────────┼──────────┼────────┤
│    🔴 5  │ Random.Real4    │ 105.2  │ 100.0  │ 2m 15s   │ [ACK]  │
│    🔴 5  │ Random.Int4     │  -850  │ -800   │ 5m 42s   │ [ACK]  │
│    🟠 4  │ Random.UInt2    │  990   │  900   │ 12m 05s  │ [ACK]  │
│    🟡 3  │ Random.Real8    │  15.2  │  20.0  │ 45m 12s  │ [ACK]  │
└─────────────────────────────────────────────────────────────┘
```

**Features**:
- ✅ Auto-refresh every 5 seconds
- ✅ Color-coded by priority (Red=5, Orange=4, Yellow=3)
- ✅ Real-time updates via SignalR
- ✅ One-click acknowledgment
- ✅ Alarm sound notification (browser audio)
- ✅ Export to CSV

### 4.3 Trip History View

**Layout**:
```
┌─────────────────────────────────────────────────────────────────┐
│  Trip History - Last 7 Days                      Filters: [All] │
├─────────────────────────────────────────────────────────────────┤
│ Trip Time        │ Equipment   │ Category      │ Initiating Alarm  │ Duration │
├──────────────────┼─────────────┼───────────────┼───────────────────┼──────────┤
│ 2025-12-22 14:30 │ TURBINE_01  │ SAFETY_TRIP   │ ALARM_HIGH_TEMP   │ 45 min   │
│ 2025-12-22 09:15 │ BOILER_A    │ PROCESS_TRIP  │ ALARM_LOW_PRESS   │ 2h 15m   │
│ 2025-12-21 18:45 │ TURBINE_01  │ EMERGENCY_TRIP│ ALARM_VIBRATION   │ 3h 30m   │
└─────────────────────────────────────────────────────────────────┘
```

**Features**:
- ✅ Click trip row → Show causality timeline
- ✅ Filter by equipment, category, date range
- ✅ MTBF/MTTR calculations
- ✅ Export trip reports

### 4.4 Trip Causality Timeline

**Visual**:
```
Trip Event: TURBINE_01 SAFETY_TRIP - 2025-12-22 14:30:22

Timeline (5-second window):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
14:30:19          14:30:20          14:30:21          14:30:22
    │                 │                 │                 │
    │                 │                 │                 ▼
    │                 │                 │            🛑 TURBINE STOPPED
    │                 │                 │
    │                 │                 ▼
    │                 │            🔥 ALARM_HIGH_HIGH_BEARING_TEMP
    │                 │               Value: 105.2°C (Limit: 100.0°C)
    │                 │
    │                 ▼
    │            🟠 ALARM_HIGH_VIBRATION
    │               Value: 8.5 mm/s (Limit: 7.0 mm/s)
    │
    ▼
 ⚠️  ALARM_LOW_LUBE_OIL_PRESSURE
    Value: 12 PSI (Limit: 15 PSI)

Root Cause Analysis:
✓ Initiating Alarm: ALARM_HIGH_HIGH_BEARING_TEMP (Priority 5)
✓ Contributing Factors: Low lube oil pressure, High vibration
✓ Production Loss: 270 MW × 45 min = 202.5 MWh
```

### 4.5 REST API Endpoints

**File**: `Controllers/AlarmController.cs`
```csharp
[ApiController]
[Route("api/alarms")]
public class AlarmController : ControllerBase
{
    // GET /api/alarms/active
    [HttpGet("active")]
    public async Task<ActionResult<List<AlarmDto>>> GetActiveAlarms()
    
    // GET /api/alarms/history?from=2025-12-20&to=2025-12-22
    [HttpGet("history")]
    public async Task<ActionResult<List<AlarmDto>>> GetAlarmHistory(DateTime from, DateTime to)
    
    // POST /api/alarms/{id}/acknowledge
    [HttpPost("{id}/acknowledge")]
    public async Task<IActionResult> AcknowledgeAlarm(long id, [FromBody] AcknowledgeRequest request)
    
    // GET /api/alarms/stats
    [HttpGet("stats")]
    public async Task<ActionResult<AlarmStatistics>> GetAlarmStatistics()
}
```

**File**: `Controllers/TripController.cs`
```csharp
[ApiController]
[Route("api/trips")]
public class TripController : ControllerBase
{
    // GET /api/trips/recent?days=7
    [HttpGet("recent")]
    public async Task<ActionResult<List<TripDto>>> GetRecentTrips(int days = 7)
    
    // GET /api/trips/{id}/causality
    [HttpGet("{id}/causality")]
    public async Task<ActionResult<TripCausalityDto>> GetTripCausality(long id)
    
    // GET /api/trips/stats
    [HttpGet("stats")]
    public async Task<ActionResult<TripStatistics>> GetTripStatistics()
}
```

**File**: `Hubs/AlarmHub.cs`
```csharp
public class AlarmHub : Hub
{
    // Real-time alarm notifications
    public async Task SubscribeToAlarms()
    public async Task UnsubscribeFromAlarms()
    
    // Broadcast methods (called by AlarmGenerationService)
    public async Task AlarmRaised(AlarmDto alarm)
    public async Task AlarmAcknowledged(long alarmId, string acknowledgedBy)
    public async Task AlarmCleared(long alarmId)
}
```

### 4.6 Frontend Structure

**Technology**: Vanilla JavaScript + HTML/CSS (or React if preferred)

**Files**:
```
wwwroot/
├── alarms/
│   ├── active.html                 (Active alarms dashboard)
│   ├── history.html                (Alarm history viewer)
│   ├── js/
│   │   ├── alarm-dashboard.js      (Real-time updates)
│   │   ├── alarm-acknowledgment.js (ACK handling)
│   │   └── signalr-client.js       (WebSocket connection)
│   └── css/
│       └── alarm-dashboard.css     (Styling)
├── trips/
│   ├── history.html                (Trip history)
│   ├── causality.html              (Causality timeline)
│   └── js/
│       └── trip-viewer.js
└── shared/
    └── alarm-sound.mp3             (Alarm notification sound)
```

**Deliverables**:
- ✅ Active Alarms Dashboard (HTML + JS + CSS)
- ✅ Alarm History Viewer
- ✅ Trip History Viewer
- ✅ Trip Causality Timeline
- ✅ REST API Controllers (2 files, 400 lines)
- ✅ SignalR Hub (150 lines)
- ✅ Frontend JavaScript (800 lines)

**Effort**: 40-50 hours (1 week)  
**Dependencies**: Phase 3 complete

---

## Phase 5: Testing & Validation

### 5.1 Unit Tests

**Test Coverage**:
- AlarmGenerationService threshold detection logic
- AlarmDeduplicationCache window tracking
- TripDetectionService correlation logic
- AlarmThresholdCache refresh mechanism

**Framework**: xUnit + Moq

**Effort**: 20 hours

### 5.2 Integration Tests

**Scenarios**:
1. **Alarm Generation**: Simulate OPC tag update → Verify alarm inserted in DB
2. **Trip Detection**: Simulate alarm + equipment stop → Verify trip recorded
3. **Alarm Acknowledgment**: POST /api/alarms/{id}/acknowledge → Verify state change
4. **SignalR Broadcast**: Raise alarm → Verify WebSocket notification

**Effort**: 16 hours

### 5.3 End-to-End Tests

**Test Cases**:
1. Configure alarm thresholds → Generate test signals → Verify alarms appear in UI
2. Simulate equipment trip scenario → Verify causality analysis correct
3. Stress test: 100 alarms/sec → Verify no duplicates, UI responsive
4. Alarm acknowledgment workflow → Verify operator notes saved

**Effort**: 24 hours

---

## Implementation Timeline

```
Week 1 (Dec 23-27):
├─ Day 1-2: Phase 1 - SQL scripts, threshold configuration
├─ Day 3-5: Phase 2 - AlarmGenerationService (start)
└─ Day 5: Review & testing

Week 2 (Dec 30-Jan 3):
├─ Day 1-3: Phase 2 - AlarmGenerationService (complete)
├─ Day 4-5: Phase 3 - TripDetectionService (start)
└─ Day 5: Integration testing

Week 3 (Jan 6-10):
├─ Day 1-2: Phase 3 - TripDetectionService (complete)
├─ Day 3-5: Phase 4 - Web UI (start)
└─ Day 5: UI prototype demo

Week 4 (Jan 13-17):
├─ Day 1-2: Phase 4 - Web UI (complete)
├─ Day 3-4: Phase 5 - Testing & bug fixes
└─ Day 5: Deployment & documentation
```

**Total Effort**: 160-200 hours (4 weeks, 1 developer)

---

## Deployment Checklist

### Database
- [ ] Run OPERATIONAL_HARDENING.sql on production database
- [ ] Execute Phase 1 SQL scripts (threshold analysis)
- [ ] Verify alarm columns populated in tag_master
- [ ] Create database indices for performance
- [ ] Configure PostgreSQL NOTIFY triggers

### Application
- [ ] Build C# services (AlarmGenerationService, TripDetectionService)
- [ ] Register services in Program.cs
- [ ] Configure appsettings.json (equipment mappings)
- [ ] Deploy SignalR hubs
- [ ] Test OPC event subscriptions

### Frontend
- [ ] Deploy UI files to wwwroot/
- [ ] Configure SignalR client connection
- [ ] Test alarm acknowledgment workflow
- [ ] Enable alarm sound notifications
- [ ] Set up auto-refresh timers

### Monitoring
- [ ] Enable service health checks
- [ ] Configure logging (Serilog → PostgreSQL)
- [ ] Set up performance metrics (Prometheus/Grafana)
- [ ] Create operator training documentation

---

## Success Criteria

### Functional
- ✅ Alarms generated within 1 second of threshold breach
- ✅ Zero duplicate alarms (deduplication working)
- ✅ Trip events recorded with correct causality linkage
- ✅ UI updates in real-time (<2 second latency)
- ✅ Alarm acknowledgment persists in database

### Performance
- ✅ Handle 1000 tag updates/second without delay
- ✅ Alarm generation latency <100ms
- ✅ Trip detection latency <500ms
- ✅ UI responsive with 100+ active alarms

### Reliability
- ✅ Service restarts without losing alarm state
- ✅ Database connection resilience (auto-reconnect)
- ✅ No alarm events lost during high load

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Alarm flood (100+ alarms/sec) | System overload | Implement rate limiting, deadband logic |
| False positive trips | Operator trust loss | Tune correlation window (2s → 5s), manual review |
| Database performance degradation | Slow UI | Add indexes, partitioning, retention cleanup |
| SignalR connection drops | Lost real-time updates | Auto-reconnect logic, fallback to polling |
| Threshold misconfiguration | Wrong alarms | Add threshold validation, admin approval workflow |

---

## Future Enhancements (Phase 6+)

### Short-term (1-2 months)
- Machine Learning trip prediction (analyze patterns before trip)
- SMS/Email alarm notifications
- Mobile app for alarm acknowledgment
- Advanced analytics (MTBF, MTTR, downtime attribution)

### Long-term (3-6 months)
- Predictive maintenance (detect degradation trends)
- Root cause analysis AI (suggest probable causes)
- Integration with CMMS (Maximo, SAP PM)
- Regulatory compliance reports (NERC, FERC)

---

## Questions & Decisions Needed

1. **Which signals should have alarms configured first?**
   - Suggest: Random.Real4, Random.Int4, Random.UInt2 for testing
   - Then: Critical equipment tags (turbine temp, bearing vibration, etc.)

2. **Auto-calculated thresholds or manual configuration?**
   - Auto: Fast setup, may need tuning
   - Manual: Accurate, requires engineering input

3. **Alarm priority assignment strategy?**
   - Option A: Based on observed value range (>15% deviation = High priority)
   - Option B: Manual assignment per tag criticality

4. **UI framework preference?**
   - Vanilla JavaScript (simple, no dependencies)
   - React (modern, component-based)
   - Blazor (C# full-stack)

5. **Deployment timeline?**
   - Aggressive: 2 weeks (minimum viable product)
   - Standard: 4 weeks (full feature set)
   - Conservative: 6 weeks (extensive testing)

---

## Next Steps

**Immediate Actions**:
1. Review this plan and approve scope
2. Answer Questions & Decisions section
3. Set up development environment (if needed)
4. Begin Phase 1: Run SQL analysis scripts

**This Week**:
- Execute `scripts/01_analyze_signal_ranges.sql`
- Review suggested thresholds
- Configure alarms for 3-5 test signals
- Verify data in tag_master table

**Contact**: Ready to begin implementation upon approval.

---

**Document Version**: 1.0  
**Last Updated**: December 22, 2025  
**Status**: Pending Approval
