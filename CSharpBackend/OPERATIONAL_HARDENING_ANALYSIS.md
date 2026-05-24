# Operational Hardening Analysis
**Date**: December 21, 2025  
**Purpose**: Evaluate if existing schema needs new tables OR just operational improvements

---

## CRITICAL QUESTION: Do We Need New Tables?

### User's 10 Requirements Analysis

| # | Requirement | Needs New Table? | Solution |
|---|-------------|------------------|----------|
| 1 | Schema tolerance (prevent COPY crashes) | ❌ NO | Alter existing columns (TEXT length, type flexibility) |
| 2 | Data acceptance rules (strict vs tolerant) | ❌ NO | Add constraints + validation functions |
| 3 | Duplicate handling (same tag_id + time) | ❌ NO | Add UNIQUE constraint with ON CONFLICT policy |
| 4 | Ingestion failure containment | ❌ NO | C# code change (retry logic, circuit breaker) |
| 5 | Event vs Alarm definition | ⚠️ MAYBE | Reuse `historian_events` with proper event_type taxonomy |
| 6 | Alarm lifecycle (ACTIVE/ACK/CLEARED) | ⚠️ MAYBE | Add columns to `historian_events` OR separate table |
| 7 | Latest value consistency rules | ❌ NO | Add precedence logic to `update_latest_values_batch()` |
| 8 | Mapping version discipline | ❌ NO | Add CHECK constraint + writer validation |
| 9 | Retention & compression validation | ❌ NO | Add monitoring queries to `historian_mon` |
| 10 | Schema governance | ❌ NO | Add migration tracking table + versioning |

---

## VERDICT: 8 out of 10 = Schema Improvements, NOT New Tables

### What We DON'T Need (Yet)

**Analytics tables** (equipment_state_history, downtime_events, oee_metrics, ml_models, etc.) are **FUTURE enhancements**, not operational requirements.

**Right now, you need**:
- ✅ Crash-proof ingestion
- ✅ Predictable duplicate behavior
- ✅ Controlled schema evolution
- ✅ Alarm lifecycle management

**These are OPERATIONAL HARDENING fixes**, not analytics features.

---

## Proposed Solution: 3-Layer Hardening

### Layer 1: Schema Tolerance (Prevent COPY Crashes)

#### Problem
```
Current: value_text TEXT NULL
Risk: PostgreSQL TEXT has 1GB limit, but no practical protection
Risk: quality CHAR(1) rejects 2-character values
Risk: sample_source CHAR(3) rejects longer strings
```

#### Fix
```sql
-- Already fine (TEXT unlimited)
-- But add validation trigger to log oversized values

-- Fix: Make sample_source more tolerant
ALTER TABLE historian_raw.historian_timeseries 
    ALTER COLUMN sample_source TYPE VARCHAR(10);

-- Add size validation trigger (log, don't reject)
CREATE OR REPLACE FUNCTION validate_timeseries_sample()
RETURNS TRIGGER AS $$
BEGIN
    -- Log suspicious data, but accept it
    IF length(NEW.value_text) > 10000 THEN
        INSERT INTO historian_raw.historian_events 
            (time, tag_id, event_type, severity, message, metadata)
        VALUES (
            NEW.time, 
            NEW.tag_id, 
            'DATA_QUALITY_WARNING', 
            2, 
            'Oversized value_text detected',
            jsonb_build_object('length', length(NEW.value_text))
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_validate_timeseries_sample
    BEFORE INSERT ON historian_raw.historian_timeseries
    FOR EACH ROW
    EXECUTE FUNCTION validate_timeseries_sample();
```

**Result**: Historian accepts data, logs warnings, never crashes.

---

### Layer 2: Duplicate Handling

#### Problem
```
Current: No constraint on (time, tag_id)
Risk: Same sample written 3 times = 200% data inflation
```

#### Fix Option A: Prevent Duplicates (Strict)
```sql
-- Add unique constraint
ALTER TABLE historian_raw.historian_timeseries
    ADD CONSTRAINT uq_timeseries_time_tag UNIQUE (time, tag_id);
```
**Result**: INSERT fails on duplicate → need ON CONFLICT handling in C#.

