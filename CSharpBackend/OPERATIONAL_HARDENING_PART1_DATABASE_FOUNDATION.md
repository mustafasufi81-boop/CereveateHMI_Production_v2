# OPERATIONAL HARDENING - PART 1: DATABASE FOUNDATION

## Document Overview
**Purpose**: Complete database schema documentation for operational hardening  
**Version**: 1.0  
**Date**: December 22, 2025  
**Status**: Production-Ready  
**Related Files**: OPERATIONAL_HARDENING.sql (1292 lines)

---

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Schema Extensions](#schema-extensions)
3. [Data Quality & Validation](#data-quality--validation)
4. [Alarm & Event System](#alarm--event-system)
5. [Trip & Interlock Tracking](#trip--interlock-tracking)
6. [Views & Analytics](#views--analytics)
7. [Functions & Procedures](#functions--procedures)
8. [Retention & Cleanup](#retention--cleanup)
9. [Deployment Guide](#deployment-guide)
10. [Verification Tests](#verification-tests)

---

## 1. Architecture Overview

### Design Philosophy
- **Database Role**: Storage + structure (NOT inference)
- **Application Role**: Intelligence + correlation (trip detection, state machines)
- **Industry Standard**: Matches OSIsoft PI, IP.21, Aspen InfoPlus architecture

### Three-Schema Architecture
```
historian_meta   (Configuration & Metadata)
    ├── tag_master (extended with trip/interlock semantics)
    ├── data_quality_limits (configurable thresholds)
    ├── alarm_suppression_schedule (time-based suppression)
    ├── writer_checkpoint (mapping version tracking)
    └── schema_migrations (version control)

historian_raw    (Time-Series Data & Events)
    ├── historian_timeseries (hypertable, 4-hour chunks)
    ├── historian_latest_value (current tag values)
    ├── historian_events (unified event/alarm table)
    ├── trip_event_tracking (7-year retention, safety compliance)
    └── interlock_state_tracking (7-year retention, audit trail)

historian_mon    (System Health Monitoring)
    ├── system_metrics (performance tracking)
    ├── wal_monitoring (replication health)
    └── retention_health (compression & cleanup status)
```

### Key Design Decisions
1. **Combined Events + Alarms**: Single table reduces joins, validated for <10K alarms/day
2. **Trip/Interlock First-Class Citizens**: Not inferred from tags, explicit tracking
3. **7-Year Safety Retention**: Trips, interlocks, audit events (regulatory compliance)
4. **Causality via Foreign Keys**: `initiating_alarm_id`, `root_cause_tag_id`, `related_trip_event_id`
5. **Rate-Limited Logging**: Prevents event flood during system malfunction
6. **Smart Truncation**: Accept data, truncate extremes, never reject ingestion

---

## 2. Schema Extensions

### 2.1 Tag Master Trip/Interlock Extensions

**Purpose**: Semantic tagging for trip and interlock logic

```sql
ALTER TABLE historian_meta.tag_master
    ADD COLUMN trip_category TEXT CHECK (
        trip_category IN ('PROCESS_TRIP', 'SAFETY_TRIP', 'EMERGENCY_TRIP', 'INTERLOCK', NULL)
    ),
    ADD COLUMN interlock_type TEXT CHECK (
        interlock_type IN ('PERMISSIVE', 'CONDITIONAL', 'SEQUENTIAL', 'PROTECTIVE', NULL)
    ),
    ADD COLUMN equipment_criticality INTEGER CHECK (equipment_criticality BETWEEN 1 AND 5),
    ADD COLUMN is_trip_initiator BOOLEAN DEFAULT FALSE,
    ADD COLUMN associated_equipment TEXT;
```

**Trip Categories**:
- **PROCESS_TRIP**: Normal shutdown (e.g., low load trip, scheduled stop)
- **SAFETY_TRIP**: Hazard prevention (e.g., high pressure, overspeed)
- **EMERGENCY_TRIP**: Immediate stop (e.g., fire detection, manual E-stop)
- **INTERLOCK**: Condition-based logic (not a trip itself, but enables/prevents)

**Interlock Types**:
- **PERMISSIVE**: Must be TRUE to start equipment (e.g., lube oil pressure OK before turbine start)
- **CONDITIONAL**: Must stay TRUE while running (e.g., cooling water flow during operation)
- **SEQUENTIAL**: Order dependency (e.g., start boiler feed pump before opening valves)
- **PROTECTIVE**: Fault protection (e.g., bearing temperature < 90°C to run)

**Equipment Criticality** (1-5 scale):
- **1 (Low)**: Maintenance mode, non-critical auxiliary
- **2 (Medium)**: Isolated systems, backup equipment
- **3 (High)**: Key production equipment (pumps, compressors)
- **4 (Urgent)**: Main production units (turbines, generators)
- **5 (Critical)**: Safety systems (fire protection, emergency shutdown)

**Usage Example**:
```sql
-- Tag TURBINE_OVERSPEED_TRIP as safety trip initiator
UPDATE historian_meta.tag_master
SET 
    trip_category = 'SAFETY_TRIP',
    is_trip_initiator = TRUE,
    equipment_criticality = 5,
    associated_equipment = 'TURBINE_01'
WHERE tag_id = 'TURBINE_OVERSPEED_TRIP';

-- Tag LUBE_OIL_PRESSURE as permissive interlock
UPDATE historian_meta.tag_master
SET 
    trip_category = 'INTERLOCK',
    interlock_type = 'PERMISSIVE',
    equipment_criticality = 4,
    associated_equipment = 'TURBINE_01'
WHERE tag_id = 'LUBE_OIL_PRESSURE_OK';
```

### 2.2 Data Quality Limits Configuration

**Purpose**: Configurable validation thresholds (no code changes required)

**Table**: `historian_meta.data_quality_limits`

| Column | Type | Description |
|--------|------|-------------|
| setting_name | TEXT (PK) | Limit identifier |
| setting_value | INTEGER | Numeric threshold |
| description | TEXT | Human-readable purpose |
| updated_at | TIMESTAMPTZ | Last change timestamp |
| updated_by | TEXT | User who modified |

**Default Limits**:
```sql
setting_name                | setting_value | description
---------------------------+---------------+--------------------------------------------
value_text_max_length       | 1000         | Max chars for value_text (truncate beyond)
value_text_warn_length      | 500          | Warn threshold (no truncation)
log_cooldown_seconds        | 300          | Min seconds between duplicate warnings
warn_log_cooldown_seconds   | 1800         | Min seconds between size warnings
```

**Adjustment Examples**:
```sql
-- Increase truncation limit to 2000 chars
UPDATE historian_meta.data_quality_limits 
SET setting_value = 2000, updated_by = 'admin', updated_at = now()
WHERE setting_name = 'value_text_max_length';

-- Reduce log cooldown to 60 seconds (more frequent warnings)
UPDATE historian_meta.data_quality_limits 
SET setting_value = 60, updated_by = 'admin', updated_at = now()
WHERE setting_name = 'log_cooldown_seconds';
```

### 2.3 Sample Source Extension

**Before**: `sample_source CHAR(3)` (limited to 3 chars: OPC, SIM, API)  
**After**: `sample_source VARCHAR(10)` (supports: OPC, MANUAL, CALC, SIM, API, BACKFILL, etc.)

**Impact**: More flexible data provenance tracking

---

## 3. Data Quality & Validation

### 3.1 Smart Truncation Trigger

**Function**: `validate_timeseries_sample()`  
**Trigger**: `trg_validate_timeseries_sample` (BEFORE INSERT)

**Philosophy**: **Accept First, Validate Second** (never reject ingestion)

**Behavior**:
1. **Oversized Text** (>1000 chars):
   - Truncate to 1000 chars (keep first 1000)
   - Set `quality = 'U'` (Uncertain - data modified)
   - Log warning **ONCE per 5 minutes per tag** (rate limiting)
   - Prevents: 86,400 warnings/day → 288 warnings/day (99.7% reduction)

2. **Large Text Warning** (>500 chars):
   - Accept without truncation
   - Log warning **ONCE per 30 minutes per tag**
   - Alert operators to check PLC configuration

3. **Invalid Numeric** (NaN, Infinity):
   - Accept value
   - Set `quality = 'B'` (Bad)
   - Log warning **ONCE per 5 minutes per tag**

**Rate Limiting Logic**:
```sql
-- Check last log time for this tag
SELECT MAX(time) INTO v_last_logged
FROM historian_raw.historian_events
WHERE tag_id = NEW.tag_id 
  AND event_type = 'DATA_QUALITY_WARNING'
  AND message LIKE 'Oversized value_text%'
  AND time > now() - v_log_cooldown;

-- Only log if cooldown expired
IF v_last_logged IS NULL THEN
    INSERT INTO historian_raw.historian_events (...)
END IF;
```

**Storage Impact Example**:
```
PLC malfunction: 50KB garbage string every second

Without truncation:
- 50KB × 86,400 samples/day = 4.3 GB/day
- 86,400 warning events/day = event log flood

With smart truncation:
- 1KB × 86,400 samples/day = 86 MB/day (98% reduction)
- 288 warning events/day (rate limited)
- System keeps running (no crash)
```

### 3.2 Duplicate Handling

**Constraint**: `UNIQUE (time, tag_id)` on `historian_timeseries`

**Strategy**: Last-write-wins (ON CONFLICT DO UPDATE)

**C# Writer Usage**:
```csharp
// In HistorianIngestHostedService.cs
await using var writer = conn.BeginBinaryImport(@"
    COPY historian_raw.historian_timeseries 
    FROM STDIN BINARY
    ON CONFLICT (time, tag_id) DO UPDATE SET
        value_num = EXCLUDED.value_num,
        value_text = EXCLUDED.value_text,
        value_bool = EXCLUDED.value_bool,
        quality = EXCLUDED.quality,
        mapping_version = EXCLUDED.mapping_version
");
```

**Impact**: Prevents data inflation (same sample written 3x = 1 row, not 3)

---

## 4. Alarm & Event System

### 4.1 Extended Event Table

**Table**: `historian_raw.historian_events`

**Alarm Lifecycle Columns** (8 new columns):
```sql
ALTER TABLE historian_events
    ADD COLUMN alarm_state TEXT CHECK (
        alarm_state IN ('ACTIVE', 'ACKNOWLEDGED', 'CLEARED', 'SUPPRESSED')
    ),
    ADD COLUMN alarm_priority INTEGER CHECK (alarm_priority BETWEEN 1 AND 5),
    ADD COLUMN acknowledged_by TEXT,
    ADD COLUMN acknowledged_at TIMESTAMPTZ,
    ADD COLUMN cleared_at TIMESTAMPTZ,
    ADD COLUMN alarm_setpoint DOUBLE PRECISION,
    ADD COLUMN alarm_actual_value DOUBLE PRECISION,
    ADD COLUMN parent_alarm_id BIGINT REFERENCES historian_events(event_id);
```

**Alarm States**:
- **ACTIVE**: Just raised, requires operator attention
- **ACKNOWLEDGED**: Operator aware, investigating
- **CLEARED**: Condition normal, alarm resolved
- **SUPPRESSED**: Silenced by schedule (see `alarm_suppression_schedule`)

**Priority Levels**:
- **1 (Low)**: Informational, no action required
- **2 (Medium)**: Monitor, non-urgent response
- **3 (High)**: Respond within 15 minutes
- **4 (Urgent)**: Respond within 5 minutes
- **5 (Critical)**: Immediate response, safety risk

### 4.2 Event Type Taxonomy (ENFORCED)

**Constraint**: `chk_event_type` on `historian_events`

```sql
event_type ~ '^(SYSTEM|WRITER|DATA_QUALITY|ALARM|TRIP|USER|AUDIT)_[A-Z_0-9]+$'
```

**Event Domains** (per EVENT_ALARM_POLICY.md):

| Prefix | Purpose | Retention | Examples |
|--------|---------|-----------|----------|
| SYSTEM_* | Platform infrastructure | 30 days | SYSTEM_STARTUP, SYSTEM_SHUTDOWN |
| WRITER_* | Ingestion pipeline | 30 days | WRITER_BATCH_COMPLETE, WRITER_ERROR |
| DATA_QUALITY_* | Validation warnings | 90 days | DATA_QUALITY_TRUNCATED, DATA_QUALITY_NAN |
| ALARM_* | Process alarms | 3 years | ALARM_HIGH_HIGH, ALARM_LOW |
| TRIP_* | Trip events | 7 years | TRIP_INITIATED, TRIP_CLEARED |
| USER_* | Manual operator notes | 1 year | USER_COMMENT, USER_OVERRIDE |
| AUDIT_* | Compliance events | 7+ years (never deleted) | AUDIT_CONFIG_CHANGE, AUDIT_BYPASS |

**Valid Examples**:
```sql
'SYSTEM_STARTUP_COMPLETE'        -- ✅ Valid
'ALARM_HIGH_TEMPERATURE'         -- ✅ Valid
'TRIP_EMERGENCY_STOP_INITIATED'  -- ✅ Valid
'DATA_QUALITY_VALUE_TRUNCATED'   -- ✅ Valid

'CUSTOM_PREFIX_TEST'             -- ❌ Invalid (no CUSTOM prefix)
'alarm_low_pressure'             -- ❌ Invalid (lowercase)
'SYSTEM-START'                   -- ❌ Invalid (hyphen not allowed)
```

### 4.3 Alarm Suppression Schedule

**Table**: `historian_meta.alarm_suppression_schedule`

**Purpose**: Time-based alarm suppression (prevent nuisance alarms during known conditions)

**Schema**:
```sql
CREATE TABLE alarm_suppression_schedule (
    schedule_id SERIAL PRIMARY KEY,
    alarm_type_pattern TEXT NOT NULL,      -- Regex pattern (e.g., 'ALARM_LOW%')
    tag_id_pattern TEXT,                   -- Tag filter (NULL = all tags)
    suppress_start TIME NOT NULL,          -- Daily start time
    suppress_end TIME NOT NULL,            -- Daily end time
    days_of_week INTEGER[] NOT NULL,       -- [0-6] where 0=Sunday
    reason TEXT,                           -- Justification
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    enabled BOOLEAN DEFAULT TRUE
);
```

**Example: Night Shift Suppression**:
```sql
-- Suppress low alarms during night shift (operators absent)
INSERT INTO alarm_suppression_schedule 
    (alarm_type_pattern, suppress_start, suppress_end, days_of_week, reason, created_by)
VALUES 
    ('ALARM_LOW%', '00:00:00', '06:00:00', ARRAY[1,2,3,4,5], 
     'Night shift - operators absent, low alarms non-critical', 'plant_manager');
```

**Application Logic** (C# service must implement):
```csharp
// Check if alarm should be suppressed
bool IsAlarmSuppressed(string alarmType, string tagId, DateTime alarmTime)
{
    var schedule = GetActiveSuppressionSchedule(alarmType, tagId, alarmTime);
    if (schedule != null)
    {
        // Set alarm_state = 'SUPPRESSED' instead of 'ACTIVE'
        return true;
    }
    return false;
}
```

### 4.4 Alarm Acknowledgment Function

**Function**: `acknowledge_alarm(alarm_id, operator_name, notes)`

**Returns**: BOOLEAN (TRUE on success, FALSE if already acknowledged)

**Behavior**:
1. Validates alarm is in ACTIVE state (can't acknowledge CLEARED/SUPPRESSED)
2. Updates `alarm_state = 'ACKNOWLEDGED'`
3. Records `acknowledged_by` and `acknowledged_at`
4. Logs acknowledgment event (event_type = 'ALARM_ACKNOWLEDGED')
5. Links acknowledgment to original alarm via `parent_alarm_id`

**Usage Example**:
```sql
-- Operator acknowledges high temperature alarm
SELECT acknowledge_alarm(
    12345,  -- alarm_id from historian_events
    'operator_john',
    'Investigating furnace cooling system, checking pump status'
);

-- Returns: TRUE (success)
```

**Audit Trail**:
```sql
-- Check who acknowledged alarms in last 24 hours
SELECT 
    event_id AS alarm_id,
    time AS alarm_time,
    tag_id,
    event_type AS alarm_type,
    acknowledged_by,
    acknowledged_at,
    EXTRACT(EPOCH FROM (acknowledged_at - time))/60 AS response_time_minutes
FROM historian_raw.historian_events
WHERE alarm_state = 'ACKNOWLEDGED'
  AND acknowledged_at > now() - INTERVAL '24 hours'
ORDER BY acknowledged_at DESC;
```

---

## 5. Trip & Interlock Tracking

### 5.1 Trip Event Tracking Table

**Table**: `historian_raw.trip_event_tracking`

**Purpose**: Record all trip events with causality linkage for safety compliance

**Schema**:
```sql
CREATE TABLE trip_event_tracking (
    trip_event_id BIGSERIAL PRIMARY KEY,
    trip_time TIMESTAMPTZ NOT NULL,
    trip_tag_id TEXT NOT NULL REFERENCES tag_master(tag_id),
    trip_category TEXT NOT NULL CHECK (trip_category IN ('PROCESS_TRIP', 'SAFETY_TRIP', 'EMERGENCY_TRIP')),
    initiating_alarm_id BIGINT REFERENCES historian_events(event_id),  -- Causality link
    equipment_affected TEXT NOT NULL,
    trip_duration_seconds INTEGER,
    trip_cleared_at TIMESTAMPTZ,
    root_cause_tag_id TEXT REFERENCES tag_master(tag_id),
    operator_notes TEXT,
    automated_diagnosis JSONB,
    production_loss_mw DOUBLE PRECISION,
    metadata JSONB
);
```

**Key Relationships**:
- **trip_tag_id**: Which tag recorded the trip (e.g., 'TURBINE_TRIP_STATUS')
- **initiating_alarm_id**: Which alarm caused this trip (FK to historian_events)
- **root_cause_tag_id**: Actual problem tag (e.g., 'BEARING_TEMP' if overheating caused trip)
- **equipment_affected**: Equipment name (e.g., 'TURBINE_01', 'BOILER_A')

**Retention**: 7 years (safety compliance, regulatory requirement)

**Usage Example**:
```sql
-- Record turbine trip due to high bearing temperature
INSERT INTO historian_raw.trip_event_tracking 
    (trip_time, trip_tag_id, trip_category, equipment_affected, 
     initiating_alarm_id, root_cause_tag_id, production_loss_mw)
VALUES (
    '2025-12-22 14:35:22+00',
    'TURBINE_01_TRIP_STATUS',
    'SAFETY_TRIP',
    'TURBINE_01',
    45678,  -- alarm_id of ALARM_HIGH_BEARING_TEMP
    'TURBINE_01_BEARING_TEMP',
    270.5   -- MW lost during trip
);
```

**Indexes** (optimized for time-series queries):
```sql
CREATE INDEX idx_trip_event_time ON trip_event_tracking(trip_time DESC);
CREATE INDEX idx_trip_event_tag ON trip_event_tracking(trip_tag_id);
CREATE INDEX idx_trip_category ON trip_event_tracking(trip_category);
```

### 5.2 Interlock State Tracking Table

**Table**: `historian_raw.interlock_state_tracking`

**Purpose**: Track interlock state changes with bypass authorization audit

**Schema**:
```sql
CREATE TABLE interlock_state_tracking (
    interlock_event_id BIGSERIAL PRIMARY KEY,
    event_time TIMESTAMPTZ NOT NULL,
    interlock_tag_id TEXT NOT NULL REFERENCES tag_master(tag_id),
    interlock_type TEXT NOT NULL CHECK (interlock_type IN ('PERMISSIVE', 'CONDITIONAL', 'SEQUENTIAL', 'PROTECTIVE')),
    interlock_state TEXT NOT NULL CHECK (interlock_state IN ('SATISFIED', 'VIOLATED', 'BYPASSED', 'UNKNOWN')),
    previous_state TEXT,
    state_duration_seconds INTEGER,
    affected_equipment TEXT,
    bypass_reason TEXT,
    bypass_authorized_by TEXT,          -- WHO authorized bypass
    bypass_expires_at TIMESTAMPTZ,      -- WHEN bypass expires
    related_trip_event_id BIGINT REFERENCES trip_event_tracking(trip_event_id),
    metadata JSONB
);
```

**Interlock States**:
- **SATISFIED**: Condition met, equipment can operate
- **VIOLATED**: Condition not met, equipment should stop
- **BYPASSED**: Manually overridden (requires authorization)
- **UNKNOWN**: State indeterminate (sensor failure, startup)

**Bypass Authorization** (critical for compliance):
```sql
-- Record bypass with authorization
INSERT INTO interlock_state_tracking 
    (event_time, interlock_tag_id, interlock_type, interlock_state,
     affected_equipment, bypass_reason, bypass_authorized_by, bypass_expires_at)
VALUES (
    now(),
    'LUBE_OIL_PRESSURE_OK',
    'PERMISSIVE',
    'BYPASSED',
    'TURBINE_01',
    'Maintenance test - manual barring in progress',
    'maintenance_supervisor_jane',  -- WHO
    now() + INTERVAL '2 hours'      -- WHEN expires
);
```

**Retention**: 7 years (safety audit, regulatory compliance)

**Indexes**:
```sql
CREATE INDEX idx_interlock_event_time ON interlock_state_tracking(event_time DESC);
CREATE INDEX idx_interlock_tag ON interlock_state_tracking(interlock_tag_id);
CREATE INDEX idx_interlock_state ON interlock_state_tracking(interlock_state);
```

---

## 6. Views & Analytics

### 6.1 Active Alarms View (Operator Dashboard)

**View**: `historian_raw.vw_active_alarms`

**Purpose**: Real-time active alarm list (excludes cleared/suppressed)

```sql
CREATE OR REPLACE VIEW vw_active_alarms AS
SELECT 
    event_id AS alarm_id,
    time AS raised_at,
    tag_id,
    event_type AS alarm_type,
    alarm_priority,
    alarm_state,
    alarm_setpoint,
    alarm_actual_value,
    message AS alarm_message,
    acknowledged_by,
    acknowledged_at,
    EXTRACT(EPOCH FROM (COALESCE(cleared_at, now()) - time))/60 AS duration_minutes,
    CASE 
        WHEN cleared_at IS NULL THEN 'ONGOING'
        ELSE 'CLEARED'
    END AS status
FROM historian_raw.historian_events
WHERE event_type LIKE 'ALARM_%' 
  AND alarm_state IN ('ACTIVE', 'ACKNOWLEDGED')
ORDER BY alarm_priority DESC, time ASC;
```

**Usage** (Web UI, HMI):
```sql
-- Get top 10 active alarms (highest priority first)
SELECT * FROM historian_raw.vw_active_alarms LIMIT 10;

-- Count alarms by priority
SELECT alarm_priority, COUNT(*) AS alarm_count
FROM historian_raw.vw_active_alarms
GROUP BY alarm_priority
ORDER BY alarm_priority DESC;
```

### 6.2 Trip Causality View

**View**: `historian_raw.vw_trip_causality`

**Purpose**: Links trips → alarms → root causes for forensic analysis

```sql
CREATE OR REPLACE VIEW vw_trip_causality AS
SELECT 
    t.trip_event_id,
    t.trip_time,
    t.trip_tag_id,
    t.trip_category,
    t.equipment_affected,
    t.trip_duration_seconds,
    t.production_loss_mw,
    -- Initiating alarm details
    e.event_type AS initiating_alarm_type,
    e.time AS alarm_raised_at,
    EXTRACT(EPOCH FROM (t.trip_time - e.time)) AS alarm_to_trip_seconds,  -- Time gap
    e.tag_id AS alarm_tag_id,
    e.alarm_priority AS alarm_priority,
    -- Root cause
    t.root_cause_tag_id,
    tm.tag_name AS root_cause_tag_name,
    tm.equipment_criticality AS root_cause_criticality,
    -- Operator response
    t.operator_notes,
    t.automated_diagnosis
FROM historian_raw.trip_event_tracking t
LEFT JOIN historian_raw.historian_events e ON t.initiating_alarm_id = e.event_id
LEFT JOIN historian_meta.tag_master tm ON t.root_cause_tag_id = tm.tag_id
ORDER BY t.trip_time DESC;
```

**Analytics Examples**:
```sql
-- Find trips with <5 seconds alarm-to-trip time (fast escalation)
SELECT * FROM vw_trip_causality
WHERE alarm_to_trip_seconds < 5;

-- Total production loss by equipment (last 30 days)
SELECT 
    equipment_affected,
    COUNT(*) AS trip_count,
    SUM(production_loss_mw) AS total_loss_mw,
    AVG(trip_duration_seconds)/60 AS avg_duration_minutes
FROM vw_trip_causality
WHERE trip_time > now() - INTERVAL '30 days'
GROUP BY equipment_affected
ORDER BY total_loss_mw DESC;
```

### 6.3 Interlock Violations View

**View**: `historian_raw.vw_interlock_violations`

**Purpose**: Active violations and bypass audit trail

```sql
CREATE OR REPLACE VIEW vw_interlock_violations AS
SELECT 
    interlock_event_id,
    event_time,
    interlock_tag_id,
    interlock_type,
    interlock_state,
    state_duration_seconds,
    affected_equipment,
    bypass_reason,
    bypass_authorized_by,
    bypass_expires_at,
    related_trip_event_id,
    CASE 
        WHEN interlock_state = 'BYPASSED' AND bypass_expires_at < now() THEN 'EXPIRED_BYPASS'
        WHEN interlock_state = 'BYPASSED' THEN 'ACTIVE_BYPASS'
        WHEN interlock_state = 'VIOLATED' THEN 'VIOLATION'
        ELSE 'NORMAL'
    END AS status
FROM historian_raw.interlock_state_tracking
WHERE interlock_state IN ('VIOLATED', 'BYPASSED')
ORDER BY event_time DESC;
```

**Compliance Queries**:
```sql
-- Find expired bypasses (safety violation)
SELECT * FROM vw_interlock_violations
WHERE status = 'EXPIRED_BYPASS';

-- Bypass audit: Who bypassed interlocks this month?
SELECT 
    bypass_authorized_by,
    COUNT(*) AS bypass_count,
    STRING_AGG(DISTINCT affected_equipment, ', ') AS equipment_list
FROM vw_interlock_violations
WHERE interlock_state = 'BYPASSED'
  AND event_time > date_trunc('month', now())
GROUP BY bypass_authorized_by
ORDER BY bypass_count DESC;
```

### 6.4 Additional Views

**System Events**: `vw_system_events` (IT monitoring)  
**Data Quality**: `vw_data_quality` (process engineers)  
**Audit Trail**: `vw_audit_trail` (compliance)  
**Events Timeline**: `vw_events_timeline` (root cause analysis)

---

## 7. Functions & Procedures

### 7.1 Latest Value Update (Precedence Rules)

**Function**: `update_latest_values_batch()`

**Purpose**: Update `historian_latest_value` with precedence logic

**Precedence Rules**:
1. **Newer timestamp wins** (most recent data)
2. **Newer mapping version wins** (same timestamp)
3. **Good quality wins** (same timestamp + version)

**Usage** (C# HistorianIngestHostedService):
```csharp
await conn.ExecuteAsync(@"
    SELECT update_latest_values_batch(
        @tagIds, @times, @valueNums, @valueTexts, 
        @valueBools, @qualities, @mappingVersions
    )", new { 
        tagIds, times, valueNums, valueTexts, 
        valueBools, qualities, mappingVersions 
    });
```

### 7.2 Mapping Version Validation

**Function**: `validate_writer_mapping_version(writer_name, current_version)`

**Returns**: (is_valid BOOLEAN, message TEXT, latest_version BIGINT)

**Purpose**: Detect stale tag mappings (writer using old configuration)

**Thresholds**:
- Lag ≤5 versions: Acceptable (returns TRUE)
- Lag >5 versions: Reload required (returns FALSE)

**Usage**:
```sql
SELECT * FROM validate_writer_mapping_version('HistorianIngestService', 42);

-- Result:
is_valid | message                                                  | latest_version
---------+----------------------------------------------------------+---------------
FALSE    | Writer using STALE mapping v42 (latest: v50, lag: 8...) | 50
```

### 7.3 Retention Health Check

**Function**: `check_retention_health()`

**Returns**: (status, oldest_data_age_days, compression_coverage_pct, total_size_mb, warnings[])

**Purpose**: Monitor TimescaleDB compression and retention

**Checks**:
- Data age >730 days (retention policy violation)
- Compression coverage <80% (disk usage concern)
- Total size >100GB (alert threshold)

**Usage** (schedule daily via pg_cron):
```sql
-- Manual check
SELECT * FROM check_retention_health();

-- Automated schedule (pg_cron)
SELECT cron.schedule('retention-health-check', '0 6 * * *', 
    'SELECT * FROM check_retention_health()');
```

### 7.4 Event Cleanup (Retention Enforcement)

**Function**: `cleanup_old_events()`

**Returns**: MULTIPLE ROWS (7 per execution) - one for each event category

**Retention Policy**:
```
SYSTEM/WRITER:      30 days
DATA_QUALITY:       90 days
USER:               1 year (365 days)
ALARM:              3 years (1095 days)
AUDIT:              Never deleted (7+ years)
TRIP_EVENTS:        7 years (2555 days)
INTERLOCK_STATES:   7 years (2555 days)
```

**Returns Example**:
```sql
SELECT * FROM cleanup_old_events();

event_type_prefix | deleted_count | retention_days
------------------+---------------+---------------
SYSTEM/WRITER     |           234 |             30
DATA_QUALITY      |            67 |             90
USER              |            12 |            365
ALARM             |           445 |           1095
AUDIT             |             0 |           2555  (never deleted)
TRIP_EVENTS       |             3 |           2555
INTERLOCK_STATES  |             1 |           2555
```

**Schedule** (run daily):
```sql
-- TimescaleDB job
SELECT add_job('cleanup_old_events', '1 day');

-- OR pg_cron
SELECT cron.schedule('event-cleanup', '0 2 * * *', 
    'SELECT * FROM cleanup_old_events()');
```

---

## 8. Retention & Cleanup

### 8.1 Retention Summary

| Data Type | Retention | Compression | Rationale |
|-----------|-----------|-------------|-----------|
| Time-series data | 2 years | Yes (after 1 week) | Operational analysis |
| SYSTEM/WRITER events | 30 days | No | Infrastructure logs |
| DATA_QUALITY events | 90 days | No | Validation tracking |
| USER events | 1 year | No | Operator notes |
| ALARM events | 3 years | Yes (after 1 month) | Process analysis |
| AUDIT events | 7+ years (never deleted) | Yes | Compliance |
| TRIP events | 7 years | Yes | Safety compliance |
| INTERLOCK states | 7 years | Yes | Safety audit |

### 8.2 Compression Strategy

**TimescaleDB Compression Policy**:
```sql
-- Compress chunks older than 1 week
SELECT add_compression_policy('historian_timeseries', INTERVAL '7 days');

-- Compress historian_events chunks older than 1 month
SELECT add_compression_policy('historian_events', INTERVAL '30 days');
```

**Expected Compression Ratios**:
- Time-series data: 10-20x (numeric values compress well)
- Event data: 3-5x (text messages have lower ratio)

### 8.3 Monitoring Queries

```sql
-- Check compression status
SELECT 
    hypertable_name,
    COUNT(*) AS total_chunks,
    COUNT(*) FILTER (WHERE compression_status = 'Compressed') AS compressed_chunks,
    pg_size_pretty(SUM(uncompressed_total_bytes)) AS uncompressed_size,
    pg_size_pretty(SUM(compressed_total_bytes)) AS compressed_size
FROM timescaledb_information.chunks
GROUP BY hypertable_name;

-- Check oldest data
SELECT 
    hypertable_name,
    MIN(range_start) AS oldest_data,
    MAX(range_end) AS newest_data,
    AGE(now(), MIN(range_start)) AS data_age
FROM timescaledb_information.chunks
GROUP BY hypertable_name;
```

---

## 9. Deployment Guide

### 9.1 Pre-Deployment Checklist

- [ ] PostgreSQL 17.6+ with TimescaleDB 2.10+ installed
- [ ] Backup current database: `pg_dump -h localhost -U cereveate -d Cereveate > backup_$(date +%Y%m%d).sql`
- [ ] Verify disk space: At least 20GB free for initial deployment
- [ ] Stop C# historian service: `sc stop HistorianService` (if running)
- [ ] Review current schema version: `SELECT get_schema_version();`

### 9.2 Deployment Steps

```powershell
# 1. Set environment variables
$env:PGPASSWORD='cereveate@222'

# 2. Execute operational hardening script
psql -h localhost -U cereveate -d Cereveate -f OPERATIONAL_HARDENING.sql

# 3. Verify deployment
psql -h localhost -U cereveate -d Cereveate -c "SELECT get_schema_version();"

# Expected output: 2 (operational_hardening migration)

# 4. Check health
psql -h localhost -U cereveate -d Cereveate -c "SELECT * FROM check_retention_health();"

# 5. Restart C# historian service
sc start HistorianService
```

### 9.3 Post-Deployment Verification

```sql
-- 1. Verify schema extensions
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'tag_master' 
  AND column_name IN ('trip_category', 'interlock_type', 'is_trip_initiator');

-- Expected: 3 rows

-- 2. Verify trip/interlock tables exist
SELECT table_name 
FROM information_schema.tables 
WHERE table_name IN ('trip_event_tracking', 'interlock_state_tracking');

-- Expected: 2 rows

-- 3. Verify views created
SELECT table_name 
FROM information_schema.views 
WHERE table_name LIKE 'vw_%';

-- Expected: 8 views (vw_active_alarms, vw_trip_causality, etc.)

-- 4. Verify functions created
SELECT routine_name 
FROM information_schema.routines 
WHERE routine_name IN (
    'validate_timeseries_sample', 
    'acknowledge_alarm', 
    'update_latest_values_batch',
    'validate_writer_mapping_version',
    'check_retention_health',
    'cleanup_old_events',
    'get_schema_version'
);

-- Expected: 7 functions

-- 5. Test duplicate constraint
INSERT INTO historian_raw.historian_timeseries 
    (time, tag_id, value_num, quality, sample_source, mapping_version)
VALUES 
    (now(), 'TEST_TAG', 123.45, 'G', 'OPC', 1)
ON CONFLICT (time, tag_id) DO UPDATE SET value_num = EXCLUDED.value_num;

-- Expected: No error, 1 row affected
```

### 9.4 Rollback Procedure (Emergency)

**WARNING**: Only use if critical issues detected

```sql
-- Rollback script (reverses all changes)
-- See OPERATIONAL_HARDENING.sql bottom for complete rollback SQL
BEGIN;

-- Drop triggers
DROP TRIGGER IF EXISTS trg_validate_timeseries_sample ON historian_timeseries;

-- Remove alarm columns
ALTER TABLE historian_events 
    DROP COLUMN IF EXISTS alarm_state,
    DROP COLUMN IF EXISTS alarm_priority,
    ... (8 columns);

-- Drop trip/interlock tables
DROP TABLE IF EXISTS trip_event_tracking CASCADE;
DROP TABLE IF EXISTS interlock_state_tracking CASCADE;

-- Mark migration as rolled back
UPDATE schema_migrations SET status = 'ROLLED_BACK' WHERE migration_id = 2;

COMMIT;
```

---

## 10. Verification Tests

### Test 1: Smart Truncation

```sql
-- Insert oversized value (15KB text)
INSERT INTO historian_raw.historian_timeseries 
    (time, tag_id, value_text, quality, sample_source, mapping_version)
VALUES 
    (now(), 'TEST_TAG', repeat('GARBAGE_', 2000), 'G', 'OPC', 1);

-- Check stored length (should be truncated to 1000 chars)
SELECT tag_id, length(value_text) AS stored_length, quality 
FROM historian_raw.historian_timeseries 
WHERE tag_id = 'TEST_TAG' 
ORDER BY time DESC LIMIT 1;

-- Expected: stored_length=1000, quality='U'

-- Check warning logged
SELECT * FROM historian_raw.historian_events 
WHERE event_type = 'DATA_QUALITY_WARNING' 
  AND tag_id = 'TEST_TAG'
ORDER BY time DESC LIMIT 1;

-- Expected: Message contains "TRUNCATED from 16000 to 1000 chars"
```

### Test 2: Duplicate Handling

```sql
-- First write
INSERT INTO historian_raw.historian_timeseries 
    (time, tag_id, value_num, quality, sample_source, mapping_version)
VALUES 
    ('2025-12-22 10:00:00+00', 'TEMP_01', 25.5, 'G', 'OPC', 1)
ON CONFLICT (time, tag_id) DO UPDATE SET value_num = EXCLUDED.value_num;

-- Duplicate write (different value)
INSERT INTO historian_raw.historian_timeseries 
    (time, tag_id, value_num, quality, sample_source, mapping_version)
VALUES 
    ('2025-12-22 10:00:00+00', 'TEMP_01', 25.8, 'G', 'OPC', 1)
ON CONFLICT (time, tag_id) DO UPDATE SET value_num = EXCLUDED.value_num;

-- Check: Only 1 row, last value wins
SELECT COUNT(*), MAX(value_num) 
FROM historian_raw.historian_timeseries 
WHERE time = '2025-12-22 10:00:00+00' AND tag_id = 'TEMP_01';

-- Expected: count=1, max=25.8
```

### Test 3: Alarm Lifecycle

```sql
-- Raise alarm
INSERT INTO historian_raw.historian_events 
    (time, tag_id, event_type, severity, message, 
     alarm_state, alarm_priority, alarm_setpoint, alarm_actual_value)
VALUES 
    (now(), 'TEMP_01', 'ALARM_HIGH', 4, 'Temperature exceeded 100°C', 
     'ACTIVE', 4, 100.0, 105.3);

-- Get alarm_id
SET @alarm_id = (SELECT event_id FROM historian_raw.historian_events 
                 WHERE tag_id = 'TEMP_01' AND alarm_state = 'ACTIVE' 
                 ORDER BY time DESC LIMIT 1);

-- Acknowledge alarm
SELECT acknowledge_alarm(@alarm_id, 'operator_john', 'Checking cooling system');

-- Verify state changed
SELECT alarm_state, acknowledged_by, acknowledged_at 
FROM historian_raw.historian_events 
WHERE event_id = @alarm_id;

-- Expected: alarm_state='ACKNOWLEDGED', acknowledged_by='operator_john'
```

### Test 4: Trip Event Recording

```sql
-- Record trip
INSERT INTO historian_raw.trip_event_tracking 
    (trip_time, trip_tag_id, trip_category, equipment_affected, production_loss_mw)
VALUES 
    (now(), 'TURBINE_01_TRIP', 'SAFETY_TRIP', 'TURBINE_01', 270.5);

-- Query causality view
SELECT * FROM historian_raw.vw_trip_causality ORDER BY trip_time DESC LIMIT 1;

-- Expected: New trip event with equipment='TURBINE_01', loss=270.5 MW
```

### Test 5: Retention Cleanup

```sql
-- Run cleanup (dry run - check what would be deleted)
SELECT * FROM cleanup_old_events();

-- Expected: 7 rows showing deletion counts for each event category
-- AUDIT row should always show deleted_count=0 (never deleted)
```

---

## Appendix A: Configuration Reference

### Data Quality Limits
```sql
SELECT * FROM historian_meta.data_quality_limits ORDER BY setting_name;
```

### Alarm Suppression Schedules
```sql
SELECT * FROM historian_meta.alarm_suppression_schedule ORDER BY schedule_id;
```

### Schema Version
```sql
SELECT get_schema_version();  -- Should return 2
```

---

## Appendix B: Performance Considerations

### Index Coverage
- All foreign keys indexed
- Time-series queries optimized (time DESC indexes)
- Trip/interlock queries optimized (category, state indexes)

### Query Performance Targets
- Active alarms view: <50ms for <1000 active alarms
- Trip causality view: <200ms for 1 year of trips
- Latest value reads: <10ms per tag (indexed)

### Scaling Limits (Validated)
- Time-series ingestion: 10K tags × 1Hz = 10K samples/sec
- Event ingestion: <10K alarms/day (validated for combined table)
- Trip events: <100 trips/day (typical power plant)

---

**Document Status**: Production-Ready  
**Next Document**: PART 2 - Application Logic Guide (trip detection, correlation, state machines)

