# OPERATIONAL HARDENING - PART 2: APPLICATION LOGIC GUIDE

## Document Overview
**Purpose**: Implementation guide for C# application services (intelligence layer)  
**Version**: 1.0  
**Date**: December 22, 2025  
**Status**: Implementation Roadmap  
**Prerequisites**: PART 1 - Database Foundation (deployed)

---

## Table of Contents
1. [Architecture Philosophy](#architecture-philosophy)
2. [Application Responsibilities](#application-responsibilities)
3. [Trip Detection Engine](#trip-detection-engine)
4. [Alarm-Trip Correlation Service](#alarm-trip-correlation-service)
5. [Interlock-Trip Correlation Service](#interlock-trip-correlation-service)
6. [State Detection Service](#state-detection-service)
7. [Alarm Deduplication Service](#alarm-deduplication-service)
8. [Dynamic Priority Calculation](#dynamic-priority-calculation)
9. [Event Logging & Rate Limiting](#event-logging--rate-limiting)
10. [Authentication & Authorization](#authentication--authorization)
11. [Testing & Validation](#testing--validation)

---

## 1. Architecture Philosophy

### Division of Responsibilities

**Database (Historian Foundation)** ✅ COMPLETE:
- Storage structure (tables, constraints, indexes)
- Data integrity (FK relationships, unique constraints)
- Retention enforcement (cleanup functions)
- Causality storage (initiating_alarm_id, root_cause_tag_id links)

**Application (Intelligence Layer)** ⏸️ TO IMPLEMENT:
- Trip detection (alarm + equipment state → trip inference)
- Alarm-trip correlation (populate causality links)
- Interlock-trip correlation (timing + bypass evaluation)
- State machine logic (RUNNING/STOPPED/TRIPPED inference)
- Alarm deduplication (5-min window check)
- Dynamic priority (severity + context)

### Why This Division?

**Industry Standard**: OSIsoft PI, Aspen IP.21, Honeywell PHD all follow this pattern:
1. **Database**: Store events correctly (time, tag, value, quality)
2. **Application**: Infer causality (which alarm caused which trip)
3. **Analytics**: Compute metrics (MTBF, downtime attribution)

**Plant-Specific Logic**: Trip detection varies by:
- PLC vendor (Siemens vs Allen-Bradley vs Schneider)
- Equipment type (turbine vs compressor vs pump)
- Process design (cascade trips vs independent trips)

**Database can't know**: "Alarm X + Motor RUN → Motor STOP within 2 seconds = Trip caused by Alarm X"

**Application MUST implement**: Control logic, time-window evaluation, false positive rejection

---

## 2. Application Responsibilities

### 2.1 Core Services (Required)

| Service | Purpose | Complexity | Est. Hours |
|---------|---------|------------|------------|
| TripDetectionService | Watch alarms + equipment states, detect trips | High | 20-40 |
| AlarmTripCorrelationService | Populate `initiating_alarm_id`, `root_cause_tag_id` | Medium | 10-20 |
| InterlockTripCorrelationService | Link interlocks to trips, check bypass status | Medium | 10-20 |
| AlarmDeduplicationService | Prevent duplicate alarms (5-min window) | Low | 8-12 |
| StateDetectionService | Infer equipment state (RUNNING/STOPPED/TRIPPED) | High | 40-80 |
| DynamicPriorityService | Calculate priority (severity + context + time) | Low | 8-12 |
| EventLoggingService | Rate-limited event insertion | Low | 4-8 |

**Total Estimated Effort**: 100-200 hours (2-4 weeks with 2-person team)

### 2.2 Data Flow (Application Layer)

```
OPC DA Tags → OpcDaService.TagValuesUpdated event
    ↓
[TripDetectionService]
    ├─→ Watches: Alarm states (ACTIVE/CLEARED)
    ├─→ Watches: Equipment run status (RUN=1, STOP=0)
    ├─→ Logic: Alarm ACTIVE → Motor STOP within 2s → Trip detected
    └─→ Action: Insert into trip_event_tracking
         ↓
[AlarmTripCorrelationService]
    ├─→ Query: Recent alarms (5-second window before trip)
    ├─→ Logic: Highest priority alarm = likely cause
    └─→ Action: UPDATE trip_event_tracking SET initiating_alarm_id = X
         ↓
[InterlockTripCorrelationService]
    ├─→ Query: Interlock violations (5-second window before trip)
    ├─→ Logic: Check if bypass was active
    └─→ Action: UPDATE trip_event_tracking SET related_trip_event_id = Y
         ↓
[StateDetectionService]
    ├─→ Infers: RUNNING, STOPPED, TRIPPED, STARTING, SHUTTING_DOWN
    ├─→ Logic: Multi-tag pattern recognition (load, speed, status)
    └─→ Action: INSERT into equipment_state_history (new table)
```

---

## 3. Trip Detection Engine

### 3.1 Design Overview

**Purpose**: Detect trip events by correlating alarm states with equipment state changes

**Challenge**: How to distinguish:
- **Normal shutdown** (operator stops equipment)
- **Trip** (alarm forces equipment to stop)

**Solution**: Time-window correlation
```
IF (Alarm becomes ACTIVE)
   AND (Equipment was RUNNING)
   AND (Equipment becomes STOPPED within 2 seconds)
THEN Trip detected (alarm caused stop)

IF (Equipment stops)
   AND (No active alarms in last 5 seconds)
THEN Normal shutdown (operator action)
```

### 3.2 Implementation (C# Pseudocode)

```csharp
public class TripDetectionService : BackgroundService
{
    private readonly OpcDaService _opcService;
    private readonly IDbConnection _dbConnection;
    
    // In-memory alarm state tracking
    private ConcurrentDictionary<string, AlarmState> _activeAlarms = new();
    
    // In-memory equipment state tracking
    private ConcurrentDictionary<string, EquipmentState> _equipmentStates = new();
    
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        // Subscribe to OPC tag updates
        _opcService.TagValuesUpdated += OnTagValuesUpdated;
        
        while (!stoppingToken.IsCancellationRequested)
        {
            await Task.Delay(100, stoppingToken);  // 100ms scan rate
        }
    }
    
    private async Task OnTagValuesUpdated(object sender, TagValuesEventArgs e)
    {
        foreach (var tagUpdate in e.TagValues)
        {
            // Check if this is an alarm tag
            if (IsAlarmTag(tagUpdate.TagId))
            {
                await ProcessAlarmUpdate(tagUpdate);
            }
            
            // Check if this is an equipment run status tag
            if (IsEquipmentRunStatusTag(tagUpdate.TagId))
            {
                await ProcessEquipmentStatusUpdate(tagUpdate);
            }
        }
    }
    
    private async Task ProcessAlarmUpdate(TagValue tagUpdate)
    {
        bool isAlarmActive = tagUpdate.ValueBool ?? false;
        string alarmTagId = tagUpdate.TagId;
        
        if (isAlarmActive && !_activeAlarms.ContainsKey(alarmTagId))
        {
            // Alarm just became ACTIVE
            var alarmState = new AlarmState
            {
                TagId = alarmTagId,
                ActivatedAt = DateTime.UtcNow,
                Priority = await GetAlarmPriority(alarmTagId),
                EquipmentAffected = await GetAffectedEquipment(alarmTagId)
            };
            
            _activeAlarms[alarmTagId] = alarmState;
            
            // Check if equipment stopped recently (within 2 seconds)
            await CheckForRecentTrip(alarmState);
        }
        else if (!isAlarmActive && _activeAlarms.ContainsKey(alarmTagId))
        {
            // Alarm cleared
            _activeAlarms.TryRemove(alarmTagId, out _);
        }
    }
    
    private async Task ProcessEquipmentStatusUpdate(TagValue tagUpdate)
    {
        bool isRunning = tagUpdate.ValueNum > 0.5;  // RUN=1, STOP=0
        string equipmentId = GetEquipmentIdFromTag(tagUpdate.TagId);
        
        var currentState = _equipmentStates.GetOrAdd(equipmentId, 
            new EquipmentState { EquipmentId = equipmentId });
        
        if (currentState.IsRunning && !isRunning)
        {
            // Equipment just STOPPED
            currentState.IsRunning = false;
            currentState.StoppedAt = DateTime.UtcNow;
            
            // Check if any alarms became active recently (within 2 seconds)
            await CheckForTripCausedByAlarm(equipmentId, currentState.StoppedAt);
        }
        else if (!currentState.IsRunning && isRunning)
        {
            // Equipment just STARTED
            currentState.IsRunning = true;
            currentState.StartedAt = DateTime.UtcNow;
        }
    }
    
    private async Task CheckForTripCausedByAlarm(string equipmentId, DateTime stopTime)
    {
        // Find alarms that became active in the last 2 seconds
        var recentAlarms = _activeAlarms.Values
            .Where(a => a.EquipmentAffected == equipmentId)
            .Where(a => (stopTime - a.ActivatedAt).TotalSeconds <= 2)
            .OrderByDescending(a => a.Priority)
            .ToList();
        
        if (recentAlarms.Any())
        {
            // TRIP DETECTED: Alarm caused equipment to stop
            var initiatingAlarm = recentAlarms.First();  // Highest priority
            
            await RecordTripEvent(
                tripTime: stopTime,
                tripTagId: GetTripTagId(equipmentId),
                tripCategory: DetermineTripCategory(initiatingAlarm.Priority),
                equipmentAffected: equipmentId,
                initiatingAlarmId: initiatingAlarm.AlarmEventId,
                rootCauseTagId: initiatingAlarm.TagId
            );
            
            _logger.LogWarning(
                "TRIP DETECTED: {Equipment} stopped due to {Alarm} (priority {Priority})",
                equipmentId, initiatingAlarm.TagId, initiatingAlarm.Priority
            );
        }
        else
        {
            // No recent alarms: Normal operator shutdown
            _logger.LogInformation(
                "Normal shutdown: {Equipment} stopped (no active alarms)",
                equipmentId
            );
        }
    }
    
    private async Task RecordTripEvent(
        DateTime tripTime,
        string tripTagId,
        string tripCategory,
        string equipmentAffected,
        long? initiatingAlarmId,
        string rootCauseTagId)
    {
        await _dbConnection.ExecuteAsync(@"
            INSERT INTO historian_raw.trip_event_tracking 
                (trip_time, trip_tag_id, trip_category, equipment_affected, 
                 initiating_alarm_id, root_cause_tag_id, production_loss_mw)
            VALUES 
                (@tripTime, @tripTagId, @tripCategory, @equipmentAffected,
                 @initiatingAlarmId, @rootCauseTagId, @productionLossMw)
        ", new {
            tripTime,
            tripTagId,
            tripCategory,
            equipmentAffected,
            initiatingAlarmId,
            rootCauseTagId,
            productionLossMw = CalculateProductionLoss(equipmentAffected)
        });
    }
    
    private string DetermineTripCategory(int alarmPriority)
    {
        return alarmPriority switch
        {
            5 => "EMERGENCY_TRIP",   // Critical alarm → emergency trip
            >= 4 => "SAFETY_TRIP",   // High/urgent alarm → safety trip
            _ => "PROCESS_TRIP"      // Medium/low alarm → process trip
        };
    }
}

public class AlarmState
{
    public string TagId { get; set; }
    public DateTime ActivatedAt { get; set; }
    public int Priority { get; set; }
    public string EquipmentAffected { get; set; }
    public long? AlarmEventId { get; set; }
}

public class EquipmentState
{
    public string EquipmentId { get; set; }
    public bool IsRunning { get; set; }
    public DateTime? StartedAt { get; set; }
    public DateTime? StoppedAt { get; set; }
}
```

### 3.3 Configuration (appsettings.json)

```json
{
  "TripDetection": {
    "AlarmToTripWindowSeconds": 2,
    "EquipmentMappings": [
      {
        "EquipmentId": "TURBINE_01",
        "RunStatusTagId": "TURBINE_01_RUN_STATUS",
        "TripTagId": "TURBINE_01_TRIP_STATUS",
        "RatedCapacityMW": 270.0
      },
      {
        "EquipmentId": "BOILER_A",
        "RunStatusTagId": "BOILER_A_RUN_STATUS",
        "TripTagId": "BOILER_A_TRIP_STATUS",
        "RatedCapacityMW": 0.0
      }
    ],
    "AlarmTagPatterns": [
      "*_ALARM_*",
      "*_TRIP_*",
      "*_HIGH_HIGH",
      "*_LOW_LOW"
    ]
  }
}
```

### 3.4 Testing Strategy

```csharp
[Fact]
public async Task TripDetectionService_DetectsTrip_WhenAlarmCausesStop()
{
    // Arrange
    var service = new TripDetectionService(_opcService, _dbConnection, _config);
    await service.StartAsync(CancellationToken.None);
    
    // Act
    // 1. Equipment is running
    SimulateTagUpdate("TURBINE_01_RUN_STATUS", valueNum: 1.0);
    await Task.Delay(100);
    
    // 2. Alarm becomes active
    SimulateTagUpdate("TURBINE_01_OVERSPEED_ALARM", valueBool: true);
    await Task.Delay(500);  // 0.5 seconds
    
    // 3. Equipment stops (within 2-second window)
    SimulateTagUpdate("TURBINE_01_RUN_STATUS", valueNum: 0.0);
    await Task.Delay(500);
    
    // Assert
    var trips = await GetTripsFromDatabase("TURBINE_01");
    Assert.Single(trips);
    Assert.Equal("SAFETY_TRIP", trips[0].TripCategory);
    Assert.NotNull(trips[0].InitiatingAlarmId);
}

[Fact]
public async Task TripDetectionService_IgnoresNormalShutdown_WhenNoActiveAlarms()
{
    // Arrange
    var service = new TripDetectionService(_opcService, _dbConnection, _config);
    await service.StartAsync(CancellationToken.None);
    
    // Act
    // 1. Equipment is running
    SimulateTagUpdate("TURBINE_01_RUN_STATUS", valueNum: 1.0);
    await Task.Delay(100);
    
    // 2. Equipment stops (no active alarms)
    SimulateTagUpdate("TURBINE_01_RUN_STATUS", valueNum: 0.0);
    await Task.Delay(500);
    
    // Assert
    var trips = await GetTripsFromDatabase("TURBINE_01");
    Assert.Empty(trips);  // No trip recorded (normal shutdown)
}
```

---

## 4. Alarm-Trip Correlation Service

### 4.1 Design Overview

**Purpose**: After trip is detected, analyze recent alarm history to populate causality fields

**Fields to Populate**:
- `initiating_alarm_id`: Which alarm caused this trip (highest priority in 5-second window)
- `root_cause_tag_id`: Actual problem tag (e.g., bearing temperature sensor)

**Challenge**: Multiple alarms may be active before trip (cascade effect)

**Solution**: Priority-based correlation
```
1. Get all ACTIVE alarms in 5-second window before trip
2. Sort by priority (5=Critical, 4=Urgent, 3=High, ...)
3. Highest priority alarm = initiating_alarm_id
4. Check alarm tag's associated sensor = root_cause_tag_id
```

### 4.2 Implementation (C# Pseudocode)

```csharp
public class AlarmTripCorrelationService : BackgroundService
{
    private readonly IDbConnection _dbConnection;
    private readonly IConfiguration _config;
    
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            // Process trips with missing causality (every 10 seconds)
            await CorrelateUnlinkedTrips();
            await Task.Delay(TimeSpan.FromSeconds(10), stoppingToken);
        }
    }
    
    private async Task CorrelateUnlinkedTrips()
    {
        // Find trips without causality links
        var unlinkedTrips = await _dbConnection.QueryAsync<TripEvent>(@"
            SELECT trip_event_id, trip_time, trip_tag_id, equipment_affected
            FROM historian_raw.trip_event_tracking
            WHERE initiating_alarm_id IS NULL
              AND trip_time > now() - INTERVAL '1 hour'
            ORDER BY trip_time DESC
        ");
        
        foreach (var trip in unlinkedTrips)
        {
            await CorrelateTrip(trip);
        }
    }
    
    private async Task CorrelateTrip(TripEvent trip)
    {
        // Get alarms active in 5-second window before trip
        var correlationWindowSeconds = _config.GetValue<int>(
            "AlarmTripCorrelation:WindowSeconds", 5);
        
        var candidateAlarms = await _dbConnection.QueryAsync<AlarmEvent>(@"
            SELECT 
                event_id,
                time AS alarm_time,
                tag_id,
                alarm_priority,
                alarm_actual_value,
                message
            FROM historian_raw.historian_events
            WHERE event_type LIKE 'ALARM_%'
              AND alarm_state = 'ACTIVE'
              AND time BETWEEN @tripTime - INTERVAL '5 seconds' 
                           AND @tripTime
              AND (
                  -- Match by equipment
                  message LIKE '%' || @equipment || '%'
                  OR tag_id LIKE @equipment || '%'
              )
            ORDER BY alarm_priority DESC, time ASC
        ", new { trip.TripTime, trip.EquipmentAffected });
        
        if (candidateAlarms.Any())
        {
            // Highest priority alarm = likely cause
            var initiatingAlarm = candidateAlarms.First();
            
            // Determine root cause tag (sensor that detected problem)
            string rootCauseTagId = await DetermineRootCause(
                initiatingAlarm.TagId, 
                trip.EquipmentAffected
            );
            
            // Update trip event with causality
            await _dbConnection.ExecuteAsync(@"
                UPDATE historian_raw.trip_event_tracking
                SET 
                    initiating_alarm_id = @alarmId,
                    root_cause_tag_id = @rootCauseTagId,
                    automated_diagnosis = @diagnosis::jsonb
                WHERE trip_event_id = @tripEventId
            ", new {
                tripEventId = trip.TripEventId,
                alarmId = initiatingAlarm.EventId,
                rootCauseTagId,
                diagnosis = JsonSerializer.Serialize(new {
                    alarm_count = candidateAlarms.Count(),
                    alarm_to_trip_seconds = (trip.TripTime - initiatingAlarm.AlarmTime).TotalSeconds,
                    alarm_priority = initiatingAlarm.AlarmPriority,
                    alarm_message = initiatingAlarm.Message
                })
            });
            
            _logger.LogInformation(
                "Correlated trip {TripId}: Alarm {AlarmId} ({AlarmTag}) caused trip on {Equipment}",
                trip.TripEventId, initiatingAlarm.EventId, initiatingAlarm.TagId, trip.EquipmentAffected
            );
        }
        else
        {
            _logger.LogWarning(
                "No candidate alarms found for trip {TripId} on {Equipment} (time: {TripTime})",
                trip.TripEventId, trip.EquipmentAffected, trip.TripTime
            );
        }
    }
    
    private async Task<string> DetermineRootCause(string alarmTagId, string equipment)
    {
        // Query tag_master for associated sensor
        var rootCauseTag = await _dbConnection.QuerySingleOrDefaultAsync<string>(@"
            SELECT tag_id
            FROM historian_meta.tag_master
            WHERE is_trip_initiator = TRUE
              AND associated_equipment = @equipment
              AND tag_id = @alarmTagId
        ", new { alarmTagId, equipment });
        
        return rootCauseTag ?? alarmTagId;  // Fallback to alarm tag if no mapping
    }
}
```

### 4.3 Configuration (appsettings.json)

```json
{
  "AlarmTripCorrelation": {
    "WindowSeconds": 5,
    "ProcessingIntervalSeconds": 10,
    "MaxUnlinkedTripsPerBatch": 50,
    "RootCauseMappings": [
      {
        "AlarmPattern": "*_OVERSPEED_*",
        "RootCauseTagPattern": "*_TURBINE_SPEED"
      },
      {
        "AlarmPattern": "*_HIGH_TEMP_*",
        "RootCauseTagPattern": "*_BEARING_TEMP"
      },
      {
        "AlarmPattern": "*_LOW_PRESSURE_*",
        "RootCauseTagPattern": "*_LUBE_OIL_PRESSURE"
      }
    ]
  }
}
```

---

## 5. Interlock-Trip Correlation Service

### 5.1 Design Overview

**Purpose**: Link interlock violations to trips, check bypass authorization

**Key Questions**:
1. Was an interlock violated before trip?
2. Was the interlock bypassed (authorized or unauthorized)?
3. Did bypass expire before trip?

**Compliance Requirement**: Safety audit trail (who bypassed, when, why)

### 5.2 Implementation (C# Pseudocode)

```csharp
public class InterlockTripCorrelationService : BackgroundService
{
    private readonly IDbConnection _dbConnection;
    
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            await CorrelateInterlockViolations();
            await Task.Delay(TimeSpan.FromSeconds(15), stoppingToken);
        }
    }
    
    private async Task CorrelateInterlockViolations()
    {
        // Get recent trips
        var recentTrips = await _dbConnection.QueryAsync<TripEvent>(@"
            SELECT trip_event_id, trip_time, trip_tag_id, equipment_affected
            FROM historian_raw.trip_event_tracking
            WHERE trip_time > now() - INTERVAL '1 hour'
              AND NOT EXISTS (
                  SELECT 1 FROM historian_raw.interlock_state_tracking ist
                  WHERE ist.related_trip_event_id = trip_event_tracking.trip_event_id
              )
        ");
        
        foreach (var trip in recentTrips)
        {
            // Check for interlock violations in 5-second window before trip
            var interlockViolations = await _dbConnection.QueryAsync<InterlockEvent>(@"
                SELECT 
                    interlock_event_id,
                    event_time,
                    interlock_tag_id,
                    interlock_type,
                    interlock_state,
                    bypass_authorized_by,
                    bypass_expires_at
                FROM historian_raw.interlock_state_tracking
                WHERE interlock_state IN ('VIOLATED', 'BYPASSED')
                  AND event_time BETWEEN @tripTime - INTERVAL '5 seconds' 
                                     AND @tripTime
                  AND (
                      affected_equipment = @equipment
                      OR interlock_tag_id LIKE @equipment || '%'
                  )
                ORDER BY event_time DESC
            ", new { trip.TripTime, trip.EquipmentAffected });
            
            foreach (var interlockEvent in interlockViolations)
            {
                // Check bypass status
                bool bypassExpired = interlockEvent.InterlockState == "BYPASSED" 
                                  && interlockEvent.BypassExpiresAt < trip.TripTime;
                
                // Link interlock to trip
                await _dbConnection.ExecuteAsync(@"
                    UPDATE historian_raw.interlock_state_tracking
                    SET related_trip_event_id = @tripEventId
                    WHERE interlock_event_id = @interlockEventId
                ", new {
                    tripEventId = trip.TripEventId,
                    interlockEventId = interlockEvent.InterlockEventId
                });
                
                // Log compliance issue if bypass expired
                if (bypassExpired)
                {
                    await _dbConnection.ExecuteAsync(@"
                        INSERT INTO historian_raw.historian_events 
                            (time, tag_id, event_type, severity, message, metadata)
                        VALUES (
                            @tripTime,
                            @interlockTagId,
                            'AUDIT_EXPIRED_BYPASS_CAUSED_TRIP',
                            5,  -- CRITICAL
                            @message,
                            @metadata::jsonb
                        )
                    ", new {
                        trip.TripTime,
                        interlockEvent.InterlockTagId,
                        message = $"SAFETY VIOLATION: Expired bypass on {interlockEvent.InterlockTagId} contributed to trip on {trip.EquipmentAffected}",
                        metadata = JsonSerializer.Serialize(new {
                            trip_event_id = trip.TripEventId,
                            interlock_event_id = interlockEvent.InterlockEventId,
                            bypass_authorized_by = interlockEvent.BypassAuthorizedBy,
                            bypass_expired_at = interlockEvent.BypassExpiresAt,
                            trip_time = trip.TripTime
                        })
                    });
                    
                    _logger.LogCritical(
                        "SAFETY VIOLATION: Expired bypass on {InterlockTag} caused trip on {Equipment}",
                        interlockEvent.InterlockTagId, trip.EquipmentAffected
                    );
                }
            }
        }
    }
}
```

---

## 6. State Detection Service

### 6.1 Design Overview

**Purpose**: Infer equipment operational state from multiple tag patterns

**Challenge**: State is not a single tag, but a pattern:
```
RUNNING:      Speed > 3000 RPM AND Load > 50 MW AND Status = 1
STOPPED:      Speed < 100 RPM AND Load < 5 MW AND Status = 0
TRIPPED:      Speed < 100 RPM AND Load < 5 MW AND Status = 2 (trip code)
STARTING:     Speed increasing AND Load < 20 MW AND Status = 3
SHUTTING_DOWN: Speed decreasing AND Load decreasing AND Status = 4
```

**Solution**: Multi-tag pattern recognition with hysteresis

### 6.2 Implementation (C# Pseudocode)

```csharp
public class StateDetectionService : BackgroundService
{
    private readonly OpcDaService _opcService;
    private readonly IDbConnection _dbConnection;
    
    // State machine per equipment
    private ConcurrentDictionary<string, EquipmentStateMachine> _stateMachines = new();
    
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _opcService.TagValuesUpdated += OnTagValuesUpdated;
        
        while (!stoppingToken.IsCancellationRequested)
        {
            // Evaluate state machines every 500ms
            await EvaluateStateMachines();
            await Task.Delay(500, stoppingToken);
        }
    }
    
    private async Task EvaluateStateMachines()
    {
        foreach (var (equipmentId, stateMachine) in _stateMachines)
        {
            var newState = stateMachine.EvaluateState();
            
            if (newState != stateMachine.CurrentState)
            {
                // State transition detected
                await RecordStateTransition(
                    equipmentId, 
                    stateMachine.CurrentState, 
                    newState,
                    stateMachine.GetCurrentTags()
                );
                
                stateMachine.CurrentState = newState;
            }
        }
    }
    
    private async Task RecordStateTransition(
        string equipmentId,
        string previousState,
        string newState,
        Dictionary<string, double> tagValues)
    {
        await _dbConnection.ExecuteAsync(@"
            INSERT INTO historian_raw.equipment_state_history
                (time, equipment_id, state, previous_state, tag_values)
            VALUES (now(), @equipmentId, @newState, @previousState, @tagValues::jsonb)
        ", new { equipmentId, newState, previousState, tagValues = JsonSerializer.Serialize(tagValues) });
        
        _logger.LogInformation(
            "State transition: {Equipment} changed from {OldState} to {NewState}",
            equipmentId, previousState, newState
        );
        
        // If state changed to TRIPPED, check for recent alarms
        if (newState == "TRIPPED")
        {
            await NotifyTripDetectionService(equipmentId);
        }
    }
}

public class EquipmentStateMachine
{
    public string EquipmentId { get; set; }
    public string CurrentState { get; set; } = "UNKNOWN";
    
    private Dictionary<string, double> _currentTags = new();
    
    public void UpdateTag(string tagId, double value)
    {
        _currentTags[tagId] = value;
    }
    
    public string EvaluateState()
    {
        // Get tag values with defaults
        double speed = GetTagValue("SPEED", 0);
        double load = GetTagValue("LOAD_MW", 0);
        int status = (int)GetTagValue("STATUS", 0);
        
        // State evaluation logic (with hysteresis)
        if (speed > 3000 && load > 50 && status == 1)
        {
            return "RUNNING";
        }
        else if (speed < 100 && load < 5 && status == 2)
        {
            return "TRIPPED";
        }
        else if (speed < 100 && load < 5 && status == 0)
        {
            return "STOPPED";
        }
        else if (IsSpeedIncreasing() && load < 20 && status == 3)
        {
            return "STARTING";
        }
        else if (IsSpeedDecreasing() && IsLoadDecreasing() && status == 4)
        {
            return "SHUTTING_DOWN";
        }
        else
        {
            return "UNKNOWN";
        }
    }
    
    private double GetTagValue(string tagSuffix, double defaultValue)
    {
        var fullTagId = $"{EquipmentId}_{tagSuffix}";
        return _currentTags.GetValueOrDefault(fullTagId, defaultValue);
    }
    
    private bool IsSpeedIncreasing()
    {
        // Compare current speed with 5-second-ago speed
        // Implementation: Store ring buffer of last 10 speed values
        return false;  // Simplified
    }
    
    private bool IsLoadDecreasing()
    {
        // Compare current load with 5-second-ago load
        return false;  // Simplified
    }
    
    public Dictionary<string, double> GetCurrentTags() => _currentTags;
}
```

### 6.3 New Table Required (Database Extension)

```sql
-- Add to OPERATIONAL_HARDENING.sql or separate migration
CREATE TABLE IF NOT EXISTS historian_raw.equipment_state_history (
    state_id BIGSERIAL PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL,
    equipment_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('RUNNING', 'STOPPED', 'TRIPPED', 'STARTING', 'SHUTTING_DOWN', 'UNKNOWN')),
    previous_state TEXT,
    tag_values JSONB,  -- Snapshot of tag values at transition
    CONSTRAINT fk_equipment FOREIGN KEY (equipment_id) REFERENCES historian_meta.equipment_hierarchy(equipment_id)
);

CREATE INDEX idx_equipment_state_time ON equipment_state_history(equipment_id, time DESC);
CREATE INDEX idx_equipment_state ON equipment_state_history(state);

COMMENT ON TABLE equipment_state_history IS 
'Equipment operational state history inferred from tag patterns.
Used for: MTBF/MTTR calculation, downtime analysis, OEE computation.
Populated by: StateDetectionService (application logic).';
```

---

## 7. Alarm Deduplication Service

### 7.1 Design Overview

**Purpose**: Prevent duplicate alarms within 5-minute window

**Problem**: Alarm oscillates (HIGH → NORMAL → HIGH → NORMAL) = 4 alarm events in 10 seconds

**Solution**: Track alarm insertions, suppress duplicates within time window

### 7.2 Implementation (C# Pseudocode)

```csharp
public class AlarmDeduplicationService
{
    private readonly IMemoryCache _cache;
    private readonly IDbConnection _dbConnection;
    private readonly TimeSpan _deduplicationWindow = TimeSpan.FromMinutes(5);
    
    public async Task<bool> TryInsertAlarm(AlarmEvent alarmEvent)
    {
        string cacheKey = $"alarm:{alarmEvent.TagId}:{alarmEvent.EventType}";
        
        // Check if alarm was raised recently
        if (_cache.TryGetValue(cacheKey, out DateTime lastAlarmTime))
        {
            if (DateTime.UtcNow - lastAlarmTime < _deduplicationWindow)
            {
                // Duplicate alarm within window: suppress
                _logger.LogDebug(
                    "Suppressed duplicate alarm: {TagId} {EventType} (last raised {Seconds}s ago)",
                    alarmEvent.TagId, alarmEvent.EventType, (DateTime.UtcNow - lastAlarmTime).TotalSeconds
                );
                return false;  // Alarm NOT inserted
            }
        }
        
        // Insert alarm
        await _dbConnection.ExecuteAsync(@"
            INSERT INTO historian_raw.historian_events 
                (time, tag_id, event_type, severity, message, 
                 alarm_state, alarm_priority, alarm_setpoint, alarm_actual_value)
            VALUES 
                (@time, @tagId, @eventType, @severity, @message,
                 @alarmState, @alarmPriority, @alarmSetpoint, @alarmActualValue)
        ", alarmEvent);
        
        // Cache insertion time
        _cache.Set(cacheKey, DateTime.UtcNow, _deduplicationWindow);
        
        return true;  // Alarm inserted
    }
}
```

---

## 8. Dynamic Priority Calculation

### 8.1 Design Overview

**Purpose**: Calculate alarm priority based on severity + context + time

**Factors**:
- **Base Severity**: From alarm definition (1-5)
- **Equipment Criticality**: From tag_master (1-5)
- **Time of Day**: Night shift (lower priority), day shift (higher priority)
- **Alarm History**: Frequent alarms (lower priority), rare alarms (higher priority)

**Formula**:
```
Priority = BaseSeverity × CriticalityMultiplier × TimeMultiplier × FrequencyMultiplier

CriticalityMultiplier = EquipmentCriticality / 3.0  (1.0 to 1.67)
TimeMultiplier = IsNightShift ? 0.8 : 1.0
FrequencyMultiplier = (AlarmCount in last 24h) > 10 ? 0.7 : 1.0
```

### 8.2 Implementation (C# Pseudocode)

```csharp
public class DynamicPriorityService
{
    private readonly IDbConnection _dbConnection;
    
    public async Task<int> CalculatePriority(
        string tagId,
        int baseSeverity,
        DateTime alarmTime)
    {
        // Get equipment criticality
        int criticality = await GetEquipmentCriticality(tagId);
        
        // Check time of day
        bool isNightShift = alarmTime.Hour >= 22 || alarmTime.Hour < 6;
        
        // Get alarm frequency (last 24 hours)
        int recentAlarmCount = await GetRecentAlarmCount(tagId, TimeSpan.FromHours(24));
        
        // Calculate multipliers
        double criticalityMultiplier = criticality / 3.0;  // 1.0 to 1.67
        double timeMultiplier = isNightShift ? 0.8 : 1.0;
        double frequencyMultiplier = recentAlarmCount > 10 ? 0.7 : 1.0;
        
        // Compute priority
        double rawPriority = baseSeverity * criticalityMultiplier * timeMultiplier * frequencyMultiplier;
        
        // Clamp to 1-5 range
        int finalPriority = Math.Clamp((int)Math.Round(rawPriority), 1, 5);
        
        _logger.LogDebug(
            "Priority calculation: {TagId} base={Base} crit={Crit} time={Time} freq={Freq} → final={Final}",
            tagId, baseSeverity, criticality, isNightShift ? "NIGHT" : "DAY", recentAlarmCount, finalPriority
        );
        
        return finalPriority;
    }
    
    private async Task<int> GetEquipmentCriticality(string tagId)
    {
        return await _dbConnection.QuerySingleOrDefaultAsync<int>(@"
            SELECT COALESCE(equipment_criticality, 3)
            FROM historian_meta.tag_master
            WHERE tag_id = @tagId
        ", new { tagId });
    }
    
    private async Task<int> GetRecentAlarmCount(string tagId, TimeSpan window)
    {
        return await _dbConnection.ExecuteScalarAsync<int>(@"
            SELECT COUNT(*)
            FROM historian_raw.historian_events
            WHERE tag_id = @tagId
              AND event_type LIKE 'ALARM_%'
              AND time > @startTime
        ", new { tagId, startTime = DateTime.UtcNow - window });
    }
}
```

---

## 9. Event Logging & Rate Limiting

### 9.1 Design Overview

**Purpose**: Centralized event logging with rate limiting (prevent log flood)

**Features**:
- Rate limit by event_type + tag_id (configurable per event)
- Batch insertion (reduce DB roundtrips)
- Async queue (non-blocking)

### 9.2 Implementation (C# Pseudocode)

```csharp
public class EventLoggingService : BackgroundService
{
    private readonly IDbConnection _dbConnection;
    private readonly Channel<EventLogEntry> _eventQueue;
    private readonly IMemoryCache _rateLimitCache;
    
    public EventLoggingService()
    {
        _eventQueue = Channel.CreateUnbounded<EventLogEntry>();
    }
    
    public async Task LogEventAsync(
        string eventType,
        string tagId,
        string message,
        int severity,
        JObject metadata = null,
        TimeSpan? rateLimitWindow = null)
    {
        // Check rate limiting
        if (rateLimitWindow.HasValue)
        {
            string rateLimitKey = $"ratelimit:{eventType}:{tagId}";
            if (_rateLimitCache.TryGetValue(rateLimitKey, out _))
            {
                // Within rate limit window: drop event
                return;
            }
            _rateLimitCache.Set(rateLimitKey, true, rateLimitWindow.Value);
        }
        
        // Enqueue event (non-blocking)
        await _eventQueue.Writer.WriteAsync(new EventLogEntry
        {
            Time = DateTime.UtcNow,
            TagId = tagId,
            EventType = eventType,
            Severity = severity,
            Message = message,
            Metadata = metadata
        });
    }
    
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var batch = new List<EventLogEntry>();
        
        while (!stoppingToken.IsCancellationRequested)
        {
            // Collect events for 1 second
            var timeout = Task.Delay(1000, stoppingToken);
            
            while (batch.Count < 1000)  // Max 1000 events per batch
            {
                if (_eventQueue.Reader.TryRead(out var eventEntry))
                {
                    batch.Add(eventEntry);
                }
                else if (await Task.WhenAny(_eventQueue.Reader.WaitToReadAsync(stoppingToken).AsTask(), timeout) == timeout)
                {
                    break;  // Timeout: flush batch
                }
            }
            
            if (batch.Any())
            {
                await FlushBatch(batch);
                batch.Clear();
            }
        }
    }
    
    private async Task FlushBatch(List<EventLogEntry> batch)
    {
        try
        {
            await _dbConnection.ExecuteAsync(@"
                INSERT INTO historian_raw.historian_events 
                    (time, tag_id, event_type, severity, message, metadata)
                SELECT 
                    time, tag_id, event_type, severity, message, metadata::jsonb
                FROM UNNEST(
                    @times, @tagIds, @eventTypes, @severities, @messages, @metadatas
                ) AS t(time, tag_id, event_type, severity, message, metadata)
            ", new {
                times = batch.Select(e => e.Time).ToArray(),
                tagIds = batch.Select(e => e.TagId).ToArray(),
                eventTypes = batch.Select(e => e.EventType).ToArray(),
                severities = batch.Select(e => e.Severity).ToArray(),
                messages = batch.Select(e => e.Message).ToArray(),
                metadatas = batch.Select(e => e.Metadata?.ToString()).ToArray()
            });
            
            _logger.LogDebug("Flushed {Count} events to database", batch.Count);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to flush event batch");
        }
    }
}

public class EventLogEntry
{
    public DateTime Time { get; set; }
    public string TagId { get; set; }
    public string EventType { get; set; }
    public int Severity { get; set; }
    public string Message { get; set; }
    public JObject Metadata { get; set; }
}
```

---

## 10. Authentication & Authorization

### 10.1 Alarm Acknowledgment API

**Endpoint**: `POST /api/alarms/{alarmId}/acknowledge`

**Authorization**: Requires `Operator` or `Engineer` role

```csharp
[ApiController]
[Route("api/alarms")]
[Authorize(Roles = "Operator,Engineer")]
public class AlarmsController : ControllerBase
{
    private readonly IDbConnection _dbConnection;
    
    [HttpPost("{alarmId}/acknowledge")]
    public async Task<IActionResult> AcknowledgeAlarm(
        long alarmId,
        [FromBody] AcknowledgeAlarmRequest request)
    {
        // Get user identity
        string userName = User.Identity.Name;
        
        // Call database function
        var result = await _dbConnection.QuerySingleAsync<bool>(@"
            SELECT acknowledge_alarm(@alarmId, @userName, @notes)
        ", new { alarmId, userName, notes = request.Notes });
        
        if (result)
        {
            return Ok(new { success = true, message = "Alarm acknowledged" });
        }
        else
        {
            return BadRequest(new { success = false, message = "Alarm cannot be acknowledged (already cleared or acknowledged)" });
        }
    }
}

public class AcknowledgeAlarmRequest
{
    [Required]
    [MaxLength(500)]
    public string Notes { get; set; }
}
```

### 10.2 Interlock Bypass Authorization

**Endpoint**: `POST /api/interlocks/{interlockId}/bypass`

**Authorization**: Requires `MaintenanceSupervisor` or `PlantManager` role

```csharp
[ApiController]
[Route("api/interlocks")]
[Authorize(Roles = "MaintenanceSupervisor,PlantManager")]
public class InterlocksController : ControllerBase
{
    private readonly IDbConnection _dbConnection;
    
    [HttpPost("{interlockId}/bypass")]
    public async Task<IActionResult> BypassInterlock(
        string interlockId,
        [FromBody] BypassInterlockRequest request)
    {
        // Validate bypass duration (max 8 hours)
        if (request.DurationHours > 8)
        {
            return BadRequest("Bypass duration cannot exceed 8 hours");
        }
        
        // Get user identity
        string userName = User.Identity.Name;
        
        // Record bypass
        await _dbConnection.ExecuteAsync(@"
            INSERT INTO historian_raw.interlock_state_tracking 
                (event_time, interlock_tag_id, interlock_type, interlock_state,
                 affected_equipment, bypass_reason, bypass_authorized_by, bypass_expires_at)
            VALUES (
                now(), @interlockId, @interlockType, 'BYPASSED',
                @equipment, @reason, @userName, now() + (@duration || ' hours')::INTERVAL
            )
        ", new {
            interlockId,
            interlockType = request.InterlockType,
            equipment = request.Equipment,
            reason = request.Reason,
            userName,
            duration = request.DurationHours
        });
        
        // Log audit event
        await _dbConnection.ExecuteAsync(@"
            INSERT INTO historian_raw.historian_events 
                (time, tag_id, event_type, severity, message, metadata)
            VALUES (
                now(), @interlockId, 'AUDIT_INTERLOCK_BYPASS_AUTHORIZED', 5,
                @message, @metadata::jsonb
            )
        ", new {
            interlockId,
            message = $"Interlock {interlockId} bypassed by {userName} for {request.DurationHours} hours",
            metadata = JsonSerializer.Serialize(new {
                authorized_by = userName,
                reason = request.Reason,
                duration_hours = request.DurationHours,
                expires_at = DateTime.UtcNow.AddHours(request.DurationHours)
            })
        });
        
        return Ok(new {
            success = true,
            message = "Interlock bypassed",
            expires_at = DateTime.UtcNow.AddHours(request.DurationHours)
        });
    }
}

public class BypassInterlockRequest
{
    [Required]
    public string InterlockType { get; set; }
    
    [Required]
    public string Equipment { get; set; }
    
    [Required]
    [MaxLength(500)]
    public string Reason { get; set; }
    
    [Range(0.5, 8.0)]
    public double DurationHours { get; set; }
}
```

---

## 11. Testing & Validation

### 11.1 Integration Test Scenarios

```csharp
[Collection("Database")]
public class TripDetectionIntegrationTests
{
    [Fact]
    public async Task EndToEnd_TripDetection_AlarmCorrelation_InterlockLink()
    {
        // Arrange: Setup equipment + alarms + interlocks
        await SetupEquipment("TURBINE_01");
        await SetupAlarm("TURBINE_01_OVERSPEED_ALARM", priority: 5);
        await SetupInterlock("LUBE_OIL_PRESSURE_OK", type: "PERMISSIVE");
        
        // Act 1: Start equipment
        await SimulateTagUpdate("TURBINE_01_RUN_STATUS", 1.0);
        await Task.Delay(2000);
        
        // Act 2: Interlock violated (low lube oil pressure)
        await SimulateInterlockViolation("LUBE_OIL_PRESSURE_OK");
        await Task.Delay(1000);
        
        // Act 3: Alarm raised (overspeed)
        await SimulateAlarm("TURBINE_01_OVERSPEED_ALARM", actualValue: 3800, setpoint: 3600);
        await Task.Delay(500);
        
        // Act 4: Equipment stops (trip)
        await SimulateTagUpdate("TURBINE_01_RUN_STATUS", 0.0);
        await Task.Delay(5000);  // Wait for correlation services
        
        // Assert: Trip detected
        var trips = await GetTripsFromDatabase("TURBINE_01");
        Assert.Single(trips);
        
        var trip = trips[0];
        Assert.Equal("SAFETY_TRIP", trip.TripCategory);
        Assert.NotNull(trip.InitiatingAlarmId);  // Alarm correlation worked
        Assert.Equal("TURBINE_01_OVERSPEED_ALARM", trip.RootCauseTagId);
        
        // Assert: Interlock linked to trip
        var interlockEvents = await GetInterlockEventsForTrip(trip.TripEventId);
        Assert.Single(interlockEvents);
        Assert.Equal("LUBE_OIL_PRESSURE_OK", interlockEvents[0].InterlockTagId);
    }
}
```

### 11.2 Performance Benchmarks

**Target Performance**:
- Trip detection latency: <500ms (from equipment stop to trip recorded)
- Alarm correlation: <5 seconds (from trip to causality populated)
- Interlock correlation: <10 seconds (from trip to interlock linked)
- Event logging throughput: >1000 events/second (batched)

---

**Document Status**: Implementation Roadmap  
**Next Document**: PART 3 - Analytics & Operations (queries, shift calendar, maintenance, future enhancements)