#### Fix Option B: Last-Write-Wins (Tolerant)
```sql
-- No schema change, handle in C# with ON CONFLICT UPDATE
-- C# code:
COPY ... ON CONFLICT (time, tag_id) DO UPDATE SET
    value_num = EXCLUDED.value_num,
    value_text = EXCLUDED.value_text,
    quality = EXCLUDED.quality,
    mapping_version = EXCLUDED.mapping_version
WHERE historian_timeseries.time < EXCLUDED.time;  -- Only if newer
```

#### Fix Option C: Count-Based Deduplication
```sql
-- Add dedup column
ALTER TABLE historian_raw.historian_timeseries
    ADD COLUMN write_count INTEGER DEFAULT 1;

-- Update function to increment on duplicate
ON CONFLICT (time, tag_id) DO UPDATE SET
    write_count = historian_timeseries.write_count + 1;
```

**Recommendation**: Option B (last-write-wins) for historians (industry standard).

---

### Layer 3: Alarm Lifecycle

#### Problem
```
Current: historian_events stores everything (system events + alarms)
Risk: No clear alarm state (ACTIVE vs CLEARED vs ACKNOWLEDGED)
Risk: No alarm acknowledgment tracking
```

#### Fix Option A: Reuse historian_events (Minimal Change)
```sql
-- Add alarm-specific columns
ALTER TABLE historian_raw.historian_events
    ADD COLUMN alarm_state TEXT CHECK (alarm_state IN ('ACTIVE', 'ACKNOWLEDGED', 'CLEARED', 'SUPPRESSED')),
    ADD COLUMN alarm_priority INTEGER CHECK (alarm_priority BETWEEN 1 AND 5),
    ADD COLUMN acknowledged_by TEXT,
    ADD COLUMN acknowledged_at TIMESTAMPTZ,
    ADD COLUMN cleared_at TIMESTAMPTZ,
    ADD COLUMN parent_alarm_id BIGINT REFERENCES historian_events(event_id);

-- Index for active alarms
CREATE INDEX idx_events_active_alarms 
    ON historian_raw.historian_events (alarm_state, time DESC) 
    WHERE alarm_state IN ('ACTIVE', 'ACKNOWLEDGED');

-- View for active alarms only
CREATE VIEW historian_raw.vw_active_alarms AS
SELECT 
    event_id,
    time AS alarm_time,
    tag_id,
    message AS alarm_message,
    severity AS alarm_priority,
    alarm_state,
    acknowledged_by,
    acknowledged_at,
    EXTRACT(EPOCH FROM (now() - time))/60 AS duration_minutes
FROM historian_raw.historian_events
WHERE alarm_state IN ('ACTIVE', 'ACKNOWLEDGED')
ORDER BY alarm_priority DESC, time ASC;
```

**Result**: Alarms tracked in same table, clean separation via views.

#### Fix Option B: Separate Alarm Table (Clean Separation)
```sql
CREATE TABLE historian_raw.historian_alarms (
    alarm_id BIGSERIAL PRIMARY KEY,
    raised_at TIMESTAMPTZ NOT NULL,
    cleared_at TIMESTAMPTZ,
    acknowledged_at TIMESTAMPTZ,
    tag_id TEXT NOT NULL,
    alarm_type TEXT NOT NULL,  -- 'HIGH', 'LOW', 'DEVIATION', 'RATE_OF_CHANGE'
    priority INTEGER NOT NULL CHECK (priority BETWEEN 1 AND 5),
    state TEXT NOT NULL CHECK (state IN ('ACTIVE', 'ACKNOWLEDGED', 'CLEARED', 'SUPPRESSED')),
    alarm_value DOUBLE PRECISION,
    setpoint DOUBLE PRECISION,
    acknowledged_by TEXT,
    notes TEXT,
    metadata JSONB
);

SELECT create_hypertable('historian_raw.historian_alarms', 'raised_at', 
    if_not_exists => TRUE, chunk_time_interval => INTERVAL '7 days');

CREATE INDEX idx_alarms_active ON historian_raw.historian_alarms (state, raised_at DESC)
    WHERE state IN ('ACTIVE', 'ACKNOWLEDGED');
```

