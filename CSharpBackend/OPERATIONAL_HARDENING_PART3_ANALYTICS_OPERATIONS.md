# OPERATIONAL HARDENING - PART 3: ANALYTICS & OPERATIONS

## Document Overview
**Purpose**: Analytics queries, maintenance procedures, and operational guidelines  
**Version**: 1.0  
**Date**: December 22, 2025  
**Status**: Production Operations Guide  
**Prerequisites**: PART 1 (deployed) + PART 2 (services implemented)

---

## Table of Contents
1. [Analytics Queries](#analytics-queries)
2. [Trip Analysis](#trip-analysis)
3. [Alarm Analytics](#alarm-analytics)
4. [Interlock Compliance Audits](#interlock-compliance-audits)
5. [MTBF/MTTR Calculations](#mtbfmttr-calculations)
6. [Shift-Wise Analytics](#shift-wise-analytics)
7. [Maintenance Procedures](#maintenance-procedures)
8. [Performance Tuning](#performance-tuning)
9. [Monitoring & Alerts](#monitoring--alerts)
10. [Future Enhancements](#future-enhancements)

---

## 1. Analytics Queries

### 1.1 Active Alarms Dashboard

**Query**: Real-time alarm summary by priority

```sql
-- Count active alarms by priority
SELECT 
    alarm_priority,
    COUNT(*) AS alarm_count,
    MIN(EXTRACT(EPOCH FROM (now() - time))/60) AS oldest_alarm_age_minutes,
    STRING_AGG(DISTINCT tag_id, ', ' ORDER BY tag_id) AS affected_tags
FROM historian_raw.vw_active_alarms
GROUP BY alarm_priority
ORDER BY alarm_priority DESC;

-- Sample output:
alarm_priority | alarm_count | oldest_alarm_age_minutes | affected_tags
---------------+-------------+--------------------------+---------------------------
5              |           2 |                     12.5 | TURBINE_OVERSPEED, FIRE_ALARM
4              |           5 |                     45.2 | BEARING_TEMP, PRESSURE_HIGH
3              |          12 |                    120.8 | COOLING_WATER, VIBRATION
```

**Web UI Integration** (JavaScript):
```javascript
// Auto-refresh every 10 seconds
setInterval(async () => {
    const response = await fetch('/api/alarms/active');
    const alarms = await response.json();
    
    updateAlarmBanner(alarms.filter(a => a.alarm_priority >= 4));  // Critical + Urgent
    updateAlarmTable(alarms);
}, 10000);
```

### 1.2 Alarm Response Time Analysis

**Query**: Average operator response time by priority

```sql
SELECT 
    alarm_priority,
    COUNT(*) AS acknowledged_count,
    AVG(EXTRACT(EPOCH FROM (acknowledged_at - time))/60) AS avg_response_minutes,
    MIN(EXTRACT(EPOCH FROM (acknowledged_at - time))/60) AS fastest_response_minutes,
    MAX(EXTRACT(EPOCH FROM (acknowledged_at - time))/60) AS slowest_response_minutes,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (acknowledged_at - time))/60) AS median_response_minutes
FROM historian_raw.historian_events
WHERE event_type LIKE 'ALARM_%'
  AND alarm_state = 'ACKNOWLEDGED'
  AND time > now() - INTERVAL '7 days'
GROUP BY alarm_priority
ORDER BY alarm_priority DESC;

-- Sample output:
alarm_priority | acknowledged_count | avg_response_minutes | fastest | slowest | median
---------------+--------------------+---------------------+---------+---------+--------
5              |                 15 |                 2.3 |     0.5 |     5.2 |    1.8
4              |                 42 |                 8.7 |     1.2 |    25.3 |    6.5
3              |                123 |                18.5 |     2.1 |    85.2 |   12.3
```

**KPI Targets**:
- Priority 5 (Critical): <3 min response time
- Priority 4 (Urgent): <10 min response time
- Priority 3 (High): <20 min response time

### 1.3 Unacknowledged Alarms Report

**Query**: Alarms pending operator action (>15 minutes)

```sql
SELECT 
    event_id AS alarm_id,
    time AS raised_at,
    EXTRACT(EPOCH FROM (now() - time))/60 AS age_minutes,
    tag_id,
    event_type AS alarm_type,
    alarm_priority,
    alarm_actual_value,
    alarm_setpoint,
    message
FROM historian_raw.vw_active_alarms
WHERE alarm_state = 'ACTIVE'
  AND EXTRACT(EPOCH FROM (now() - time))/60 > 15
ORDER BY alarm_priority DESC, time ASC;
```

**Automated Alert** (C# scheduled job):
```csharp
// Run every 15 minutes
public async Task CheckUnacknowledgedAlarms()
{
    var unacknowledged = await _dbConnection.QueryAsync<Alarm>(@"
        SELECT * FROM historian_raw.vw_active_alarms
        WHERE alarm_state = 'ACTIVE'
          AND EXTRACT(EPOCH FROM (now() - time))/60 > 15
        ORDER BY alarm_priority DESC
    ");
    
    if (unacknowledged.Any())
    {
        // Send SMS/email to shift supervisor
        await _notificationService.AlertShiftSupervisor(unacknowledged);
    }
}
```

---

## 2. Trip Analysis

### 2.1 Trip Frequency by Equipment

**Query**: MTBF analysis (Mean Time Between Failures)

```sql
SELECT * FROM historian_raw.vw_trip_frequency_by_equipment;

-- Sample output:
equipment_affected | trip_category | trip_count | avg_duration_seconds | total_production_loss_mw | first_trip          | last_trip           | observation_period_days | trips_per_day
-------------------+---------------+------------+----------------------+--------------------------+--------------------+--------------------+------------------------+--------------
TURBINE_01         | SAFETY_TRIP   |          5 |                 3600 |                   1352.5 | 2025-11-01 08:00   | 2025-12-15 14:30   |                     44 |         0.11
BOILER_A           | PROCESS_TRIP  |         12 |                 1200 |                      0.0 | 2025-10-20 10:15   | 2025-12-20 16:45   |                     61 |         0.20
```

**MTBF Calculation**:
```sql
-- Mean Time Between Failures (MTBF) in days
SELECT 
    equipment_affected,
    trip_category,
    trip_count,
    observation_period_days,
    ROUND(observation_period_days::NUMERIC / NULLIF(trip_count, 0), 2) AS mtbf_days,
    CASE 
        WHEN trip_count = 0 THEN 'EXCELLENT'
        WHEN (observation_period_days::NUMERIC / NULLIF(trip_count, 0)) > 30 THEN 'GOOD'
        WHEN (observation_period_days::NUMERIC / NULLIF(trip_count, 0)) > 10 THEN 'FAIR'
        ELSE 'POOR'
    END AS reliability_rating
FROM historian_raw.vw_trip_frequency_by_equipment
WHERE observation_period_days > 0
ORDER BY mtbf_days ASC;

-- Sample output:
equipment_affected | trip_category | trip_count | observation_period_days | mtbf_days | reliability_rating
-------------------+---------------+------------+------------------------+-----------+-------------------
PUMP_03            | PROCESS_TRIP  |         15 |                     60 |      4.00 | POOR
TURBINE_01         | SAFETY_TRIP   |          5 |                     44 |      8.80 | POOR
BOILER_A           | PROCESS_TRIP  |         12 |                     61 |      5.08 | POOR
COMPRESSOR_02      | SAFETY_TRIP   |          2 |                     90 |     45.00 | GOOD
```

### 2.2 Trip Causality Deep Dive

**Query**: Alarm → Trip correlation with time gaps

```sql
SELECT 
    trip_event_id,
    trip_time,
    equipment_affected,
    trip_category,
    -- Alarm details
    initiating_alarm_type,
    alarm_raised_at,
    alarm_to_trip_seconds,
    alarm_priority,
    -- Production impact
    trip_duration_seconds,
    production_loss_mw,
    -- Root cause
    root_cause_tag_name,
    root_cause_criticality
FROM historian_raw.vw_trip_causality
WHERE trip_time > now() - INTERVAL '30 days'
ORDER BY production_loss_mw DESC NULLS LAST;

-- Top 10 costliest trips (last 30 days)
SELECT 
    equipment_affected,
    trip_time,
    production_loss_mw,
    trip_duration_seconds / 60.0 AS downtime_minutes,
    initiating_alarm_type,
    root_cause_tag_name
FROM historian_raw.vw_trip_causality
WHERE trip_time > now() - INTERVAL '30 days'
  AND production_loss_mw IS NOT NULL
ORDER BY production_loss_mw DESC
LIMIT 10;
```

### 2.3 Fast Escalation Analysis

**Query**: Trips with <5 seconds alarm-to-trip time (fast cascades)

```sql
-- Fast escalation trips (alarm → trip in <5 seconds)
SELECT 
    trip_event_id,
    trip_time,
    equipment_affected,
    initiating_alarm_type,
    alarm_to_trip_seconds,
    production_loss_mw,
    operator_notes
FROM historian_raw.vw_trip_causality
WHERE alarm_to_trip_seconds < 5
  AND trip_time > now() - INTERVAL '90 days'
ORDER BY trip_time DESC;

-- Count by equipment
SELECT 
    equipment_affected,
    COUNT(*) AS fast_escalation_count,
    AVG(alarm_to_trip_seconds) AS avg_escalation_seconds
FROM historian_raw.vw_trip_causality
WHERE alarm_to_trip_seconds < 5
  AND trip_time > now() - INTERVAL '90 days'
GROUP BY equipment_affected
ORDER BY fast_escalation_count DESC;
```

**Interpretation**:
- **<2 seconds**: Protection system trip (normal, safety design)
- **2-5 seconds**: Operator had no time to react (consider alarm tuning)
- **>10 seconds**: Operator could have intervened (training opportunity)

### 2.4 Production Loss Attribution

**Query**: Total production loss by root cause

```sql
-- Top 10 root causes by production loss (last 90 days)
SELECT 
    root_cause_tag_name,
    root_cause_tag_id,
    COUNT(*) AS trip_count,
    SUM(production_loss_mw) AS total_loss_mw,
    AVG(production_loss_mw) AS avg_loss_per_trip_mw,
    SUM(trip_duration_seconds) / 3600.0 AS total_downtime_hours
FROM historian_raw.vw_trip_causality
WHERE trip_time > now() - INTERVAL '90 days'
  AND production_loss_mw IS NOT NULL
GROUP BY root_cause_tag_name, root_cause_tag_id
ORDER BY total_loss_mw DESC
LIMIT 10;

-- Sample output:
root_cause_tag_name       | root_cause_tag_id        | trip_count | total_loss_mw | avg_loss_per_trip_mw | total_downtime_hours
--------------------------+--------------------------+------------+---------------+----------------------+---------------------
Bearing Temperature High  | TURBINE_01_BEARING_TEMP  |          5 |        1352.5 |               270.50 |                 5.0
Lube Oil Pressure Low     | LUBE_OIL_PRESSURE        |          8 |        1080.0 |               135.00 |                 8.0
```

**Cost Analysis** (assuming $100/MWh):
```sql
-- Financial impact of trips (last 90 days)
SELECT 
    equipment_affected,
    COUNT(*) AS trip_count,
    SUM(production_loss_mw) AS total_loss_mw,
    SUM(production_loss_mw) * 100 AS estimated_cost_usd,  -- Assume $100/MWh
    AVG(trip_duration_seconds) / 60.0 AS avg_downtime_minutes
FROM historian_raw.vw_trip_causality
WHERE trip_time > now() - INTERVAL '90 days'
  AND production_loss_mw IS NOT NULL
GROUP BY equipment_affected
ORDER BY estimated_cost_usd DESC;
```

---

## 3. Alarm Analytics

### 3.1 Alarm Flood Detection

**Query**: Detect alarm floods (>10 alarms in 1 minute)

```sql
-- Alarm count per minute (last 24 hours)
WITH alarm_counts_per_minute AS (
    SELECT 
        DATE_TRUNC('minute', time) AS minute,
        COUNT(*) AS alarm_count
    FROM historian_raw.historian_events
    WHERE event_type LIKE 'ALARM_%'
      AND time > now() - INTERVAL '24 hours'
    GROUP BY DATE_TRUNC('minute', time)
)
SELECT 
    minute,
    alarm_count,
    CASE 
        WHEN alarm_count > 50 THEN 'SEVERE_FLOOD'
        WHEN alarm_count > 20 THEN 'FLOOD'
        WHEN alarm_count > 10 THEN 'HIGH'
        ELSE 'NORMAL'
    END AS flood_severity
FROM alarm_counts_per_minute
WHERE alarm_count > 10
ORDER BY alarm_count DESC;

-- Sample output:
minute               | alarm_count | flood_severity
---------------------+-------------+---------------
2025-12-22 14:35:00  |          78 | SEVERE_FLOOD
2025-12-22 14:36:00  |          45 | FLOOD
2025-12-22 10:22:00  |          15 | HIGH
```

**Alarm Flood Response**:
1. Identify root cause (check system events at flood start time)
2. Implement alarm suppression (if recurring nuisance alarms)
3. Review alarm priority (downgrade low-value alarms)

### 3.2 Chattering Alarms

**Query**: Alarms oscillating (>5 activations in 10 minutes)

```sql
-- Detect chattering alarms (last 24 hours)
WITH alarm_sequences AS (
    SELECT 
        tag_id,
        event_type,
        time,
        LAG(time) OVER (PARTITION BY tag_id, event_type ORDER BY time) AS prev_time
    FROM historian_raw.historian_events
    WHERE event_type LIKE 'ALARM_%'
      AND alarm_state = 'ACTIVE'
      AND time > now() - INTERVAL '24 hours'
)
SELECT 
    tag_id,
    event_type,
    COUNT(*) AS activation_count,
    MIN(time) AS first_activation,
    MAX(time) AS last_activation,
    EXTRACT(EPOCH FROM (MAX(time) - MIN(time)))/60 AS duration_minutes
FROM alarm_sequences
WHERE prev_time IS NOT NULL
  AND EXTRACT(EPOCH FROM (time - prev_time)) < 600  -- <10 minutes between activations
GROUP BY tag_id, event_type
HAVING COUNT(*) > 5
ORDER BY activation_count DESC;

-- Sample output:
tag_id                  | event_type        | activation_count | first_activation    | last_activation     | duration_minutes
------------------------+-------------------+------------------+--------------------+--------------------+-----------------
COOLING_WATER_FLOW_LOW  | ALARM_LOW         |               12 | 2025-12-22 08:00   | 2025-12-22 08:45   |            45.0
PRESSURE_OSCILLATION    | ALARM_HIGH        |                8 | 2025-12-22 14:20   | 2025-12-22 14:35   |            15.0
```

**Remediation**:
1. Adjust alarm setpoint (widen deadband)
2. Add alarm delay (e.g., must persist 30 seconds before raising)
3. Implement alarm suppression schedule (if expected during certain operations)

### 3.3 Nuisance Alarms

**Query**: Alarms with high activation rate but low acknowledgment rate

```sql
-- Nuisance alarm candidates (raised often, rarely acknowledged)
WITH alarm_stats AS (
    SELECT 
        tag_id,
        event_type,
        COUNT(*) AS total_activations,
        COUNT(*) FILTER (WHERE alarm_state = 'ACKNOWLEDGED') AS acknowledged_count,
        100.0 * COUNT(*) FILTER (WHERE alarm_state = 'ACKNOWLEDGED') / COUNT(*) AS acknowledgment_rate
    FROM historian_raw.historian_events
    WHERE event_type LIKE 'ALARM_%'
      AND time > now() - INTERVAL '30 days'
    GROUP BY tag_id, event_type
)
SELECT 
    tag_id,
    event_type,
    total_activations,
    acknowledged_count,
    ROUND(acknowledgment_rate, 1) AS acknowledgment_pct
FROM alarm_stats
WHERE total_activations > 10  -- At least 10 activations
  AND acknowledgment_rate < 20  -- <20% acknowledgment rate
ORDER BY total_activations DESC;

-- Sample output:
tag_id                  | event_type        | total_activations | acknowledged_count | acknowledgment_pct
------------------------+-------------------+-------------------+-------------------+-------------------
MINOR_LEAK_DETECTOR     | ALARM_LOW         |                45 |                  2 |                4.4
VIBRATION_SENSOR_01     | ALARM_HIGH        |                38 |                  5 |               13.2
```

**Action**:
1. Downgrade priority (e.g., Priority 3 → Priority 2)
2. Increase alarm setpoint (reduce false positives)
3. Remove alarm if non-actionable (informational only)

---

## 4. Interlock Compliance Audits

### 4.1 Active Bypass Report

**Query**: Current active bypasses (safety audit)

```sql
SELECT * FROM historian_raw.vw_interlock_violations
WHERE status IN ('ACTIVE_BYPASS', 'EXPIRED_BYPASS')
ORDER BY 
    CASE status
        WHEN 'EXPIRED_BYPASS' THEN 1  -- Highest priority
        WHEN 'ACTIVE_BYPASS' THEN 2
    END,
    event_time DESC;

-- Sample output:
interlock_event_id | event_time          | interlock_tag_id      | interlock_type | interlock_state | bypass_authorized_by        | bypass_expires_at   | status
-------------------+--------------------+-----------------------+----------------+-----------------+----------------------------+--------------------+---------------
1234               | 2025-12-22 14:00   | LUBE_OIL_PRESSURE_OK  | PERMISSIVE     | BYPASSED        | maintenance_supervisor_jane | 2025-12-22 12:00   | EXPIRED_BYPASS
1235               | 2025-12-22 15:00   | COOLING_WATER_FLOW_OK | CONDITIONAL    | BYPASSED        | plant_manager_bob           | 2025-12-22 17:00   | ACTIVE_BYPASS
```

**Compliance Actions**:
1. **Expired bypasses**: Immediate investigation (safety violation)
2. **Active bypasses >4 hours**: Supervisor review
3. **Weekly audit**: All bypasses reviewed by safety committee

### 4.2 Unauthorized Bypass Detection

**Query**: Bypasses without proper authorization

```sql
-- Bypasses missing authorization
SELECT 
    interlock_event_id,
    event_time,
    interlock_tag_id,
    affected_equipment,
    bypass_reason,
    bypass_authorized_by,
    CASE 
        WHEN bypass_authorized_by IS NULL THEN 'NO_AUTHORIZATION'
        WHEN bypass_reason IS NULL OR LENGTH(bypass_reason) < 10 THEN 'INSUFFICIENT_REASON'
        WHEN bypass_expires_at IS NULL THEN 'NO_EXPIRY'
        ELSE 'VALID'
    END AS compliance_status
FROM historian_raw.interlock_state_tracking
WHERE interlock_state = 'BYPASSED'
  AND event_time > now() - INTERVAL '90 days'
  AND (
      bypass_authorized_by IS NULL
      OR bypass_reason IS NULL
      OR LENGTH(bypass_reason) < 10
      OR bypass_expires_at IS NULL
  )
ORDER BY event_time DESC;
```

**Automated Alert**:
```csharp
// Daily compliance check (send report to safety officer)
public async Task CheckBypassCompliance()
{
    var violations = await _dbConnection.QueryAsync<BypassViolation>(@"
        SELECT * FROM historian_raw.interlock_state_tracking
        WHERE interlock_state = 'BYPASSED'
          AND event_time > now() - INTERVAL '24 hours'
          AND (bypass_authorized_by IS NULL OR bypass_reason IS NULL)
    ");
    
    if (violations.Any())
    {
        await _emailService.SendComplianceAlert(
            "safety_officer@plant.com",
            $"SAFETY ALERT: {violations.Count()} unauthorized bypasses detected in last 24 hours",
            violations
        );
    }
}
```

### 4.3 Bypass Frequency by User

**Query**: Who bypasses interlocks most frequently?

```sql
-- Top bypass users (last 90 days)
SELECT 
    bypass_authorized_by,
    COUNT(*) AS bypass_count,
    STRING_AGG(DISTINCT affected_equipment, ', ') AS equipment_list,
    AVG(EXTRACT(EPOCH FROM (bypass_expires_at - event_time))/3600) AS avg_bypass_duration_hours
FROM historian_raw.interlock_state_tracking
WHERE interlock_state = 'BYPASSED'
  AND event_time > now() - INTERVAL '90 days'
  AND bypass_authorized_by IS NOT NULL
GROUP BY bypass_authorized_by
ORDER BY bypass_count DESC;

-- Sample output:
bypass_authorized_by           | bypass_count | equipment_list              | avg_bypass_duration_hours
-------------------------------+--------------+----------------------------+---------------------------
maintenance_supervisor_jane     |           15 | TURBINE_01, BOILER_A       |                       2.5
plant_manager_bob               |            8 | COMPRESSOR_02, PUMP_03     |                       4.0
```

**Review Criteria**:
- >10 bypasses per month: Requires justification review
- Average duration >4 hours: Check if equipment needs repair
- Same equipment repeated: Consider permanent fix instead of bypass

---

## 5. MTBF/MTTR Calculations

### 5.1 Mean Time Between Failures (MTBF)

**Query**: MTBF by equipment (higher is better)

```sql
-- MTBF calculation (days between trips)
WITH trip_intervals AS (
    SELECT 
        trip_tag_id,
        equipment_affected,
        trip_time,
        LAG(trip_time) OVER (PARTITION BY trip_tag_id ORDER BY trip_time) AS prev_trip_time,
        EXTRACT(EPOCH FROM (trip_time - LAG(trip_time) OVER (PARTITION BY trip_tag_id ORDER BY trip_time)))/86400 AS days_since_last_trip
    FROM historian_raw.trip_event_tracking
    WHERE trip_time > now() - INTERVAL '180 days'
)
SELECT 
    equipment_affected,
    COUNT(*) AS trip_count,
    ROUND(AVG(days_since_last_trip), 2) AS mtbf_days,
    ROUND(MIN(days_since_last_trip), 2) AS shortest_interval_days,
    ROUND(MAX(days_since_last_trip), 2) AS longest_interval_days,
    CASE 
        WHEN AVG(days_since_last_trip) > 30 THEN 'EXCELLENT'
        WHEN AVG(days_since_last_trip) > 14 THEN 'GOOD'
        WHEN AVG(days_since_last_trip) > 7 THEN 'FAIR'
        ELSE 'POOR'
    END AS reliability_rating
FROM trip_intervals
WHERE days_since_last_trip IS NOT NULL
GROUP BY equipment_affected
ORDER BY mtbf_days DESC;

-- Sample output:
equipment_affected | trip_count | mtbf_days | shortest_interval_days | longest_interval_days | reliability_rating
-------------------+------------+-----------+-----------------------+----------------------+-------------------
COMPRESSOR_02      |          3 |     45.33 |                  30.5 |                 60.2 | EXCELLENT
TURBINE_01         |         12 |      8.75 |                   2.1 |                 18.3 | FAIR
PUMP_03            |         25 |      3.20 |                   0.5 |                 12.8 | POOR
```

### 5.2 Mean Time To Repair (MTTR)

**Query**: MTTR by equipment (lower is better)

```sql
-- MTTR calculation (average downtime per trip)
SELECT 
    equipment_affected,
    COUNT(*) AS trip_count,
    ROUND(AVG(trip_duration_seconds) / 60.0, 2) AS mttr_minutes,
    ROUND(MIN(trip_duration_seconds) / 60.0, 2) AS fastest_recovery_minutes,
    ROUND(MAX(trip_duration_seconds) / 60.0, 2) AS slowest_recovery_minutes,
    CASE 
        WHEN AVG(trip_duration_seconds) / 60.0 < 30 THEN 'EXCELLENT'
        WHEN AVG(trip_duration_seconds) / 60.0 < 60 THEN 'GOOD'
        WHEN AVG(trip_duration_seconds) / 60.0 < 120 THEN 'FAIR'
        ELSE 'POOR'
    END AS recovery_rating
FROM historian_raw.trip_event_tracking
WHERE trip_time > now() - INTERVAL '180 days'
  AND trip_duration_seconds IS NOT NULL
GROUP BY equipment_affected
ORDER BY mttr_minutes ASC;

-- Sample output:
equipment_affected | trip_count | mttr_minutes | fastest_recovery_minutes | slowest_recovery_minutes | recovery_rating
-------------------+------------+--------------+-------------------------+-------------------------+----------------
PUMP_03            |         25 |        15.50 |                     5.0 |                    45.0 | EXCELLENT
TURBINE_01         |         12 |        65.25 |                    30.0 |                   180.0 | FAIR
BOILER_A           |          8 |       145.75 |                    90.0 |                   240.0 | POOR
```

### 5.3 Combined Reliability Scorecard

**Query**: Equipment reliability dashboard

```sql
-- Equipment reliability scorecard (last 180 days)
WITH mtbf AS (
    SELECT 
        equipment_affected,
        AVG(EXTRACT(EPOCH FROM (trip_time - LAG(trip_time) OVER (PARTITION BY equipment_affected ORDER BY trip_time)))/86400) AS mtbf_days
    FROM historian_raw.trip_event_tracking
    WHERE trip_time > now() - INTERVAL '180 days'
    GROUP BY equipment_affected
),
mttr AS (
    SELECT 
        equipment_affected,
        AVG(trip_duration_seconds) / 60.0 AS mttr_minutes
    FROM historian_raw.trip_event_tracking
    WHERE trip_time > now() - INTERVAL '180 days'
      AND trip_duration_seconds IS NOT NULL
    GROUP BY equipment_affected
),
trip_counts AS (
    SELECT 
        equipment_affected,
        COUNT(*) AS trip_count,
        SUM(production_loss_mw) AS total_loss_mw
    FROM historian_raw.trip_event_tracking
    WHERE trip_time > now() - INTERVAL '180 days'
    GROUP BY equipment_affected
)
SELECT 
    tc.equipment_affected,
    tc.trip_count,
    ROUND(COALESCE(mtbf.mtbf_days, 0), 2) AS mtbf_days,
    ROUND(COALESCE(mttr.mttr_minutes, 0), 2) AS mttr_minutes,
    ROUND(COALESCE(tc.total_loss_mw, 0), 2) AS total_loss_mw,
    -- Overall Equipment Effectiveness (simplified)
    ROUND(100.0 * (1 - (tc.trip_count * COALESCE(mttr.mttr_minutes, 0) / (180.0 * 24 * 60))), 2) AS availability_pct
FROM trip_counts tc
LEFT JOIN mtbf ON tc.equipment_affected = mtbf.equipment_affected
LEFT JOIN mttr ON tc.equipment_affected = mttr.equipment_affected
ORDER BY availability_pct DESC;

-- Sample output:
equipment_affected | trip_count | mtbf_days | mttr_minutes | total_loss_mw | availability_pct
-------------------+------------+-----------+--------------+---------------+-----------------
COMPRESSOR_02      |          3 |     45.33 |        25.50 |           0.0 |            99.97
TURBINE_01         |         12 |      8.75 |        65.25 |        1352.5 |            99.70
PUMP_03            |         25 |      3.20 |        15.50 |           0.0 |            99.85
BOILER_A           |          8 |     12.50 |       145.75 |           0.0 |            99.55
```

---

## 6. Shift-Wise Analytics

### 6.1 Shift Calendar Implementation

**Database Extension** (add to OPERATIONAL_HARDENING.sql or new migration):

```sql
-- Shift calendar table (defines shift boundaries)
CREATE TABLE IF NOT EXISTS historian_meta.shift_calendar (
    shift_id SERIAL PRIMARY KEY,
    shift_name TEXT NOT NULL CHECK (shift_name IN ('DAY', 'EVENING', 'NIGHT')),
    shift_start_time TIME NOT NULL,
    shift_end_time TIME NOT NULL,
    days_of_week INTEGER[] NOT NULL CHECK (days_of_week <@ ARRAY[0,1,2,3,4,5,6]),
    timezone TEXT DEFAULT 'UTC'
);

-- Example shift definitions (8-hour shifts)
INSERT INTO historian_meta.shift_calendar 
    (shift_name, shift_start_time, shift_end_time, days_of_week)
VALUES 
    ('DAY', '06:00:00', '14:00:00', ARRAY[1,2,3,4,5,6,0]),     -- 6 AM - 2 PM, all days
    ('EVENING', '14:00:00', '22:00:00', ARRAY[1,2,3,4,5,6,0]), -- 2 PM - 10 PM, all days
    ('NIGHT', '22:00:00', '06:00:00', ARRAY[1,2,3,4,5,6,0]);   -- 10 PM - 6 AM, all days

-- Shift function (returns shift name for given timestamp)
CREATE OR REPLACE FUNCTION get_shift(ts TIMESTAMPTZ)
RETURNS TEXT AS $$
DECLARE
    v_time TIME;
    v_dow INTEGER;
    v_shift TEXT;
BEGIN
    v_time := ts::TIME;
    v_dow := EXTRACT(DOW FROM ts)::INTEGER;  -- 0=Sunday, 6=Saturday
    
    -- Handle overnight shifts (e.g., NIGHT shift 22:00-06:00)
    SELECT shift_name INTO v_shift
    FROM historian_meta.shift_calendar
    WHERE v_dow = ANY(days_of_week)
      AND (
          (shift_start_time < shift_end_time AND v_time BETWEEN shift_start_time AND shift_end_time)
          OR (shift_start_time > shift_end_time AND (v_time >= shift_start_time OR v_time <= shift_end_time))
      )
    LIMIT 1;
    
    RETURN COALESCE(v_shift, 'UNKNOWN');
END;
$$ LANGUAGE plpgsql IMMUTABLE;

COMMENT ON FUNCTION get_shift(TIMESTAMPTZ) IS 
'Returns shift name (DAY/EVENING/NIGHT) for given timestamp.
Handles overnight shifts (e.g., 22:00-06:00 = NIGHT).
Used for shift-wise analytics queries.';
```

### 6.2 Shift-Wise Trip Analysis

**Query**: Trip count by shift

```sql
-- Trip count by shift (last 30 days)
SELECT 
    get_shift(trip_time) AS shift,
    COUNT(*) AS trip_count,
    AVG(trip_duration_seconds) / 60.0 AS avg_downtime_minutes,
    SUM(production_loss_mw) AS total_loss_mw
FROM historian_raw.trip_event_tracking
WHERE trip_time > now() - INTERVAL '30 days'
GROUP BY get_shift(trip_time)
ORDER BY trip_count DESC;

-- Sample output:
shift   | trip_count | avg_downtime_minutes | total_loss_mw
--------+------------+---------------------+--------------
NIGHT   |         18 |                45.5 |         540.0
DAY     |         12 |                32.3 |         360.0
EVENING |          8 |                28.7 |         240.0
```

**Insights**:
- **More trips on NIGHT shift**: Possible operator fatigue, reduced supervision
- **Longer downtime on NIGHT shift**: Slower response time (fewer staff)
- **Action**: Increase night shift staffing, improve lighting, reduce operator workload

### 6.3 Shift-Wise Alarm Response Time

**Query**: Alarm acknowledgment time by shift

```sql
-- Alarm response time by shift (last 7 days)
SELECT 
    get_shift(time) AS shift,
    alarm_priority,
    COUNT(*) AS alarm_count,
    AVG(EXTRACT(EPOCH FROM (acknowledged_at - time))/60) AS avg_response_minutes,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (acknowledged_at - time))/60) AS median_response_minutes
FROM historian_raw.historian_events
WHERE event_type LIKE 'ALARM_%'
  AND alarm_state = 'ACKNOWLEDGED'
  AND time > now() - INTERVAL '7 days'
GROUP BY get_shift(time), alarm_priority
ORDER BY shift, alarm_priority DESC;

-- Sample output:
shift   | alarm_priority | alarm_count | avg_response_minutes | median_response_minutes
--------+----------------+-------------+---------------------+------------------------
DAY     |              5 |          12 |                 2.1 |                     1.5
DAY     |              4 |          35 |                 6.8 |                     5.2
EVENING |              5 |           8 |                 3.5 |                     2.8
EVENING |              4 |          28 |                 9.2 |                     7.5
NIGHT   |              5 |          15 |                 5.2 |                     4.1
NIGHT   |              4 |          42 |                15.3 |                    12.8
```

**Findings**:
- **NIGHT shift**: Slower response times (5.2 min vs 2.1 min for critical alarms)
- **Action**: Add 2nd operator on night shift, implement escalation alerts

### 6.4 Shift Performance Scorecard

**Query**: Comprehensive shift comparison

```sql
-- Shift performance scorecard (last 30 days)
WITH shift_stats AS (
    SELECT 
        get_shift(trip_time) AS shift,
        COUNT(*) AS trip_count,
        SUM(trip_duration_seconds) / 3600.0 AS total_downtime_hours,
        SUM(production_loss_mw) AS total_loss_mw
    FROM historian_raw.trip_event_tracking
    WHERE trip_time > now() - INTERVAL '30 days'
    GROUP BY get_shift(trip_time)
),
alarm_stats AS (
    SELECT 
        get_shift(time) AS shift,
        COUNT(*) FILTER (WHERE alarm_priority >= 4) AS critical_alarms,
        AVG(EXTRACT(EPOCH FROM (acknowledged_at - time))/60) AS avg_response_minutes
    FROM historian_raw.historian_events
    WHERE event_type LIKE 'ALARM_%'
      AND time > now() - INTERVAL '30 days'
    GROUP BY get_shift(time)
)
SELECT 
    ss.shift,
    ss.trip_count,
    ROUND(ss.total_downtime_hours, 2) AS total_downtime_hours,
    ROUND(ss.total_loss_mw, 2) AS total_loss_mw,
    COALESCE(als.critical_alarms, 0) AS critical_alarms,
    ROUND(COALESCE(als.avg_response_minutes, 0), 2) AS avg_alarm_response_minutes,
    -- Overall shift performance score (lower is better)
    ROUND((ss.trip_count * 10) + (ss.total_downtime_hours * 5) + (COALESCE(als.avg_response_minutes, 0) * 2), 2) AS performance_penalty_score
FROM shift_stats ss
LEFT JOIN alarm_stats als ON ss.shift = als.shift
ORDER BY performance_penalty_score ASC;

-- Sample output:
shift   | trip_count | total_downtime_hours | total_loss_mw | critical_alarms | avg_alarm_response_minutes | performance_penalty_score
--------+------------+----------------------+---------------+-----------------+---------------------------+---------------------------
DAY     |         12 |                 6.48 |        360.00 |              47 |                       5.20 |                    162.80
EVENING |          8 |                 3.83 |        240.00 |              36 |                       7.50 |                    114.15
NIGHT   |         18 |                13.65 |        540.00 |              57 |                      12.80 |                    274.85
```

---

## 7. Maintenance Procedures

### 7.1 Daily Tasks

**Task 1: Check Retention Health** (Run at 6 AM)
```sql
-- Daily retention health check
SELECT * FROM check_retention_health();

-- If warnings present:
-- 1. Review compression status (ensure TimescaleDB compression job running)
-- 2. Check disk space (df -h)
-- 3. Manually compress old chunks if needed:
SELECT compress_chunk(i) FROM show_chunks('historian_raw.historian_timeseries', older_than => INTERVAL '7 days') i;
```

**Task 2: Cleanup Old Events** (Run at 2 AM)
```sql
-- Daily event cleanup
SELECT * FROM cleanup_old_events();

-- Review results (7 rows returned):
-- - SYSTEM/WRITER: Should show deletions if >30 days old data exists
-- - AUDIT: Should always show 0 deletions (never deleted)
-- - TRIP_EVENTS/INTERLOCK_STATES: Check 7-year retention enforced
```

**Task 3: Active Alarm Summary** (Run at start of each shift)
```sql
-- Shift handover alarm report
SELECT 
    alarm_priority,
    COUNT(*) AS active_count,
    STRING_AGG(tag_id || ' (' || ROUND(EXTRACT(EPOCH FROM (now() - time))/60, 1) || ' min)', ', ') AS alarms
FROM historian_raw.vw_active_alarms
GROUP BY alarm_priority
ORDER BY alarm_priority DESC;
```

### 7.2 Weekly Tasks

**Task 1: Bypass Compliance Audit** (Run Friday 5 PM)
```sql
-- Weekly bypass audit report
SELECT 
    interlock_tag_id,
    event_time,
    bypass_authorized_by,
    bypass_reason,
    bypass_expires_at,
    CASE 
        WHEN bypass_expires_at < now() THEN 'EXPIRED'
        WHEN EXTRACT(EPOCH FROM (bypass_expires_at - event_time))/3600 > 4 THEN 'LONG_DURATION'
        ELSE 'ACCEPTABLE'
    END AS status
FROM historian_raw.interlock_state_tracking
WHERE interlock_state = 'BYPASSED'
  AND event_time > now() - INTERVAL '7 days'
ORDER BY status, event_time DESC;

-- Export to CSV for safety committee review
```

**Task 2: Chattering Alarm Review** (Run Monday 9 AM)
```sql
-- Identify chattering alarms (last 7 days)
-- [Use query from Section 3.2]

-- Action items:
-- 1. Export list to operations team
-- 2. Schedule alarm tuning for top 5 offenders
-- 3. Update alarm suppression schedules if needed
```

**Task 3: MTBF/MTTR Trending** (Run Wednesday 2 PM)
```sql
-- Generate reliability trend report
-- [Use queries from Section 5]

-- Actions:
-- 1. Identify equipment with declining MTBF (increasing trip frequency)
-- 2. Schedule preventive maintenance for POOR-rated equipment
-- 3. Review root cause for repeat trips (same root_cause_tag_id)
```

### 7.3 Monthly Tasks

**Task 1: Schema Version Audit** (Run 1st of month)
```sql
-- Check schema version consistency
SELECT get_schema_version();

-- Expected: 2 (operational_hardening)

-- Review migration history
SELECT * FROM historian_meta.schema_migrations ORDER BY applied_at DESC;
```

**Task 2: Trip Causality Review** (Run 5th of month)
```sql
-- Monthly trip causality review meeting
-- Agenda:
-- 1. Top 10 costliest trips (production loss)
-- 2. Fast escalation trips (<5 seconds alarm-to-trip)
-- 3. Trips with no initiating_alarm_id (missing correlation)
-- 4. Action items: Root cause elimination, alarm tuning

-- [Use queries from Section 2]
```

**Task 3: Database Vacuum & Reindex** (Run 15th of month, 2 AM)
```sql
-- Vacuum analyze (reclaim space, update statistics)
VACUUM ANALYZE historian_raw.historian_timeseries;
VACUUM ANALYZE historian_raw.historian_events;
VACUUM ANALYZE historian_raw.trip_event_tracking;

-- Reindex (rebuild indexes for performance)
REINDEX TABLE historian_raw.historian_timeseries;
REINDEX TABLE historian_raw.historian_events;
```

### 7.4 Quarterly Tasks

**Task 1: Compression Review** (Run 1st of quarter)
```sql
-- Check compression effectiveness
SELECT 
    hypertable_name,
    COUNT(*) AS total_chunks,
    COUNT(*) FILTER (WHERE compression_status = 'Compressed') AS compressed_chunks,
    ROUND(100.0 * COUNT(*) FILTER (WHERE compression_status = 'Compressed') / COUNT(*), 2) AS compression_pct,
    pg_size_pretty(SUM(uncompressed_total_bytes)) AS uncompressed_size,
    pg_size_pretty(SUM(compressed_total_bytes)) AS compressed_size,
    ROUND(SUM(uncompressed_total_bytes)::NUMERIC / NULLIF(SUM(compressed_total_bytes), 0), 2) AS compression_ratio
FROM timescaledb_information.chunks
WHERE hypertable_name IN ('historian_timeseries', 'historian_events')
GROUP BY hypertable_name;

-- Target: >80% compression coverage, >10x compression ratio for timeseries
```

**Task 2: Alarm Rationalization Workshop** (Run 2nd month of quarter)
```
1. Generate nuisance alarm report (Section 3.3)
2. Schedule 4-hour workshop with operations team
3. Review each nuisance alarm:
   - Keep & tune setpoint
   - Downgrade priority
   - Remove (if non-actionable)
4. Implement approved changes
5. Monitor for 30 days
```

---

## 8. Performance Tuning

### 8.1 Index Optimization

**Check Index Usage**:
```sql
-- Identify unused indexes (candidates for removal)
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan AS index_scans,
    idx_tup_read AS tuples_read,
    idx_tup_fetch AS tuples_fetched,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE schemaname = 'historian_raw'
  AND idx_scan = 0
  AND indexname NOT LIKE '%_pkey'  -- Exclude primary keys
ORDER BY pg_relation_size(indexrelid) DESC;

-- If index unused for >90 days and large (>100MB), consider dropping:
-- DROP INDEX IF EXISTS historian_raw.unused_index_name;
```

**Check Missing Indexes**:
```sql
-- Identify slow queries (missing indexes?)
SELECT 
    query,
    calls,
    mean_exec_time,
    total_exec_time,
    ROUND((100 * total_exec_time / SUM(total_exec_time) OVER())::NUMERIC, 2) AS pct_total_time
FROM pg_stat_statements
WHERE query NOT LIKE '%pg_stat%'
  AND mean_exec_time > 100  -- Queries taking >100ms avg
ORDER BY mean_exec_time DESC
LIMIT 20;

-- Analyze slow queries with EXPLAIN ANALYZE
EXPLAIN ANALYZE SELECT ...;
```

### 8.2 Query Optimization Examples

**Slow Query**: Trip causality with full table scan
```sql
-- BEFORE (slow: full table scan on historian_events)
SELECT * FROM historian_raw.vw_trip_causality
WHERE trip_time > '2025-01-01'
  AND alarm_priority >= 4;

-- Execution time: 2500ms

-- AFTER (add composite index)
CREATE INDEX idx_events_time_priority ON historian_raw.historian_events(time DESC, alarm_priority DESC)
WHERE event_type LIKE 'ALARM_%';

-- Execution time: 80ms (31x faster)
```

**Slow Query**: Alarm response time aggregation
```sql
-- BEFORE (inefficient: multiple passes over data)
SELECT 
    alarm_priority,
    AVG(response_time_minutes),
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY response_time_minutes)
FROM (
    SELECT 
        alarm_priority,
        EXTRACT(EPOCH FROM (acknowledged_at - time))/60 AS response_time_minutes
    FROM historian_raw.historian_events
    WHERE alarm_state = 'ACKNOWLEDGED'
      AND time > now() - INTERVAL '7 days'
) sub
GROUP BY alarm_priority;

-- Execution time: 850ms

-- AFTER (materialized view, refreshed hourly)
CREATE MATERIALIZED VIEW historian_raw.mv_alarm_response_stats AS
SELECT 
    DATE_TRUNC('hour', time) AS hour,
    alarm_priority,
    COUNT(*) AS alarm_count,
    AVG(EXTRACT(EPOCH FROM (acknowledged_at - time))/60) AS avg_response_minutes,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (acknowledged_at - time))/60) AS median_response_minutes
FROM historian_raw.historian_events
WHERE event_type LIKE 'ALARM_%'
  AND alarm_state = 'ACKNOWLEDGED'
GROUP BY DATE_TRUNC('hour', time), alarm_priority;

CREATE INDEX idx_mv_alarm_response_hour ON mv_alarm_response_stats(hour DESC, alarm_priority DESC);

-- Refresh hourly via pg_cron
SELECT cron.schedule('refresh-alarm-response-stats', '0 * * * *', 
    'REFRESH MATERIALIZED VIEW historian_raw.mv_alarm_response_stats');

-- Query materialized view (fast)
SELECT * FROM historian_raw.mv_alarm_response_stats
WHERE hour > now() - INTERVAL '7 days';

-- Execution time: 15ms (56x faster)
```

### 8.3 Connection Pooling

**C# Configuration** (appsettings.json):
```json
{
  "ConnectionStrings": {
    "Historian": "Host=localhost;Database=Cereveate;Username=cereveate;Password=cereveate@222;Port=5432;Pooling=true;MinPoolSize=5;MaxPoolSize=50;ConnectionIdleLifetime=300;ConnectionPruningInterval=10"
  }
}
```

**Explanation**:
- **MinPoolSize=5**: Keep 5 connections open (avoid cold start latency)
- **MaxPoolSize=50**: Limit to 50 connections (prevent resource exhaustion)
- **ConnectionIdleLifetime=300**: Close idle connections after 5 minutes
- **ConnectionPruningInterval=10**: Check for idle connections every 10 seconds

---

## 9. Monitoring & Alerts

### 9.1 Key Metrics to Monitor

**Database Health**:
- Disk usage: <80% full (alert at 70%)
- Connection count: <40 active connections (alert at 35)
- Replication lag: <5 seconds (if using replication)
- Compression coverage: >80% (alert if <70%)

**Application Health**:
- Trip detection latency: <500ms (alert if >1000ms)
- Alarm correlation delay: <5 seconds (alert if >10s)
- Event logging queue depth: <1000 events (alert if >5000)
- OPC connection status: Connected (alert if disconnected >30s)

**Operational Metrics**:
- Active critical alarms: <5 (alert if >10)
- Unacknowledged alarms >15 min: <3 (alert if >5)
- Expired bypasses: 0 (immediate alert)
- Trips per day: <2 (alert if >5)

### 9.2 Automated Alerts (C# Implementation)

```csharp
public class HealthMonitoringService : BackgroundService
{
    private readonly IDbConnection _dbConnection;
    private readonly INotificationService _notificationService;
    
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            await CheckCriticalAlarms();
            await CheckExpiredBypasses();
            await CheckRetentionHealth();
            await CheckEventQueueDepth();
            
            await Task.Delay(TimeSpan.FromMinutes(5), stoppingToken);
        }
    }
    
    private async Task CheckCriticalAlarms()
    {
        var criticalAlarms = await _dbConnection.QueryAsync<Alarm>(@"
            SELECT * FROM historian_raw.vw_active_alarms
            WHERE alarm_priority = 5
              AND EXTRACT(EPOCH FROM (now() - time))/60 > 15
        ");
        
        if (criticalAlarms.Count() > 5)
        {
            await _notificationService.SendSMS(
                "+1-555-0100",  // Shift supervisor
                $"ALERT: {criticalAlarms.Count()} unacknowledged critical alarms (>15 min old)"
            );
        }
    }
    
    private async Task CheckExpiredBypasses()
    {
        var expiredBypasses = await _dbConnection.QueryAsync<Bypass>(@"
            SELECT * FROM historian_raw.vw_interlock_violations
            WHERE status = 'EXPIRED_BYPASS'
        ");
        
        if (expiredBypasses.Any())
        {
            await _notificationService.SendEmail(
                "safety_officer@plant.com",
                "SAFETY VIOLATION: Expired Interlock Bypasses",
                $"{expiredBypasses.Count()} bypasses expired without renewal"
            );
        }
    }
    
    private async Task CheckRetentionHealth()
    {
        var health = await _dbConnection.QuerySingleAsync<RetentionHealth>(@"
            SELECT * FROM check_retention_health()
        ");
        
        if (health.Status == "WARNING")
        {
            await _notificationService.SendEmail(
                "it_team@plant.com",
                "Database Health Warning",
                $"Retention health issues: {string.Join(", ", health.Warnings)}"
            );
        }
    }
}
```

### 9.3 Dashboard Widgets (Recommended)

**HMI/SCADA Dashboard**:
1. **Active Alarms Banner** (top of screen)
   - Priority 5: Red background, flashing
   - Priority 4: Orange background
   - Click to open alarm detail popup

2. **Equipment Status Grid**
   - RUNNING: Green
   - STOPPED: Gray
   - TRIPPED: Red flashing
   - Click to view trip history

3. **Shift Performance Score** (updated hourly)
   - Today's shift vs. yesterday same shift
   - Trips, downtime, alarm response time

4. **Reliability Trends** (updated daily)
   - MTBF/MTTR sparklines (last 30 days)
   - Equipment criticality color-coding

---

## 10. Future Enhancements

### 10.1 Shift Calendar (Immediate - 2 Hours)

**Status**: Schema designed (Section 6.1), ready to deploy

**Steps**:
1. Execute shift calendar SQL (Section 6.1)
2. Populate shift definitions (adjust times for plant)
3. Test `get_shift(ts)` function
4. Update analytics queries to use shift function
5. Add shift filter to HMI dashboards

**Benefits**:
- Shift performance comparison (identify weak shifts)
- Shift-wise alarm response time (training targets)
- Bypass tracking per shift (compliance audit)

### 10.2 OEE Calculator (2-3 Weeks)

**Overall Equipment Effectiveness (OEE) = Availability × Performance × Quality**

**Schema Extension**:
```sql
-- OEE tracking table
CREATE TABLE historian_raw.equipment_oee_hourly (
    oee_id BIGSERIAL PRIMARY KEY,
    hour TIMESTAMPTZ NOT NULL,
    equipment_id TEXT NOT NULL,
    availability_pct DOUBLE PRECISION,  -- Uptime / Total time
    performance_pct DOUBLE PRECISION,   -- Actual output / Rated output
    quality_pct DOUBLE PRECISION,       -- Good units / Total units
    oee_pct DOUBLE PRECISION GENERATED ALWAYS AS (availability_pct * performance_pct * quality_pct / 10000) STORED,
    total_downtime_minutes INTEGER,
    trip_count INTEGER,
    production_mw DOUBLE PRECISION,
    CONSTRAINT fk_equipment FOREIGN KEY (equipment_id) REFERENCES historian_meta.equipment_hierarchy(equipment_id)
);

CREATE INDEX idx_oee_hour ON equipment_oee_hourly(hour DESC, equipment_id);

COMMENT ON TABLE equipment_oee_hourly IS 
'Hourly OEE calculation per equipment.
Computed by: OEECalculatorService (C# background service).
Target OEE: 85% (world-class), 60% (industry average).';
```

**C# Implementation**:
```csharp
public class OEECalculatorService : BackgroundService
{
    // Run hourly, calculate OEE for previous hour
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            var lastHour = DateTime.UtcNow.AddHours(-1);
            var lastHourStart = new DateTime(lastHour.Year, lastHour.Month, lastHour.Day, lastHour.Hour, 0, 0);
            var lastHourEnd = lastHourStart.AddHours(1);
            
            await CalculateOEE("TURBINE_01", lastHourStart, lastHourEnd);
            
            await Task.Delay(TimeSpan.FromHours(1), stoppingToken);
        }
    }
    
    private async Task CalculateOEE(string equipmentId, DateTime startTime, DateTime endTime)
    {
        // Availability = (Total time - Downtime) / Total time
        var downtime = await GetDowntime(equipmentId, startTime, endTime);
        var availability = 100.0 * (3600 - downtime) / 3600;
        
        // Performance = Actual output / Rated output
        var actualOutput = await GetActualOutput(equipmentId, startTime, endTime);
        var ratedOutput = await GetRatedOutput(equipmentId);
        var performance = 100.0 * actualOutput / ratedOutput;
        
        // Quality = Good units / Total units (simplified: assume 100% for power plant)
        var quality = 100.0;
        
        // Insert OEE
        await _dbConnection.ExecuteAsync(@"
            INSERT INTO historian_raw.equipment_oee_hourly 
                (hour, equipment_id, availability_pct, performance_pct, quality_pct, 
                 total_downtime_minutes, production_mw)
            VALUES (@hour, @equipmentId, @availability, @performance, @quality, 
                    @downtime, @actualOutput)
        ", new { hour = startTime, equipmentId, availability, performance, quality, downtime, actualOutput });
    }
}
```

### 10.3 Alarm Cascade Detection (3-4 Weeks)

**Purpose**: Detect cascading alarms (one fault triggers multiple alarms)

**Algorithm**:
1. Group alarms within 5-second window
2. Identify primary alarm (first in sequence, highest priority)
3. Mark subsequent alarms as "CASCADED" (link to primary via `parent_alarm_id`)

**Benefits**:
- Reduce alarm noise (suppress cascaded alarms)
- Focus operator attention on root cause
- Improve alarm acknowledgment efficiency

### 10.4 Predictive Trip Detection (6-8 Weeks)

**Purpose**: Predict trips 30-60 seconds before they occur

**Approach**:
1. Train ML model on historical trip data
2. Features: Alarm sequences, tag value trends, equipment state
3. Deploy model as C# service
4. Raise "PREDICTIVE_TRIP_WARNING" alarm when trip probability >70%
5. Give operator 30-60 seconds to intervene

**Required Technologies**:
- ML.NET or Python scikit-learn
- Time-series feature engineering (rate of change, moving averages)
- Model retraining pipeline (monthly)

### 10.5 Advanced Trip Analytics (4-6 Weeks)

**Feature 1: Trip Chain Analysis**
- Detect trips that cause subsequent trips (domino effect)
- Visualize trip propagation graph (NetworkX or D3.js)
- Example: Turbine trip → Loss of power → Auxiliary equipment trips

**Feature 2: Seasonal Trip Patterns**
- Detect seasonal trends (more trips in summer due to cooling issues)
- Compare trip frequency: Winter vs. Summer vs. Monsoon
- Adjust preventive maintenance schedules accordingly

**Feature 3: Root Cause Ranking (Pareto Analysis)**
- 80/20 rule: 20% of root causes cause 80% of trips
- Focus maintenance on top 5 root causes
- Track improvement over time (trips eliminated per root cause fix)

---

## Appendix A: SQL Cheat Sheet

**Get current schema version**:
```sql
SELECT get_schema_version();
```

**Check active alarms**:
```sql
SELECT * FROM historian_raw.vw_active_alarms ORDER BY alarm_priority DESC LIMIT 20;
```

**Check recent trips**:
```sql
SELECT * FROM historian_raw.vw_trip_causality WHERE trip_time > now() - INTERVAL '24 hours';
```

**Check expired bypasses**:
```sql
SELECT * FROM historian_raw.vw_interlock_violations WHERE status = 'EXPIRED_BYPASS';
```

**Run retention cleanup**:
```sql
SELECT * FROM cleanup_old_events();
```

**Check retention health**:
```sql
SELECT * FROM check_retention_health();
```

**Get shift for timestamp**:
```sql
SELECT get_shift('2025-12-22 14:30:00+00'::TIMESTAMPTZ);  -- Returns 'EVENING'
```

---

## Appendix B: Troubleshooting Guide

**Problem**: No trips detected despite equipment stops  
**Solution**: Check TripDetectionService logs, verify alarm tags configured correctly, ensure equipment run status tags exist

**Problem**: Alarm correlation missing (initiating_alarm_id = NULL)  
**Solution**: Verify AlarmTripCorrelationService running, check 5-second correlation window sufficient, review alarm history at trip time

**Problem**: High event logging latency  
**Solution**: Check EventLoggingService queue depth, increase batch size, reduce rate limiting windows

**Problem**: Compression not working  
**Solution**: Verify TimescaleDB compression policy active (`SELECT * FROM timescaledb_information.jobs`), manually compress old chunks

**Problem**: Slow queries  
**Solution**: Run EXPLAIN ANALYZE, check index usage, consider materialized views for complex aggregations

---

**Document Status**: Production Operations Guide  
**Deployment Status**: Ready for production (after PART 1 deployed + PART 2 services implemented)  
**Next Steps**: Deploy shift calendar (2 hours), implement OEE calculator (2-3 weeks), train operations team on analytics dashboards

---

**END OF OPERATIONAL HARDENING DOCUMENTATION (3 PARTS)**