**Recommendation**: Option A (reuse historian_events) unless you have >10,000 alarms/day.

---

## Operational Requirements → Solutions

### 1. Schema Tolerance ✅
**Solution**: 
- Change `sample_source CHAR(3)` → `VARCHAR(10)`
- Add validation trigger (log warnings, don't reject)
- Document max safe sizes in comments

**Files to Modify**:
- `production_schema.sql` - ALTER TABLE statements
- `HistorianIngestHostedService.cs` - Add size pre-checks before COPY

---

### 2. Data Acceptance Rules ✅
**Solution**:
- **STRICT**: time, tag_id, mapping_version (must be valid)
- **TOLERANT**: value_num, value_text, value_bool (accept nulls, log warnings)
- **VALIDATED**: quality ('G', 'B', 'U' only via CHECK constraint)

**Implementation**:
```sql
-- Add comments documenting contract
COMMENT ON COLUMN historian_timeseries.time IS 
    'STRICT: Must be valid timestamptz. Rejects: NULL, invalid timestamps, far future (>1 year ahead)';

COMMENT ON COLUMN historian_timeseries.value_num IS 
    'TOLERANT: Accepts NULL, Infinity, NaN. Logs warning for NaN/Inf in historian_events.';

COMMENT ON COLUMN historian_timeseries.quality IS 
    'VALIDATED: Must be G (Good), B (Bad), or U (Uncertain). Rejects other values.';
```

---

### 3. Duplicate Handling ✅
**Solution**: Last-write-wins policy

**Schema Change**:
```sql
-- Add unique constraint
ALTER TABLE historian_raw.historian_timeseries
    ADD CONSTRAINT uq_timeseries_time_tag UNIQUE (time, tag_id);
```

**C# Change** (DbWriterService.cs):
```csharp
// Change COPY to handle conflicts
var copyCommand = @"
    COPY historian_raw.historian_timeseries 
    (time, tag_id, value_num, value_text, value_bool, quality, sample_source, mapping_version)
    FROM STDIN BINARY
    ON CONFLICT (time, tag_id) DO UPDATE SET
        value_num = EXCLUDED.value_num,
        value_text = EXCLUDED.value_text,
        value_bool = EXCLUDED.value_bool,
        quality = CASE 
            WHEN EXCLUDED.time > historian_timeseries.time THEN EXCLUDED.quality
            ELSE historian_timeseries.quality
        END,
        mapping_version = GREATEST(historian_timeseries.mapping_version, EXCLUDED.mapping_version)
    WHERE EXCLUDED.time >= historian_timeseries.time;
";
```

**Alternative**: Partition by hour + allow duplicates within partition (dedup in queries).

---

### 4. Ingestion Failure Containment ✅
**Solution**: Circuit breaker pattern (NO schema change)

**C# Implementation** (HistorianIngestHostedService.cs):
```csharp
// Add circuit breaker
private CircuitBreakerState _circuitState = CircuitBreakerState.Closed;
private int _consecutiveFailures = 0;
private DateTime _circuitOpenedAt;

private async Task<bool> TryWriteBatchAsync(List<Sample> batch)
{
    if (_circuitState == CircuitBreakerState.Open)
    {
        if (DateTime.UtcNow - _circuitOpenedAt > TimeSpan.FromMinutes(5))
        {
            _circuitState = CircuitBreakerState.HalfOpen;
            _logger.LogInformation("Circuit breaker entering HALF-OPEN state");
        }
        else
        {
            _logger.LogWarning("Circuit breaker OPEN - dropping batch");
            return false;
        }
    }

    try
    {
        await _dbWriter.WriteBatchAsync(batch);
        _consecutiveFailures = 0;
        if (_circuitState == CircuitBreakerState.HalfOpen)
        {
            _circuitState = CircuitBreakerState.Closed;
            _logger.LogInformation("Circuit breaker CLOSED");
        }
        return true;
    }
    catch (Exception ex)
    {
        _consecutiveFailures++;
        if (_consecutiveFailures >= 5)
        {
            _circuitState = CircuitBreakerState.Open;
            _circuitOpenedAt = DateTime.UtcNow;
            _logger.LogError("Circuit breaker OPENED after 5 failures");
        }
        throw;
    }
}
```

---

### 5. Event vs Alarm Definition ✅
**Solution**: Taxonomy via event_type + severity

**Schema Change**:
```sql
-- Add constraint for event types
ALTER TABLE historian_raw.historian_events
    ADD CONSTRAINT chk_event_type CHECK (
        event_type IN (
            -- System Events
            'SYSTEM_START', 'SYSTEM_STOP', 'WRITER_START', 'WRITER_STOP',
            'MAPPING_RELOAD', 'COMPRESSION_COMPLETE', 'BACKUP_COMPLETE',
            -- Data Quality Events
            'TYPE_CONVERSION_ERROR', 'DATA_QUALITY_WARNING', 'OVERSIZED_VALUE',
            -- Alarms (process)
            'ALARM_HIGH', 'ALARM_LOW', 'ALARM_DEVIATION', 'ALARM_RATE_OF_CHANGE',
            'ALARM_ACKNOWLEDGED', 'ALARM_CLEARED'
        )
    );

-- Add severity levels
COMMENT ON COLUMN historian_events.severity IS 
    '1=DEBUG, 2=INFO, 3=WARNING, 4=ERROR, 5=CRITICAL. 
     Alarms use 1-5 for priority (5=highest)';
```

**Application Change** (HistorianEventTypes.cs):
```csharp
public static class HistorianEventTypes
{
    // System Events
    public const string SystemStart = "SYSTEM_START";
    public const string WriterStart = "WRITER_START";
    
    // Data Events
    public const string TypeConversionError = "TYPE_CONVERSION_ERROR";
    
    // Alarms
    public const string AlarmHigh = "ALARM_HIGH";
    public const string AlarmLow = "ALARM_LOW";
    public const string AlarmAcknowledged = "ALARM_ACKNOWLEDGED";
    public const string AlarmCleared = "ALARM_CLEARED";
}
```

---

### 6. Alarm Lifecycle ✅
**Solution**: Add alarm columns to historian_events

**Schema Change**:
```sql
ALTER TABLE historian_raw.historian_events
    ADD COLUMN alarm_state TEXT CHECK (alarm_state IN ('ACTIVE', 'ACKNOWLEDGED', 'CLEARED', 'SUPPRESSED')),
    ADD COLUMN alarm_priority INTEGER CHECK (alarm_priority BETWEEN 1 AND 5),
    ADD COLUMN acknowledged_by TEXT,
    ADD COLUMN acknowledged_at TIMESTAMPTZ,
    ADD COLUMN cleared_at TIMESTAMPTZ,
    ADD COLUMN alarm_setpoint DOUBLE PRECISION,
    ADD COLUMN alarm_actual_value DOUBLE PRECISION;

-- Active alarms view
CREATE VIEW historian_raw.vw_active_alarms AS
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
    EXTRACT(EPOCH FROM (now() - time))/60 AS duration_minutes
FROM historian_raw.historian_events
WHERE event_type LIKE 'ALARM_%' 
  AND alarm_state IN ('ACTIVE', 'ACKNOWLEDGED')
ORDER BY alarm_priority DESC, time ASC;
```

---

### 7. Latest Value Consistency ✅
**Solution**: Precedence logic in update function

**Schema Change**:
```sql
-- Add last_updated column for conflict resolution
ALTER TABLE historian_raw.historian_latest_value
    ADD COLUMN last_sample_time TIMESTAMPTZ;  -- Different from updated_at (write time)

-- Modify update function
CREATE OR REPLACE FUNCTION update_latest_values_batch(...) 
RETURNS void AS $$
BEGIN
    UPDATE historian_raw.historian_latest_value AS lv
    SET 
        last_time = upd.last_time,
        last_value_num = upd.last_value_num,
        last_quality = upd.last_quality,
        last_mapping_version = upd.last_mapping_version,
        updated_at = now(),
        last_sample_time = upd.last_time
    FROM (...) AS upd
    WHERE lv.tag_id = upd.tag_id
      -- Precedence rules:
      AND (
          lv.last_sample_time IS NULL                    -- First write
          OR upd.last_time > lv.last_sample_time          -- Newer timestamp
          OR (upd.last_time = lv.last_sample_time         -- Same timestamp
              AND upd.last_mapping_version > lv.last_mapping_version)  -- Newer mapping
          OR (upd.last_time = lv.last_sample_time 
              AND upd.last_mapping_version = lv.last_mapping_version
              AND upd.last_quality = 'G' AND lv.last_quality != 'G')  -- Good quality wins
      );
END;
$$ LANGUAGE plpgsql;
```

---

### 8. Mapping Version Discipline ✅
**Solution**: Writer validation + staleness policy

**Schema Change**:
```sql
-- Add to writer_checkpoint
ALTER TABLE historian_meta.writer_checkpoint
    ADD COLUMN last_successful_write_at TIMESTAMPTZ,
    ADD COLUMN stale_mapping_warnings INTEGER DEFAULT 0;

-- Add validation function
CREATE OR REPLACE FUNCTION validate_writer_mapping_version(
    p_writer_name TEXT,
    p_current_mapping_version BIGINT
) RETURNS TABLE(is_valid BOOLEAN, message TEXT) AS $$
DECLARE
    v_latest_version BIGINT;
    v_version_age INTERVAL;
BEGIN
    -- Get latest mapping version from tag_master
    SELECT MAX(mapping_version) INTO v_latest_version
    FROM historian_meta.tag_master;

    IF p_current_mapping_version < v_latest_version THEN
        RETURN QUERY SELECT 
            FALSE, 
            format('Writer %s using stale mapping v%s (latest: v%s)', 
                   p_writer_name, p_current_mapping_version, v_latest_version);
    ELSE
        RETURN QUERY SELECT TRUE, 'Mapping version current';
    END IF;
END;
$$ LANGUAGE plpgsql;
```

**C# Change**:
```csharp
// Before writing batch, validate mapping version
var validationResult = await _dbWriter.ValidateWriterMappingVersionAsync(
    "HistorianIngestService", 
    _currentMappingVersion
);

if (!validationResult.IsValid)
{
    _logger.LogWarning(validationResult.Message);
    // Trigger mapping reload
    await _mappingCache.RefreshAsync();
}
```

---

### 9. Retention & Compression Validation ✅
**Solution**: Monitoring queries + alerting

**Schema Change**:
```sql
-- Add to historian_mon schema
CREATE TABLE historian_mon.retention_health (
    check_time TIMESTAMPTZ PRIMARY KEY DEFAULT now(),
    oldest_chunk_time TIMESTAMPTZ,
    oldest_chunk_age_days INTEGER,
    newest_chunk_time TIMESTAMPTZ,
    total_chunks INTEGER,
    compressed_chunks INTEGER,
    compression_ratio DOUBLE PRECISION,
    uncompressed_size_mb BIGINT,
    compressed_size_mb BIGINT,
    retention_policy_days INTEGER,
    chunks_outside_retention INTEGER,
    warnings TEXT[]
);

-- Health check function
CREATE OR REPLACE FUNCTION check_retention_health()
RETURNS TABLE(
    status TEXT,
    oldest_data_age_days INTEGER,
    compression_coverage_pct DOUBLE PRECISION,
    warnings TEXT[]
) AS $$
DECLARE
    v_warnings TEXT[] := ARRAY[]::TEXT[];
    v_oldest_age_days INTEGER;
    v_compression_pct DOUBLE PRECISION;
BEGIN
    -- Check oldest data age
    SELECT EXTRACT(DAY FROM now() - MIN(range_start))::INTEGER
    INTO v_oldest_age_days
    FROM timescaledb_information.chunks
    WHERE hypertable_name = 'historian_timeseries';

    IF v_oldest_age_days > 730 THEN
        v_warnings := array_append(v_warnings, 
            format('Data retention exceeded: %s days (policy: 730)', v_oldest_age_days));
    END IF;

    -- Check compression coverage
    SELECT 
        100.0 * COUNT(*) FILTER (WHERE compression_status = 'Compressed') / COUNT(*)
    INTO v_compression_pct
    FROM timescaledb_information.chunks
    WHERE hypertable_name = 'historian_timeseries';

    IF v_compression_pct < 80 THEN
        v_warnings := array_append(v_warnings, 
            format('Low compression coverage: %.1f%% (target: 80%%)', v_compression_pct));
    END IF;

    RETURN QUERY SELECT 
        CASE 
            WHEN array_length(v_warnings, 1) > 0 THEN 'WARNING'
            ELSE 'HEALTHY'
        END,
        v_oldest_age_days,
        v_compression_pct,
        v_warnings;
END;
$$ LANGUAGE plpgsql;
```

---

### 10. Schema Governance ✅
**Solution**: Migration tracking table

**Schema Change**:
```sql
CREATE TABLE historian_meta.schema_migrations (
    migration_id INTEGER PRIMARY KEY,
    migration_name TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_by TEXT NOT NULL,
    description TEXT,
    sql_file_hash TEXT,  -- SHA256 of migration file
    rollback_sql TEXT,   -- Optional rollback script
    status TEXT CHECK (status IN ('APPLIED', 'FAILED', 'ROLLED_BACK'))
);

-- Current schema version function
CREATE OR REPLACE FUNCTION get_schema_version()
RETURNS INTEGER AS $$
    SELECT COALESCE(MAX(migration_id), 0) 
    FROM historian_meta.schema_migrations 
    WHERE status = 'APPLIED';
$$ LANGUAGE sql;

-- Example migration record
INSERT INTO historian_meta.schema_migrations 
    (migration_id, migration_name, applied_by, description, status)
VALUES 
    (1, 'initial_schema', 'system', 'Base historian schema v1.0', 'APPLIED'),
    (2, 'add_alarm_lifecycle', 'admin', 'Added alarm state tracking to historian_events', 'APPLIED');
```

---

## Implementation Priority

### Phase 1: Critical (Do First) 🔴
1. **Duplicate handling** (UNIQUE constraint + ON CONFLICT)
2. **Schema tolerance** (ALTER sample_source, add validation trigger)
3. **Circuit breaker** (C# code, no schema change)

### Phase 2: Important (Do Next) 🟡
4. **Alarm lifecycle** (ADD COLUMN to historian_events)
5. **Latest value precedence** (UPDATE function logic)
6. **Event taxonomy** (CHECK constraint on event_type)

### Phase 3: Governance (Do Last) 🟢
7. **Mapping version validation** (validation function)
8. **Retention monitoring** (health check function)
9. **Schema migrations** (tracking table)

---

## What About Analytics Tables?

### Deferred to Phase 2 (After Operational Hardening)

Once operational requirements are rock-solid:
- ✅ No crash risk
- ✅ Predictable duplicates
- ✅ Alarm lifecycle works
- ✅ Schema versioned

**THEN** add analytics tables:
- equipment_state_history (for MTBF/MTTR)
- production_batches (for OEE)
- ml_features (for predictive maintenance)

**Reason**: Analytics tables won't help if ingestion is crashing or alarms aren't tracked properly.

---

## Recommended Next Step

**Create `OPERATIONAL_HARDENING.sql`** with Phase 1 + Phase 2 changes:
1. ALTER TABLE statements (schema tolerance, alarm columns)
2. UNIQUE constraints (duplicate handling)
3. Helper functions (validation, monitoring)
4. Views (active alarms)

**Then modify C# code**:
1. Circuit breaker pattern (HistorianIngestHostedService)
2. ON CONFLICT handling (DbWriterService)
3. Mapping version validation

**SKIP analytics tables for now** - focus on operational stability first.

---

## Document Status

**Version**: 1.0  
**Date**: December 21, 2025  
**Recommendation**: ✅ Proceed with operational hardening, ❌ Defer analytics tables
