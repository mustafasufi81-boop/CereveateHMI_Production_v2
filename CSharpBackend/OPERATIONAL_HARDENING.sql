/* ====================================================================
   OPERATIONAL HARDENING FOR HISTORIAN PLATFORM
   
   Purpose: Fix 10 operational requirements WITHOUT adding new tables
   - Schema tolerance (prevent crashes)
   - Duplicate handling (last-write-wins)
   - Alarm lifecycle (extend historian_events)
   - Data validation (accept first, validate later)
   - Latest value precedence (consistent reads)
   
   Version: 1.0
   Date: December 21, 2025
   
   BEFORE running: Review examples at end of file
   AFTER running: Test with example scenarios
==================================================================== */

-- ================= PHASE 1: SCHEMA TOLERANCE =================

-- Fix #1: Add data quality limits configuration table
CREATE TABLE IF NOT EXISTS historian_meta.data_quality_limits (
    setting_name TEXT PRIMARY KEY,
    setting_value INTEGER NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT now(),
    updated_by TEXT
);

INSERT INTO historian_meta.data_quality_limits (setting_name, setting_value, description) VALUES
    ('value_text_max_length', 1000, 'Maximum chars for value_text. Longer values truncated.'),
    ('value_text_warn_length', 500, 'Warn if value_text exceeds this (no truncation)'),
    ('log_cooldown_seconds', 300, 'Min seconds between duplicate warnings (per tag)'),
    ('warn_log_cooldown_seconds', 1800, 'Min seconds between size warnings (per tag)')
ON CONFLICT (setting_name) DO NOTHING;

COMMENT ON TABLE historian_meta.data_quality_limits IS 
'Configurable limits for data quality validation. Adjust without code changes.';

-- Fix #1b: Add trip/interlock semantic tagging to tag_master
ALTER TABLE historian_meta.tag_master
    -- Basic tag configuration (deadband and polling)
    ADD COLUMN IF NOT EXISTS min_value DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS max_value DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS deadband_enabled BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS deadband_value DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS logging_interval_ms INTEGER,
    
    -- OPC Server connection metadata
    ADD COLUMN IF NOT EXISTS server_progid TEXT,
    ADD COLUMN IF NOT EXISTS server_host TEXT,
    ADD COLUMN IF NOT EXISTS process_unit TEXT,
    
    -- Alarm configuration (legacy naming for compatibility)
    ADD COLUMN IF NOT EXISTS alarm_hh_limit DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS alarm_h_limit DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS alarm_l_limit DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS alarm_ll_limit DOUBLE PRECISION,
    
    -- Trip/Interlock classification
    ADD COLUMN IF NOT EXISTS trip_category TEXT CHECK (trip_category IN ('PROCESS_TRIP', 'SAFETY_TRIP', 'EMERGENCY_TRIP', 'INTERLOCK', NULL)),
    ADD COLUMN IF NOT EXISTS interlock_type TEXT CHECK (interlock_type IN ('PERMISSIVE', 'CONDITIONAL', 'SEQUENTIAL', 'PROTECTIVE', NULL)),
    ADD COLUMN IF NOT EXISTS equipment_criticality INTEGER CHECK (equipment_criticality BETWEEN 1 AND 5),
    ADD COLUMN IF NOT EXISTS is_trip_initiator BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS associated_equipment TEXT,
    
    -- Value range tracking (for alarm threshold determination)
    ADD COLUMN IF NOT EXISTS observed_min_value DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS observed_max_value DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS observation_start_time TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS observation_sample_count BIGINT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_observation_update TIMESTAMPTZ,
    
    -- Alarm thresholds (new naming convention)
    ADD COLUMN IF NOT EXISTS alarm_low_low_threshold DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS alarm_low_threshold DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS alarm_high_threshold DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS alarm_high_high_threshold DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS alarm_priority INTEGER CHECK (alarm_priority BETWEEN 1 AND 5),
    ADD COLUMN IF NOT EXISTS alarm_deadband DOUBLE PRECISION DEFAULT 1.0,
    ADD COLUMN IF NOT EXISTS alarm_enabled BOOLEAN DEFAULT FALSE,
    
    -- Trip correlation configuration
    ADD COLUMN IF NOT EXISTS causes_trip_on_tag TEXT,
    ADD COLUMN IF NOT EXISTS trip_time_window_seconds INTEGER DEFAULT 2;

COMMENT ON COLUMN historian_meta.tag_master.trip_category IS 
'Trip classification: PROCESS_TRIP (normal shutdown), SAFETY_TRIP (hazard prevention), EMERGENCY_TRIP (immediate stop), INTERLOCK (condition-based), NULL (not a trip tag)';

COMMENT ON COLUMN historian_meta.tag_master.interlock_type IS 
'Interlock logic type: PERMISSIVE (must be true to start), CONDITIONAL (must stay true while running), SEQUENTIAL (order dependency), PROTECTIVE (fault protection), NULL (not an interlock)';

COMMENT ON COLUMN historian_meta.tag_master.equipment_criticality IS 
'Equipment criticality: 1=Low (maintenance mode), 2=Medium (isolated systems), 3=High (key equipment), 4=Urgent (main production), 5=Critical (safety systems)';

COMMENT ON COLUMN historian_meta.tag_master.is_trip_initiator IS 
'TRUE if this tag can initiate a trip (e.g., HIGH_TEMP_ALARM triggers TURBINE_TRIP). Used for causality analysis.';

COMMENT ON COLUMN historian_meta.tag_master.observed_min_value IS 
'Minimum value observed during monitoring period. Used to establish baseline for alarm thresholds.';

COMMENT ON COLUMN historian_meta.tag_master.observed_max_value IS 
'Maximum value observed during monitoring period. Used to establish baseline for alarm thresholds.';

COMMENT ON COLUMN historian_meta.tag_master.observation_start_time IS 
'When value range observation started. Reset when thresholds are configured.';

COMMENT ON COLUMN historian_meta.tag_master.observation_sample_count IS 
'Number of samples collected during observation period. Higher count = more reliable min/max.';

COMMENT ON COLUMN historian_meta.tag_master.alarm_high_threshold IS 
'HIGH alarm threshold. When value > threshold, log ALARM_HIGH event. Set AFTER observing value ranges.';

COMMENT ON COLUMN historian_meta.tag_master.alarm_high_high_threshold IS 
'HIGH-HIGH alarm threshold (critical). When value > threshold, log ALARM_HIGH_HIGH event.';

COMMENT ON COLUMN historian_meta.tag_master.causes_trip_on_tag IS 
'Tag ID of equipment that trips when this alarm activates. 
Example: MOTOR_TEMP_ALARM.causes_trip_on_tag = MOTOR_RUN_STATUS';

COMMENT ON COLUMN historian_meta.tag_master.trip_time_window_seconds IS 
'Max seconds between alarm activation and equipment stop to consider it a trip. Default: 2 seconds.';

-- Fix #2: Make sample_source more tolerant (currently CHAR(3))

ALTER TABLE historian_raw.historian_timeseries 
    ALTER COLUMN sample_source TYPE VARCHAR(10);

COMMENT ON COLUMN historian_raw.historian_timeseries.sample_source IS 
'Source of sample: OPC, MANUAL, CALC, SIM, API, etc. Max 10 chars.';

-- Fix #1c: Add validation trigger with SMART LIMITS and RATE-LIMITED LOGGING
CREATE OR REPLACE FUNCTION validate_timeseries_sample()
RETURNS TRIGGER AS $$
DECLARE
    v_max_safe_length INTEGER;
    v_warning_threshold INTEGER;
    v_log_suppression_key TEXT;
    v_last_logged TIMESTAMPTZ;
    v_log_cooldown INTERVAL;
    v_warn_cooldown INTERVAL;
BEGIN
    -- Load limits from config table (cached by PostgreSQL)
    SELECT setting_value INTO v_max_safe_length 
    FROM historian_meta.data_quality_limits 
    WHERE setting_name = 'value_text_max_length';
    
    SELECT setting_value INTO v_warning_threshold 
    FROM historian_meta.data_quality_limits 
    WHERE setting_name = 'value_text_warn_length';
    
    SELECT (setting_value || ' seconds')::INTERVAL INTO v_log_cooldown 
    FROM historian_meta.data_quality_limits 
    WHERE setting_name = 'log_cooldown_seconds';
    
    SELECT (setting_value || ' seconds')::INTERVAL INTO v_warn_cooldown 
    FROM historian_meta.data_quality_limits 
    WHERE setting_name = 'warn_log_cooldown_seconds';
    
    -- Default fallback if config missing
    v_max_safe_length := COALESCE(v_max_safe_length, 1000);
    v_warning_threshold := COALESCE(v_warning_threshold, 500);
    v_log_cooldown := COALESCE(v_log_cooldown, INTERVAL '5 minutes');
    v_warn_cooldown := COALESCE(v_warn_cooldown, INTERVAL '30 minutes');
    
    -- SMART TRUNCATION: Accept first N chars, truncate rest, log ONCE per tag
    IF NEW.value_text IS NOT NULL AND length(NEW.value_text) > v_max_safe_length THEN
        -- Check last log time for this tag (rate limiting)
        SELECT MAX(time) INTO v_last_logged
        FROM historian_raw.historian_events
        WHERE tag_id = NEW.tag_id 
          AND event_type = 'DATA_QUALITY_WARNING'
          AND message LIKE 'Oversized value_text%'
          AND time > now() - v_log_cooldown;
        
        -- Only log if cooldown expired (rate limiting)
        IF v_last_logged IS NULL THEN
            INSERT INTO historian_raw.historian_events 
                (time, tag_id, event_type, severity, message, metadata)
            VALUES (
                NEW.time, 
                NEW.tag_id, 
                'DATA_QUALITY_WARNING', 
                3,  -- WARNING severity (not INFO)
                format('Oversized value_text detected - TRUNCATED from %s to %s chars', 
                       length(NEW.value_text), v_max_safe_length),
                jsonb_build_object(
                    'original_length', length(NEW.value_text),
                    'truncated_length', v_max_safe_length,
                    'sample_preview', left(NEW.value_text, 100),
                    'truncated_bytes', length(NEW.value_text) - v_max_safe_length,
                    'warning', 'Check PLC/OPC for data corruption or config error'
                )
            );
        END IF;
        
        -- TRUNCATE value_text to safe limit
        NEW.value_text := left(NEW.value_text, v_max_safe_length);
        
        -- Mark quality as UNCERTAIN (data modified)
        NEW.quality := 'U';
    
    -- WARNING threshold: Log but don't truncate
    ELSIF NEW.value_text IS NOT NULL AND length(NEW.value_text) > v_warning_threshold THEN
        -- Check rate limiting
        SELECT MAX(time) INTO v_last_logged
        FROM historian_raw.historian_events
        WHERE tag_id = NEW.tag_id 
          AND event_type = 'DATA_QUALITY_WARNING'
          AND message LIKE 'Large value_text%'
          AND time > now() - v_warn_cooldown;
        
        IF v_last_logged IS NULL THEN
            INSERT INTO historian_raw.historian_events 
                (time, tag_id, event_type, severity, message, metadata)
            VALUES (
                NEW.time, 
                NEW.tag_id, 
                'DATA_QUALITY_WARNING', 
                2,
                format('Large value_text detected: %s chars (threshold: %s)', 
                       length(NEW.value_text), v_warning_threshold),
                jsonb_build_object('length', length(NEW.value_text))
            );
        END IF;
    END IF;
    
    -- Check for NaN/Infinity in numeric values
    IF NEW.value_num IS NOT NULL AND (NEW.value_num = 'NaN'::DOUBLE PRECISION OR 
                                       NEW.value_num = 'Infinity'::DOUBLE PRECISION OR 
                                       NEW.value_num = '-Infinity'::DOUBLE PRECISION) THEN
        -- Rate limiting for NaN/Infinity
        SELECT MAX(time) INTO v_last_logged
        FROM historian_raw.historian_events
        WHERE tag_id = NEW.tag_id 
          AND event_type = 'DATA_QUALITY_WARNING'
          AND message LIKE 'Invalid numeric%'
          AND time > now() - v_log_cooldown;
        
        IF v_last_logged IS NULL THEN
            INSERT INTO historian_raw.historian_events 
                (time, tag_id, event_type, severity, message, metadata)
            VALUES (
                NEW.time, 
                NEW.tag_id, 
                'DATA_QUALITY_WARNING', 
                3,
                'Invalid numeric value detected (NaN/Infinity) - marked as BAD quality',
                jsonb_build_object(
                    'value', NEW.value_num::TEXT,
                    'warning', 'Check sensor or PLC configuration'
                )
            );
        END IF;
        
        -- Set quality to Bad
        NEW.quality := 'B';
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_validate_timeseries_sample
    BEFORE INSERT ON historian_raw.historian_timeseries
    FOR EACH ROW
    EXECUTE FUNCTION validate_timeseries_sample();

COMMENT ON FUNCTION validate_timeseries_sample() IS 
'Smart validation with rate-limited logging:
- Truncates value_text >1000 chars (keeps first 1000, logs ONCE per 5 min per tag)
- Warns if value_text >500 chars (logs ONCE per 30 min)
- Sets quality=B for NaN/Infinity (logs ONCE per 5 min)
- Prevents event log flood during system malfunction
- Philosophy: Accept data, truncate extremes, rate-limit warnings';

-- ================= PHASE 2: DUPLICATE HANDLING =================
-- Fix #2a: Add unique constraint for duplicate detection

-- First, check if constraint already exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'uq_timeseries_time_tag'
    ) THEN
        -- Add unique constraint
        ALTER TABLE historian_raw.historian_timeseries
            ADD CONSTRAINT uq_timeseries_time_tag UNIQUE (time, tag_id);
        
        RAISE NOTICE 'Added UNIQUE constraint on (time, tag_id)';
    ELSE
        RAISE NOTICE 'UNIQUE constraint already exists';
    END IF;
END $$;

COMMENT ON CONSTRAINT uq_timeseries_time_tag ON historian_raw.historian_timeseries IS 
'Prevents duplicate samples for same tag at same timestamp. Use ON CONFLICT in writer for last-write-wins behavior.';

-- Note: C# code must now use:
-- COPY ... ON CONFLICT (time, tag_id) DO UPDATE SET ...

-- ================= PHASE 3: ALARM LIFECYCLE =================
-- Fix #3a: Add alarm tracking columns to existing historian_events table

ALTER TABLE historian_raw.historian_events
    ADD COLUMN IF NOT EXISTS alarm_state TEXT CHECK (alarm_state IN ('ACTIVE', 'ACKNOWLEDGED', 'CLEARED', 'SUPPRESSED')),
    ADD COLUMN IF NOT EXISTS alarm_priority INTEGER CHECK (alarm_priority BETWEEN 1 AND 5),
    ADD COLUMN IF NOT EXISTS acknowledged_by TEXT,
    ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS cleared_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS alarm_setpoint DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS alarm_actual_value DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS parent_alarm_id BIGINT;

COMMENT ON COLUMN historian_raw.historian_events.alarm_state IS 
'Alarm lifecycle state: ACTIVE (just raised), ACKNOWLEDGED (operator aware), CLEARED (condition normal), SUPPRESSED (silenced)';

COMMENT ON COLUMN historian_raw.historian_events.alarm_priority IS 
'Alarm priority: 1=Low, 2=Medium, 3=High, 4=Urgent, 5=Critical. Determines operator response time.';

COMMENT ON COLUMN historian_raw.historian_events.parent_alarm_id IS 
'References historian_events(event_id) for alarm chaining (e.g., acknowledgment events link to original alarm). 
NOTE: FK constraint not enforced (TimescaleDB hypertable limitation). Application must ensure referential integrity.';

-- Fix #3b: Add event type taxonomy (ENFORCES EVENT_ALARM_POLICY.md Section 1)
ALTER TABLE historian_raw.historian_events
    DROP CONSTRAINT IF EXISTS chk_event_type,
    ADD CONSTRAINT chk_event_type CHECK (
        event_type ~ '^(SYSTEM|WRITER|DATA_QUALITY|ALARM|TRIP|USER|AUDIT)_[A-Z_0-9]+$'
    );

COMMENT ON CONSTRAINT chk_event_type ON historian_raw.historian_events IS 
'Enforces event domain prefixes per EVENT_ALARM_POLICY.md:
- SYSTEM_*: Platform infrastructure (30-day retention)
- WRITER_*: Ingestion pipeline (30-day retention)
- DATA_QUALITY_*: Validation warnings (90-day retention)
- ALARM_*: Process alarms (3-year retention)
- TRIP_*: Trip events (7-year retention, safety compliance)
- USER_*: Manual operator notes (1-year retention)
- AUDIT_*: Compliance events (7-year retention)
Regex allows: SYSTEM_START, ALARM_HIGH_HIGH, TRIP_INITIATED, DATA_QUALITY_WARNING, etc.';

-- Fix #3c: Create view for active alarms only (OPERATOR UI)
CREATE OR REPLACE VIEW historian_raw.vw_active_alarms AS
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

COMMENT ON VIEW historian_raw.vw_active_alarms IS 
'Real-time active alarms view. Use for operator dashboards and alarm banners.
Per EVENT_ALARM_POLICY.md Section 9: Operators MUST use this view, never raw table.';

-- Fix #3d: Create alarm suppression schedule table (ENFORCES EVENT_ALARM_POLICY.md Section 4)
CREATE TABLE IF NOT EXISTS historian_meta.alarm_suppression_schedule (
    schedule_id SERIAL PRIMARY KEY,
    alarm_type_pattern TEXT NOT NULL,
    tag_id_pattern TEXT,
    suppress_start TIME NOT NULL,
    suppress_end TIME NOT NULL,
    days_of_week INTEGER[] NOT NULL CHECK (days_of_week <@ ARRAY[0,1,2,3,4,5,6]),
    reason TEXT,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    enabled BOOLEAN DEFAULT TRUE,
    CONSTRAINT valid_time_range CHECK (suppress_start < suppress_end)
);

COMMENT ON TABLE historian_meta.alarm_suppression_schedule IS 
'Time-based alarm suppression (EVENT_ALARM_POLICY.md Section 4).
Example: Suppress ALARM_LOW on night shifts (00:00-06:00) when operators absent.
days_of_week: 0=Sunday, 1=Monday, ..., 6=Saturday';

-- Fix #3e: Create trip event tracking table (PROCESS SAFETY REQUIREMENT)
CREATE TABLE IF NOT EXISTS historian_raw.trip_event_tracking (
    trip_event_id BIGSERIAL PRIMARY KEY,
    trip_time TIMESTAMPTZ NOT NULL,
    trip_tag_id TEXT NOT NULL,
    trip_category TEXT NOT NULL CHECK (trip_category IN ('PROCESS_TRIP', 'SAFETY_TRIP', 'EMERGENCY_TRIP')),
    initiating_alarm_id BIGINT,
    equipment_affected TEXT NOT NULL,
    trip_duration_seconds INTEGER,
    trip_cleared_at TIMESTAMPTZ,
    root_cause_tag_id TEXT,
    operator_notes TEXT,
    automated_diagnosis JSONB,
    production_loss_mw DOUBLE PRECISION,
    metadata JSONB,
    CONSTRAINT fk_trip_tag FOREIGN KEY (trip_tag_id) REFERENCES historian_meta.tag_master(tag_id)
);

CREATE INDEX idx_trip_event_time ON historian_raw.trip_event_tracking(trip_time DESC);
CREATE INDEX idx_trip_event_tag ON historian_raw.trip_event_tracking(trip_tag_id);
CREATE INDEX idx_trip_category ON historian_raw.trip_event_tracking(trip_category);

COMMENT ON TABLE historian_raw.trip_event_tracking IS 
'Trip event history for process safety and root cause analysis.
NOTE: initiating_alarm_id references historian_events(event_id) but FK constraint not enforced (TimescaleDB hypertable limitation). Application must validate referential integrity.
Records all PROCESS_TRIP, SAFETY_TRIP, EMERGENCY_TRIP events with causality linkage.
Application populates initiating_alarm_id to link alarm → trip causality.
Retention: 7 years (safety compliance requirement).';

-- Fix #3f: Create interlock state tracking table
CREATE TABLE IF NOT EXISTS historian_raw.interlock_state_tracking (
    interlock_event_id BIGSERIAL PRIMARY KEY,
    event_time TIMESTAMPTZ NOT NULL,
    interlock_tag_id TEXT NOT NULL,
    interlock_type TEXT NOT NULL CHECK (interlock_type IN ('PERMISSIVE', 'CONDITIONAL', 'SEQUENTIAL', 'PROTECTIVE')),
    interlock_state TEXT NOT NULL CHECK (interlock_state IN ('SATISFIED', 'VIOLATED', 'BYPASSED', 'UNKNOWN')),
    previous_state TEXT,
    state_duration_seconds INTEGER,
    affected_equipment TEXT,
    bypass_reason TEXT,
    bypass_authorized_by TEXT,
    bypass_expires_at TIMESTAMPTZ,
    related_trip_event_id BIGINT REFERENCES historian_raw.trip_event_tracking(trip_event_id),
    metadata JSONB,
    CONSTRAINT fk_interlock_tag FOREIGN KEY (interlock_tag_id) REFERENCES historian_meta.tag_master(tag_id)
);

CREATE INDEX idx_interlock_event_time ON historian_raw.interlock_state_tracking(event_time DESC);
CREATE INDEX idx_interlock_tag ON historian_raw.interlock_state_tracking(interlock_tag_id);
CREATE INDEX idx_interlock_state ON historian_raw.interlock_state_tracking(interlock_state);

COMMENT ON TABLE historian_raw.interlock_state_tracking IS 
'Interlock state change history for safety verification.
Records: PERMISSIVE (start conditions), CONDITIONAL (run conditions), SEQUENTIAL (order logic), PROTECTIVE (fault protection).
BYPASSED state requires authorization tracking for compliance.
Retention: 7 years (safety audit requirement).';

-- Sample suppression: Night shift low alarms
INSERT INTO historian_meta.alarm_suppression_schedule 
    (alarm_type_pattern, suppress_start, suppress_end, days_of_week, reason, created_by)
VALUES 
    ('ALARM_LOW%', '00:00:00', '06:00:00', ARRAY[1,2,3,4,5], 
     'Night shift - operators absent', 'system')
ON CONFLICT DO NOTHING;

-- Fix #3g: Create alarm acknowledgment function
CREATE OR REPLACE FUNCTION acknowledge_alarm(
    p_alarm_id BIGINT,
    p_acknowledged_by TEXT,
    p_notes TEXT DEFAULT NULL
) RETURNS BOOLEAN AS $$
DECLARE
    v_current_state TEXT;
BEGIN
    -- Get current alarm state
    SELECT alarm_state INTO v_current_state
    FROM historian_raw.historian_events
    WHERE event_id = p_alarm_id;
    
    -- Only ACTIVE alarms can be acknowledged
    IF v_current_state != 'ACTIVE' THEN
        RAISE NOTICE 'Alarm % cannot be acknowledged (current state: %)', p_alarm_id, v_current_state;
        RETURN FALSE;
    END IF;
    
    -- Update alarm to ACKNOWLEDGED state
    UPDATE historian_raw.historian_events
    SET 
        alarm_state = 'ACKNOWLEDGED',
        acknowledged_by = p_acknowledged_by,
        acknowledged_at = now(),
        message = COALESCE(message || E'\n' || 'ACK: ' || p_notes, message)
    WHERE event_id = p_alarm_id;
    
    -- Log acknowledgment event
    INSERT INTO historian_raw.historian_events 
        (time, tag_id, event_type, severity, message, metadata, parent_alarm_id)
    SELECT 
        now(),
        tag_id,
        'ALARM_ACKNOWLEDGED',
        2,
        format('Alarm %s acknowledged by %s', p_alarm_id, p_acknowledged_by),
        jsonb_build_object('notes', p_notes),
        p_alarm_id
    FROM historian_raw.historian_events
    WHERE event_id = p_alarm_id;
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION acknowledge_alarm(BIGINT, TEXT, TEXT) IS 
'Acknowledge an active alarm. Returns TRUE on success. Logs acknowledgment event.';

-- ================= PHASE 4: LATEST VALUE PRECEDENCE =================
-- Fix #4a: Improve latest value update with precedence rules

ALTER TABLE historian_raw.historian_latest_value
    ADD COLUMN IF NOT EXISTS last_sample_time TIMESTAMPTZ;

COMMENT ON COLUMN historian_raw.historian_latest_value.last_sample_time IS 
'Timestamp of the sample (different from updated_at which is write time). Used for precedence resolution.';

CREATE OR REPLACE FUNCTION update_latest_values_batch(
    tag_ids TEXT[],
    times TIMESTAMPTZ[],
    value_nums DOUBLE PRECISION[],
    value_texts TEXT[],
    value_bools BOOLEAN[],
    qualities TEXT[],
    mapping_versions BIGINT[]
) RETURNS void AS $$
BEGIN
    -- Update existing records with precedence rules
    UPDATE historian_raw.historian_latest_value AS lv
    SET 
        last_time = upd.last_time,
        last_value_num = upd.last_value_num,
        last_value_text = upd.last_value_text,
        last_value_bool = upd.last_value_bool,
        last_quality = upd.last_quality,
        last_mapping_version = upd.last_mapping_version,
        updated_at = now(),
        last_sample_time = upd.last_time
    FROM (
        SELECT 
            unnest(tag_ids) AS tag_id,
            unnest(times) AS last_time,
            unnest(value_nums) AS last_value_num,
            unnest(value_texts) AS last_value_text,
            unnest(value_bools) AS last_value_bool,
            unnest(qualities) AS last_quality,
            unnest(mapping_versions) AS last_mapping_version
    ) AS upd
    WHERE lv.tag_id = upd.tag_id
      -- Precedence rules:
      AND (
          lv.last_sample_time IS NULL                              -- 1. First write wins
          OR upd.last_time > lv.last_sample_time                   -- 2. Newer timestamp wins
          OR (upd.last_time = lv.last_sample_time                  -- 3. Same timestamp:
              AND upd.last_mapping_version > lv.last_mapping_version)   --    a. Newer mapping version wins
          OR (upd.last_time = lv.last_sample_time 
              AND upd.last_mapping_version = lv.last_mapping_version
              AND upd.last_quality = 'G' AND lv.last_quality != 'G')    --    b. Good quality wins over Bad/Uncertain
      );
    
    -- Insert new tags
    INSERT INTO historian_raw.historian_latest_value 
        (tag_id, last_time, last_value_num, last_value_text, 
         last_value_bool, last_quality, last_mapping_version, updated_at, last_sample_time)
    SELECT 
        upd.tag_id, upd.last_time, upd.last_value_num, upd.last_value_text,
        upd.last_value_bool, upd.last_quality, upd.last_mapping_version, now(), upd.last_time
    FROM (
        SELECT 
            unnest(tag_ids) AS tag_id,
            unnest(times) AS last_time,
            unnest(value_nums) AS last_value_num,
            unnest(value_texts) AS last_value_text,
            unnest(value_bools) AS last_value_bool,
            unnest(qualities) AS last_quality,
            unnest(mapping_versions) AS last_mapping_version
    ) AS upd
    WHERE NOT EXISTS (
        SELECT 1 FROM historian_raw.historian_latest_value 
        WHERE tag_id = upd.tag_id
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION update_latest_values_batch IS 
'Updates latest values with precedence: 1) Newer time, 2) Newer mapping version, 3) Good quality over Bad/Uncertain';

-- ================= PHASE 5: MAPPING VERSION DISCIPLINE =================
-- Fix #5a: Add mapping version validation

ALTER TABLE historian_meta.writer_checkpoint
    ADD COLUMN IF NOT EXISTS last_successful_write_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS stale_mapping_warnings INTEGER DEFAULT 0;

CREATE OR REPLACE FUNCTION validate_writer_mapping_version(
    p_writer_name TEXT,
    p_current_mapping_version BIGINT
) RETURNS TABLE(is_valid BOOLEAN, message TEXT, latest_version BIGINT) AS $$
DECLARE
    v_latest_version BIGINT;
    v_version_lag INTEGER;
BEGIN
    -- Get latest mapping version from tag_master
    SELECT MAX(mapping_version) INTO v_latest_version
    FROM historian_meta.tag_master;

    v_version_lag := v_latest_version - p_current_mapping_version;

    IF v_version_lag = 0 THEN
        RETURN QUERY SELECT TRUE, 'Mapping version current', v_latest_version;
    ELSIF v_version_lag <= 5 THEN
        RETURN QUERY SELECT 
            TRUE,
            format('Writer %s using mapping v%s (latest: v%s, lag: %s versions - acceptable)', 
                   p_writer_name, p_current_mapping_version, v_latest_version, v_version_lag),
            v_latest_version;
    ELSE
        RETURN QUERY SELECT 
            FALSE, 
            format('Writer %s using STALE mapping v%s (latest: v%s, lag: %s versions - RELOAD REQUIRED)', 
                   p_writer_name, p_current_mapping_version, v_latest_version, v_version_lag),
            v_latest_version;
    END IF;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION validate_writer_mapping_version IS 
'Validates writer mapping version. Lag >5 versions requires reload. Returns (is_valid, message, latest_version).';

-- ================= PHASE 6: RETENTION & COMPRESSION MONITORING =================
-- Fix #6a: Add retention health monitoring

CREATE TABLE IF NOT EXISTS historian_mon.retention_health (
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

CREATE OR REPLACE FUNCTION check_retention_health()
RETURNS TABLE(
    status TEXT,
    oldest_data_age_days INTEGER,
    compression_coverage_pct DOUBLE PRECISION,
    total_size_mb BIGINT,
    warnings TEXT[]
) AS $$
DECLARE
    v_warnings TEXT[] := ARRAY[]::TEXT[];
    v_oldest_age_days INTEGER;
    v_compression_pct DOUBLE PRECISION;
    v_total_size_mb BIGINT;
    v_uncompressed_mb BIGINT;
    v_compressed_mb BIGINT;
BEGIN
    -- Check oldest data age
    SELECT EXTRACT(DAY FROM now() - MIN(range_start))::INTEGER
    INTO v_oldest_age_days
    FROM timescaledb_information.chunks
    WHERE hypertable_name = 'historian_timeseries';

    IF v_oldest_age_days > 730 THEN
        v_warnings := array_append(v_warnings, 
            format('Data retention exceeded: %s days (policy: 730 days)', v_oldest_age_days));
    END IF;

    -- Check compression coverage
    SELECT 
        100.0 * COUNT(*) FILTER (WHERE compression_status = 'Compressed') / NULLIF(COUNT(*), 0),
        SUM(CASE WHEN compression_status = 'Uncompressed' THEN uncompressed_total_bytes ELSE 0 END) / 1024 / 1024,
        SUM(CASE WHEN compression_status = 'Compressed' THEN compressed_total_bytes ELSE 0 END) / 1024 / 1024
    INTO v_compression_pct, v_uncompressed_mb, v_compressed_mb
    FROM timescaledb_information.chunks
    WHERE hypertable_name = 'historian_timeseries';

    v_total_size_mb := COALESCE(v_uncompressed_mb, 0) + COALESCE(v_compressed_mb, 0);

    IF v_compression_pct < 80 THEN
        v_warnings := array_append(v_warnings, 
            format('Low compression coverage: %.1f%% (target: 80%%+)', COALESCE(v_compression_pct, 0)));
    END IF;

    -- Check disk usage
    IF v_total_size_mb > 100000 THEN  -- >100GB
        v_warnings := array_append(v_warnings, 
            format('High disk usage: %s MB (%.1f GB)', v_total_size_mb, v_total_size_mb/1024.0));
    END IF;

    RETURN QUERY SELECT 
        CASE 
            WHEN array_length(v_warnings, 1) > 0 THEN 'WARNING'
            ELSE 'HEALTHY'
        END,
        COALESCE(v_oldest_age_days, 0),
        COALESCE(v_compression_pct, 0),
        COALESCE(v_total_size_mb, 0),
        COALESCE(v_warnings, ARRAY[]::TEXT[]);
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION check_retention_health() IS 
'Health check for retention and compression. Run daily. Returns (status, age, compression%, size, warnings).';

-- Fix #6b: Create retention cleanup function (ENFORCES EVENT_ALARM_POLICY.md Section 6)
-- NOTE: This function ALWAYS returns MULTIPLE ROWS (7 rows per execution)
-- Each row represents deletion stats for one event category (SYSTEM/WRITER, DATA_QUALITY, USER, ALARM, AUDIT, TRIP_EVENTS, INTERLOCK_STATES)
-- Rows with deleted_count=0 indicate no deletions occurred (expected when data is within retention window)
CREATE OR REPLACE FUNCTION cleanup_old_events()
RETURNS TABLE(
    event_type_prefix TEXT,
    deleted_count BIGINT,
    retention_days INTEGER
) AS $$
DECLARE
    v_deleted_count BIGINT;
BEGIN
    -- SYSTEM_* and WRITER_* events: 30-day retention
    DELETE FROM historian_raw.historian_events
    WHERE (event_type LIKE 'SYSTEM_%' OR event_type LIKE 'WRITER_%')
      AND time < now() - INTERVAL '30 days';
    GET DIAGNOSTICS v_deleted_count = ROW_COUNT;
    RETURN QUERY SELECT 'SYSTEM/WRITER'::TEXT, v_deleted_count, 30;

    -- DATA_QUALITY_* events: 90-day retention
    DELETE FROM historian_raw.historian_events
    WHERE event_type LIKE 'DATA_QUALITY_%'
      AND time < now() - INTERVAL '90 days';
    GET DIAGNOSTICS v_deleted_count = ROW_COUNT;
    RETURN QUERY SELECT 'DATA_QUALITY'::TEXT, v_deleted_count, 90;

    -- USER_* events: 1-year retention
    DELETE FROM historian_raw.historian_events
    WHERE event_type LIKE 'USER_%'
      AND time < now() - INTERVAL '1 year';
    GET DIAGNOSTICS v_deleted_count = ROW_COUNT;
    RETURN QUERY SELECT 'USER'::TEXT, v_deleted_count, 365;

    -- ALARM_* events: 3-year retention (compressed)
    DELETE FROM historian_raw.historian_events
    WHERE event_type LIKE 'ALARM_%'
      AND time < now() - INTERVAL '3 years';
    GET DIAGNOSTICS v_deleted_count = ROW_COUNT;
    RETURN QUERY SELECT 'ALARM'::TEXT, v_deleted_count, 1095;

    -- AUDIT_* events: NEVER DELETE (7-year minimum, keep forever for compliance)
    RETURN QUERY SELECT 'AUDIT'::TEXT, 0::BIGINT, 2555;  -- Report 0 deletions

    -- TRIP/INTERLOCK events: 7-year retention (safety compliance requirement)
    -- Delete trips older than 7 years
    DELETE FROM historian_raw.trip_event_tracking
    WHERE trip_time < now() - INTERVAL '7 years';
    GET DIAGNOSTICS v_deleted_count = ROW_COUNT;
    RETURN QUERY SELECT 'TRIP_EVENTS'::TEXT, v_deleted_count, 2555;

    -- Delete interlock states older than 7 years
    DELETE FROM historian_raw.interlock_state_tracking
    WHERE event_time < now() - INTERVAL '7 years';
    GET DIAGNOSTICS v_deleted_count = ROW_COUNT;
    RETURN QUERY SELECT 'INTERLOCK_STATES'::TEXT, v_deleted_count, 2555;

    RETURN;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_old_events() IS 
'Automated retention cleanup per EVENT_ALARM_POLICY.md Section 6.

RETURNS MULTIPLE ROWS (7 per execution):
- SYSTEM/WRITER: 30 days
- DATA_QUALITY: 90 days
- USER: 1 year
- ALARM: 3 years (compressed)
- AUDIT: 0 deletions (never deleted - compliance requirement)
- TRIP_EVENTS: 7 years (safety compliance)
- INTERLOCK_STATES: 7 years (safety audit)

Rows with deleted_count=0 are normal (data within retention window).
Schedule: Run daily via TimescaleDB job or pg_cron.';

-- Fix #6c: Create additional enforcement views (EVENT_ALARM_POLICY.md Section 9)
CREATE OR REPLACE VIEW historian_raw.vw_system_events AS
SELECT event_id, time, event_type, message, severity, metadata
FROM historian_raw.historian_events
WHERE event_type LIKE 'SYSTEM_%' OR event_type LIKE 'WRITER_%'
ORDER BY time DESC;

COMMENT ON VIEW historian_raw.vw_system_events IS 
'System infrastructure events for IT monitoring (EVENT_ALARM_POLICY.md).
30-day retention. Shows startup, shutdown, compression, backups, etc.';

CREATE OR REPLACE VIEW historian_raw.vw_data_quality AS
SELECT event_id, time, tag_id, event_type, message, severity, metadata
FROM historian_raw.historian_events
WHERE event_type LIKE 'DATA_QUALITY_%'
ORDER BY time DESC;

COMMENT ON VIEW historian_raw.vw_data_quality IS 
'Data quality warnings for process engineers (EVENT_ALARM_POLICY.md).
90-day retention. Shows validation errors, oversized values, type conversions, etc.';

CREATE OR REPLACE VIEW historian_raw.vw_audit_trail AS
SELECT event_id, time, event_type, message, severity, metadata, 
       (metadata->>'user_id') AS user_id,
       (metadata->>'action') AS action
FROM historian_raw.historian_events
WHERE event_type LIKE 'AUDIT_%'
ORDER BY time DESC;

COMMENT ON VIEW historian_raw.vw_audit_trail IS 
'Audit trail for compliance (EVENT_ALARM_POLICY.md).
7-year minimum retention (never deleted). Shows user actions, config changes, alarm modifications.';

CREATE OR REPLACE VIEW historian_raw.vw_events_timeline AS
SELECT 
    event_id, 
    time, 
    tag_id,
    event_type,
    CASE 
        WHEN event_type LIKE 'SYSTEM_%' OR event_type LIKE 'WRITER_%' THEN 'SYSTEM'
        WHEN event_type LIKE 'DATA_QUALITY_%' THEN 'DATA_QUALITY'
        WHEN event_type LIKE 'ALARM_%' THEN 'ALARM'
        WHEN event_type LIKE 'USER_%' THEN 'USER'
        WHEN event_type LIKE 'AUDIT_%' THEN 'AUDIT'
        ELSE 'UNKNOWN'
    END AS event_category,
    message,
    severity,
    alarm_state,
    alarm_priority,
    metadata
FROM historian_raw.historian_events
ORDER BY time DESC;

COMMENT ON VIEW historian_raw.vw_events_timeline IS 
'Unified event timeline for root cause analysis (EVENT_ALARM_POLICY.md).
Shows all event types chronologically with category tagging.
Use for correlating alarms with system events and data quality issues.';

-- Fix #6d: Create trip analysis views
CREATE OR REPLACE VIEW historian_raw.vw_trip_causality AS
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
    EXTRACT(EPOCH FROM (t.trip_time - e.time)) AS alarm_to_trip_seconds,
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

COMMENT ON VIEW historian_raw.vw_trip_causality IS 
'Trip causality analysis view. Links trip events → initiating alarms → root cause tags.
Use for: Trip frequency analysis, alarm → trip correlation, production loss attribution.
Client application populates initiating_alarm_id and root_cause_tag_id fields.';

CREATE OR REPLACE VIEW historian_raw.vw_interlock_violations AS
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

COMMENT ON VIEW historian_raw.vw_interlock_violations IS 
'Interlock violations and bypasses for safety audit.
Shows: Active violations, active bypasses, expired bypasses.
Compliance requirement: All bypasses must have authorization + expiry.
Client application must enforce bypass approval workflow.';

CREATE OR REPLACE VIEW historian_raw.vw_trip_frequency_by_equipment AS
SELECT 
    equipment_affected,
    trip_category,
    COUNT(*) AS trip_count,
    AVG(trip_duration_seconds) AS avg_duration_seconds,
    SUM(production_loss_mw) AS total_production_loss_mw,
    MIN(trip_time) AS first_trip,
    MAX(trip_time) AS last_trip,
    EXTRACT(DAY FROM (MAX(trip_time) - MIN(trip_time))) AS observation_period_days,
    COUNT(*) / NULLIF(EXTRACT(DAY FROM (MAX(trip_time) - MIN(trip_time))), 0) AS trips_per_day
FROM historian_raw.trip_event_tracking
GROUP BY equipment_affected, trip_category
ORDER BY trip_count DESC;

COMMENT ON VIEW historian_raw.vw_trip_frequency_by_equipment IS 
'Trip frequency analysis by equipment and category.
Use for: Identifying problematic equipment, MTBF calculation, maintenance prioritization.
Production loss attribution for cost analysis.';

-- ================= PHASE 6E: VALUE RANGE TRACKING & THRESHOLD HELPERS =================

-- Function: Update observed min/max values for tags
CREATE OR REPLACE FUNCTION update_tag_value_ranges()
RETURNS TABLE(
    tag_id TEXT,
    current_min DOUBLE PRECISION,
    current_max DOUBLE PRECISION,
    samples_analyzed BIGINT
) AS $$
BEGIN
    RETURN QUERY
    WITH value_stats AS (
        SELECT 
            ts.tag_id,
            MIN(ts.value_num) AS min_val,
            MAX(ts.value_num) AS max_val,
            COUNT(*) AS sample_count
        FROM historian_raw.historian_timeseries ts
        JOIN historian_meta.tag_master tm ON ts.tag_id = tm.tag_id
        WHERE ts.time > COALESCE(tm.observation_start_time, now() - INTERVAL '7 days')
          AND ts.value_num IS NOT NULL
          AND tm.data_type = 'Double'
        GROUP BY ts.tag_id
    )
    UPDATE historian_meta.tag_master tm
    SET 
        observed_min_value = LEAST(COALESCE(tm.observed_min_value, vs.min_val), vs.min_val),
        observed_max_value = GREATEST(COALESCE(tm.observed_max_value, vs.max_val), vs.max_val),
        observation_sample_count = COALESCE(tm.observation_sample_count, 0) + vs.sample_count,
        last_observation_update = now(),
        observation_start_time = COALESCE(tm.observation_start_time, now() - INTERVAL '7 days')
    FROM value_stats vs
    WHERE tm.tag_id = vs.tag_id
    RETURNING tm.tag_id, tm.observed_min_value, tm.observed_max_value, tm.observation_sample_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION update_tag_value_ranges() IS 
'Updates observed min/max values for all numeric tags based on historical data.
Run daily or after data collection period to establish baselines for alarm thresholds.';

-- Function: Suggest alarm thresholds based on observed ranges
CREATE OR REPLACE FUNCTION suggest_alarm_thresholds(p_tag_id TEXT DEFAULT NULL)
RETURNS TABLE(
    tag_id TEXT,
    observed_min DOUBLE PRECISION,
    observed_max DOUBLE PRECISION,
    suggested_low_low DOUBLE PRECISION,
    suggested_low DOUBLE PRECISION,
    suggested_high DOUBLE PRECISION,
    suggested_high_high DOUBLE PRECISION,
    sample_count BIGINT,
    recommendation TEXT
) AS $$
BEGIN
    RETURN QUERY
    WITH tag_ranges AS (
        SELECT 
            tm.tag_id,
            tm.tag_name,
            tm.observed_min_value,
            tm.observed_max_value,
            tm.observation_sample_count,
            (tm.observed_max_value - tm.observed_min_value) AS value_range
        FROM historian_meta.tag_master tm
        WHERE (p_tag_id IS NULL OR tm.tag_id = p_tag_id)
          AND tm.observed_min_value IS NOT NULL
          AND tm.observed_max_value IS NOT NULL
          AND tm.data_type = 'Double'
    )
    SELECT 
        tr.tag_id,
        tr.observed_min_value,
        tr.observed_max_value,
        -- LOW-LOW: 5% below observed min
        ROUND((tr.observed_min_value - tr.value_range * 0.05)::numeric, 2)::DOUBLE PRECISION,
        -- LOW: 10% below observed min
        ROUND((tr.observed_min_value - tr.value_range * 0.10)::numeric, 2)::DOUBLE PRECISION,
        -- HIGH: 10% above observed max
        ROUND((tr.observed_max_value + tr.value_range * 0.10)::numeric, 2)::DOUBLE PRECISION,
        -- HIGH-HIGH: 15% above observed max
        ROUND((tr.observed_max_value + tr.value_range * 0.15)::numeric, 2)::DOUBLE PRECISION,
        tr.observation_sample_count,
        CASE 
            WHEN tr.observation_sample_count < 1000 THEN 'WARNING: Low sample count, collect more data'
            WHEN tr.value_range < 1.0 THEN 'INFO: Narrow range, may be digital signal (0/1)'
            WHEN tr.observation_sample_count >= 10000 THEN 'GOOD: Sufficient data for reliable thresholds'
            ELSE 'OK: Moderate confidence, consider longer observation period'
        END
    FROM tag_ranges tr
    ORDER BY tr.tag_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION suggest_alarm_thresholds(TEXT) IS 
'Analyzes observed value ranges and suggests alarm thresholds.
Logic: HIGH = max + 10%, HIGH-HIGH = max + 15%, LOW = min - 10%, LOW-LOW = min - 5%.
Call after running update_tag_value_ranges() with sufficient data (>1000 samples recommended).';

-- Function: Apply suggested thresholds to tag_master
CREATE OR REPLACE FUNCTION apply_suggested_alarm_thresholds(
    p_tag_id TEXT,
    p_alarm_priority INTEGER DEFAULT 3,
    p_deadband DOUBLE PRECISION DEFAULT NULL
)
RETURNS BOOLEAN AS $$
DECLARE
    v_thresholds RECORD;
BEGIN
    -- Get suggested thresholds
    SELECT * INTO v_thresholds
    FROM suggest_alarm_thresholds(p_tag_id)
    WHERE tag_id = p_tag_id;
    
    IF NOT FOUND THEN
        RAISE NOTICE 'No threshold suggestions found for tag: %. Run update_tag_value_ranges() first.', p_tag_id;
        RETURN FALSE;
    END IF;
    
    -- Apply thresholds
    UPDATE historian_meta.tag_master
    SET 
        alarm_low_low_threshold = v_thresholds.suggested_low_low,
        alarm_low_threshold = v_thresholds.suggested_low,
        alarm_high_threshold = v_thresholds.suggested_high,
        alarm_high_high_threshold = v_thresholds.suggested_high_high,
        alarm_priority = p_alarm_priority,
        alarm_deadband = COALESCE(p_deadband, (v_thresholds.observed_max - v_thresholds.observed_min) * 0.02),
        alarm_enabled = FALSE  -- Keep disabled until manually reviewed
    WHERE tag_id = p_tag_id;
    
    RAISE NOTICE 'Applied thresholds for %: HIGH=%, HIGH-HIGH=%, LOW=%, LOW-LOW=%', 
        p_tag_id, 
        v_thresholds.suggested_high, 
        v_thresholds.suggested_high_high,
        v_thresholds.suggested_low,
        v_thresholds.suggested_low_low;
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION apply_suggested_alarm_thresholds(TEXT, INTEGER, DOUBLE PRECISION) IS 
'Applies suggested alarm thresholds to tag_master for specified tag.
Thresholds are set but alarm_enabled remains FALSE until manual review.
Usage: SELECT apply_suggested_alarm_thresholds(''Random.Real4'', 3, 2.0);';

-- View: Tag range analysis (for verification)
CREATE OR REPLACE VIEW historian_meta.vw_tag_value_ranges AS
SELECT 
    tm.tag_id,
    tm.tag_name,
    tm.data_type,
    tm.eng_unit,
    tm.observed_min_value,
    tm.observed_max_value,
    (tm.observed_max_value - tm.observed_min_value) AS value_range,
    tm.observation_sample_count,
    tm.observation_start_time,
    tm.last_observation_update,
    EXTRACT(EPOCH FROM (tm.last_observation_update - tm.observation_start_time)) / 3600 AS observation_hours,
    -- Suggested thresholds
    ROUND((tm.observed_max_value + (tm.observed_max_value - tm.observed_min_value) * 0.10)::numeric, 2) AS suggested_high,
    ROUND((tm.observed_max_value + (tm.observed_max_value - tm.observed_min_value) * 0.15)::numeric, 2) AS suggested_high_high,
    -- Current configured thresholds
    tm.alarm_high_threshold AS configured_high,
    tm.alarm_high_high_threshold AS configured_high_high,
    tm.alarm_enabled,
    tm.alarm_priority,
    CASE 
        WHEN tm.observation_sample_count < 1000 THEN 'INSUFFICIENT_DATA'
        WHEN tm.alarm_enabled = true THEN 'ACTIVE'
        WHEN tm.alarm_high_threshold IS NOT NULL THEN 'CONFIGURED_DISABLED'
        ELSE 'NOT_CONFIGURED'
    END AS alarm_status
FROM historian_meta.tag_master tm
WHERE tm.data_type = 'Double'
  AND tm.enabled = true
ORDER BY tm.observation_sample_count DESC NULLS LAST;

COMMENT ON VIEW historian_meta.vw_tag_value_ranges IS 
'Tag value range analysis with suggested vs configured alarm thresholds.
Use to verify observation data quality before setting alarm thresholds.';

-- ================= PHASE 7: SCHEMA GOVERNANCE =================
-- Fix #7a: Add schema migration tracking

CREATE TABLE IF NOT EXISTS historian_meta.schema_migrations (
    migration_id INTEGER PRIMARY KEY,
    migration_name TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_by TEXT NOT NULL,
    description TEXT,
    sql_file_hash TEXT,
    rollback_sql TEXT,
    status TEXT CHECK (status IN ('APPLIED', 'FAILED', 'ROLLED_BACK')) NOT NULL DEFAULT 'APPLIED'
);

CREATE OR REPLACE FUNCTION get_schema_version()
RETURNS INTEGER AS $$
    SELECT COALESCE(MAX(migration_id), 0) 
    FROM historian_meta.schema_migrations 
    WHERE status = 'APPLIED';
$$ LANGUAGE sql;

COMMENT ON TABLE historian_meta.schema_migrations IS 
'Schema version control. Each migration increments migration_id. Current version = MAX(migration_id).';

COMMENT ON FUNCTION get_schema_version() IS 
'Returns current schema version. Use in application startup validation.';

-- Record this migration
INSERT INTO historian_meta.schema_migrations 
    (migration_id, migration_name, applied_by, description, status)
VALUES 
    (2, 'operational_hardening', 'system', 
     'Added: schema tolerance, duplicate handling, alarm lifecycle, precedence rules, monitoring',
     'APPLIED')
ON CONFLICT (migration_id) DO NOTHING;

-- ================= VALIDATION & EXAMPLES =================

-- Check what was done
DO $$
DECLARE
    v_schema_version INTEGER;
    v_alarm_columns_added BOOLEAN;
    v_unique_constraint_added BOOLEAN;
BEGIN
    SELECT get_schema_version() INTO v_schema_version;
    
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'historian_raw' 
          AND table_name = 'historian_events'
          AND column_name = 'alarm_state'
    ) INTO v_alarm_columns_added;
    
    SELECT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'uq_timeseries_time_tag'
    ) INTO v_unique_constraint_added;
    
    RAISE NOTICE '=== OPERATIONAL HARDENING COMPLETE ===';
    RAISE NOTICE 'Schema Version: %', v_schema_version;
    RAISE NOTICE 'Alarm Lifecycle Columns: %', CASE WHEN v_alarm_columns_added THEN 'ADDED' ELSE 'MISSING' END;
    RAISE NOTICE 'Duplicate Constraint: %', CASE WHEN v_unique_constraint_added THEN 'ADDED' ELSE 'MISSING' END;
    RAISE NOTICE '';
    RAISE NOTICE 'EVENT_ALARM_POLICY.md enforcement:';
    RAISE NOTICE '- Event domain prefixes (Section 1): ENFORCED via chk_event_type regex';
    RAISE NOTICE '- Alarm suppression schedule (Section 4): TABLE CREATED (alarm_suppression_schedule)';
    RAISE NOTICE '- Retention by event type (Section 6): FUNCTION CREATED (cleanup_old_events)';
    RAISE NOTICE '- Operator views (Section 9): CREATED (vw_active_alarms, vw_system_events, vw_data_quality, vw_audit_trail, vw_events_timeline)';
    RAISE NOTICE '';
    RAISE NOTICE '';
    RAISE NOTICE 'Trip/Interlock provisions (PROCESS SAFETY):';
    RAISE NOTICE '- trip_category column in tag_master: %', 
        (SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='tag_master' AND column_name='trip_category'));
    RAISE NOTICE '- trip_event_tracking table: %', 
        (SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='trip_event_tracking'));
    RAISE NOTICE '- interlock_state_tracking table: %', 
        (SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='interlock_state_tracking'));
    RAISE NOTICE '- Trip causality view: %', 
        (SELECT EXISTS(SELECT 1 FROM information_schema.views WHERE table_name='vw_trip_causality'));
    RAISE NOTICE '';
    RAISE NOTICE 'Next steps:';
    RAISE NOTICE '1. Tag trip/interlock tags in tag_master (set trip_category, interlock_type, is_trip_initiator)';
    RAISE NOTICE '2. Implement trip detection logic in C# application (populate trip_event_tracking)';
    RAISE NOTICE '3. Implement interlock state monitoring (populate interlock_state_tracking)';
    RAISE NOTICE '4. Link alarms → trips (populate initiating_alarm_id in trip_event_tracking)';
    RAISE NOTICE '5. Schedule retention cleanup: SELECT add_job(''cleanup_old_events'', ''1 day'');';
    RAISE NOTICE '6. Implement alarm deduplication (5-min window) in application logic';
    RAISE NOTICE '7. Implement dynamic priority calculation in C# services';
    RAISE NOTICE '8. Add authentication to alarm acknowledgment API';
    RAISE NOTICE '9. Deploy to production for 1-week burn-in';
    RAISE NOTICE '';
    RAISE NOTICE 'Run test scenarios below to verify functionality.';
END $$;

-- ================= CONFIGURATION ADJUSTMENT EXAMPLES =================

/* 
=== How to Adjust Limits Without Code Changes ===

-- Increase truncation limit to 2000 chars (if you need more)
UPDATE historian_meta.data_quality_limits 
SET setting_value = 2000, updated_by = 'admin', updated_at = now()
WHERE setting_name = 'value_text_max_length';

-- Reduce warning threshold to 200 chars (more aggressive)
UPDATE historian_meta.data_quality_limits 
SET setting_value = 200, updated_by = 'admin', updated_at = now()
WHERE setting_name = 'value_text_warn_length';

-- Increase log cooldown to 10 minutes (less frequent warnings)
UPDATE historian_meta.data_quality_limits 
SET setting_value = 600, updated_by = 'admin', updated_at = now()
WHERE setting_name = 'log_cooldown_seconds';

-- View current settings
SELECT * FROM historian_meta.data_quality_limits ORDER BY setting_name;
*/

-- ================= TEST SCENARIOS =================

/* 
=== EXAMPLE 1: Schema Tolerance with Smart Truncation ===

Scenario: PLC malfunctions, sends 50KB garbage string every second

Before hardening: 
- COPY crashes OR accepts all → disk fills up (50KB × 86400/day = 4.3GB/day)
- Event log floods (86400 warnings/day)

After hardening: 
- Truncates to 1000 chars (safe limit)
- Logs warning ONCE per 5 minutes per tag (max 288 warnings/day, not 86400)
- Marks quality as 'U' (Uncertain - data modified)
- System keeps running

Test:
*/
/*
-- Simulate PLC sending garbage (15KB string)
INSERT INTO historian_raw.historian_timeseries 
    (time, tag_id, value_text, quality, sample_source, mapping_version)
VALUES 
    (now(), 'TEST_TAG', repeat('GARBAGE_', 2000), 'G', 'OPC', 1);

-- Check what was stored (should be truncated to 1000 chars)
SELECT tag_id, length(value_text) as stored_length, quality 
FROM historian_raw.historian_timeseries 
WHERE tag_id = 'TEST_TAG' 
ORDER BY time DESC LIMIT 1;

Expected: 
- stored_length = 1000 (truncated)
- quality = 'U' (Uncertain - data was modified)

-- Check warning was logged (only ONCE even if inserted multiple times)
SELECT * FROM historian_raw.historian_events 
WHERE event_type = 'DATA_QUALITY_WARNING' 
  AND tag_id = 'TEST_TAG'
ORDER BY time DESC LIMIT 1;

Expected: One event with message "Oversized value_text detected - TRUNCATED from 16000 to 1000 chars"

-- Try inserting again within 5 minutes (should NOT create new event)
INSERT INTO historian_raw.historian_timeseries 
    (time, tag_id, value_text, quality, sample_source, mapping_version)
VALUES 
    (now(), 'TEST_TAG', repeat('MORE_GARBAGE_', 2000), 'G', 'OPC', 1);

-- Check event count (should still be 1)
SELECT COUNT(*) FROM historian_raw.historian_events 
WHERE event_type = 'DATA_QUALITY_WARNING' 
  AND tag_id = 'TEST_TAG'
  AND time > now() - INTERVAL '10 minutes';

Expected: COUNT = 1 (rate limiting working - prevented log flood)

Storage Impact:
- Without truncation: 15KB × 86400 samples/day = 1.3 GB/day
- With truncation: 1KB × 86400 samples/day = 86 MB/day
- Savings: 93% storage reduction + prevents disk full
*/

/* 
=== EXAMPLE 2: Duplicate Handling ===

Before hardening: Same sample written 3 times = 200% data inflation
After hardening: Last write wins, only 1 row in DB

Test (run in C# or using ON CONFLICT):
*/
/*
-- First write
INSERT INTO historian_raw.historian_timeseries 
    (time, tag_id, value_num, quality, sample_source, mapping_version)
VALUES 
    ('2025-12-21 10:00:00+00', 'TEMP_01', 25.5, 'G', 'OPC', 1);

-- Duplicate write (should update, not insert)
INSERT INTO historian_raw.historian_timeseries 
    (time, tag_id, value_num, quality, sample_source, mapping_version)
VALUES 
    ('2025-12-21 10:00:00+00', 'TEMP_01', 25.8, 'G', 'OPC', 1)
ON CONFLICT (time, tag_id) DO UPDATE SET
    value_num = EXCLUDED.value_num,
    quality = EXCLUDED.quality;

-- Check: Only 1 row exists
SELECT COUNT(*) FROM historian_raw.historian_timeseries 
WHERE time = '2025-12-21 10:00:00+00' AND tag_id = 'TEMP_01';

Expected: COUNT = 1, value_num = 25.8 (last write won)
*/

/* 
=== EXAMPLE 3: Alarm Lifecycle ===

Scenario: High temperature alarm → acknowledged by operator → cleared when temp drops

Test:
*/
/*
-- 1. Raise alarm (temperature exceeds 100°C)
INSERT INTO historian_raw.historian_events 
    (time, tag_id, event_type, severity, message, alarm_state, alarm_priority, alarm_setpoint, alarm_actual_value)
VALUES 
    (now(), 'TEMP_01', 'ALARM_HIGH', 4, 'Temperature exceeded 100°C', 
     'ACTIVE', 4, 100.0, 105.3);

-- 2. Operator acknowledges alarm
SELECT acknowledge_alarm(
    (SELECT event_id FROM historian_raw.historian_events 
     WHERE tag_id = 'TEMP_01' AND alarm_state = 'ACTIVE' 
     ORDER BY time DESC LIMIT 1),
    'operator_john',
    'Investigating furnace cooling system'
);

-- 3. Check active alarms dashboard
SELECT * FROM historian_raw.vw_active_alarms;

-- 4. Clear alarm (temperature back to normal)
UPDATE historian_raw.historian_events
SET 
    alarm_state = 'CLEARED',
    cleared_at = now()
WHERE event_id = (
    SELECT event_id FROM historian_raw.historian_events 
    WHERE tag_id = 'TEMP_01' AND alarm_state = 'ACKNOWLEDGED' 
    ORDER BY time DESC LIMIT 1
);

Expected: 
- Alarm goes ACTIVE → ACKNOWLEDGED → CLEARED
- vw_active_alarms shows alarm only while ACTIVE/ACKNOWLEDGED
- Acknowledgment event logged with operator name
*/

/* 
=== EXAMPLE 4: Latest Value Precedence ===

Scenario: Out-of-order samples arrive (network lag, backfill)

Test:
*/
/*
-- 1. Write newer sample first
SELECT update_latest_values_batch(
    ARRAY['PRESSURE_01'],
    ARRAY['2025-12-21 10:05:00+00'::TIMESTAMPTZ],
    ARRAY[150.5],
    ARRAY[NULL::TEXT],
    ARRAY[NULL::BOOLEAN],
    ARRAY['G'],
    ARRAY[1::BIGINT]
);

-- 2. Write older sample (should be ignored)
SELECT update_latest_values_batch(
    ARRAY['PRESSURE_01'],
    ARRAY['2025-12-21 10:00:00+00'::TIMESTAMPTZ],
    ARRAY[148.2],
    ARRAY[NULL::TEXT],
    ARRAY[NULL::BOOLEAN],
    ARRAY['G'],
    ARRAY[1::BIGINT]
);

-- 3. Check latest value
SELECT tag_id, last_time, last_value_num, last_sample_time 
FROM historian_raw.historian_latest_value 
WHERE tag_id = 'PRESSURE_01';

Expected: 
- last_value_num = 150.5 (newer timestamp wins)
- last_time = 2025-12-21 10:05:00 (not 10:00:00)
*/

/* 
=== EXAMPLE 5: Mapping Version Validation ===

Scenario: Writer is using stale tag mapping (missed reload)

Test:
*/
/*
-- Simulate mapping update (increment version for some tags)
UPDATE historian_meta.tag_master 
SET mapping_version = 10 
WHERE tag_id IN ('TEMP_01', 'PRESSURE_01');

-- Writer validates its mapping version
SELECT * FROM validate_writer_mapping_version('HistorianIngestService', 5);

Expected:
- is_valid = FALSE
- message = "Writer using STALE mapping v5 (latest: v10, lag: 5 versions - RELOAD REQUIRED)"
- latest_version = 10
*/

/* 
=== EXAMPLE 6: Retention Health Check ===

Test:
*/
/*
SELECT * FROM check_retention_health();

Expected output example:
status     | oldest_data_age_days | compression_coverage_pct | total_size_mb | warnings
-----------+----------------------+--------------------------+---------------+----------
HEALTHY    | 365                  | 92.5                     | 15240         | {}

OR if issues:
WARNING    | 800                  | 65.3                     | 125000        | {"Data retention exceeded: 800 days...", "Low compression coverage..."}
*/

-- ================= ROLLBACK (IF NEEDED) =================
/*
-- To rollback these changes:

-- Test #7: Event type prefix validation (NEW - EVENT_ALARM_POLICY.md enforcement)
DO $$
BEGIN
    RAISE NOTICE '=== Test #7: Event Type Prefix Validation ===';
    
    -- Valid event types (should succeed)
    INSERT INTO historian_raw.historian_events 
        (time, event_type, message, severity)
    VALUES 
        (now(), 'SYSTEM_STARTUP_COMPLETE', 'System started successfully', 'INFO'),
        (now(), 'ALARM_HIGH_TEMPERATURE', 'Temperature exceeded threshold', 'HIGH'),
        (now(), 'DATA_QUALITY_TRUNCATED', 'Value truncated to 1000 chars', 'LOW'),
        (now(), 'AUDIT_CONFIG_CHANGE', 'User modified retention policy', 'INFO');
    
    RAISE NOTICE 'Valid event types: PASSED';
    
    -- Invalid event type (should fail)
    BEGIN
        INSERT INTO historian_raw.historian_events 
            (time, event_type, message, severity)
        VALUES 
            (now(), 'INVALID_PREFIX_TEST', 'This should fail', 'INFO');
        RAISE NOTICE 'Invalid event type: FAILED (constraint not working)';
    EXCEPTION WHEN check_violation THEN
        RAISE NOTICE 'Invalid event type: PASSED (rejected as expected)';
    END;
    
    -- Test suppression schedule
    RAISE NOTICE 'Alarm suppression schedule rows: %', 
        (SELECT COUNT(*) FROM historian_meta.alarm_suppression_schedule);
    
    -- Test views
    RAISE NOTICE 'Active alarms view rows: %', 
        (SELECT COUNT(*) FROM historian_raw.vw_active_alarms);
    RAISE NOTICE 'System events view rows: %', 
        (SELECT COUNT(*) FROM historian_raw.vw_system_events);
    RAISE NOTICE 'Data quality view rows: %', 
        (SELECT COUNT(*) FROM historian_raw.vw_data_quality);
    RAISE NOTICE 'Audit trail view rows: %', 
        (SELECT COUNT(*) FROM historian_raw.vw_audit_trail);
    RAISE NOTICE 'Events timeline view rows: %', 
        (SELECT COUNT(*) FROM historian_raw.vw_events_timeline);
    
    RAISE NOTICE '';
END $$;

-- Remove triggers
DROP TRIGGER IF EXISTS trg_validate_timeseries_sample ON historian_raw.historian_timeseries;
DROP FUNCTION IF EXISTS validate_timeseries_sample();

-- Remove constraint
ALTER TABLE historian_raw.historian_timeseries DROP CONSTRAINT IF EXISTS uq_timeseries_time_tag;

-- Remove alarm columns
ALTER TABLE historian_raw.historian_events 
    DROP COLUMN IF EXISTS alarm_state,
    DROP COLUMN IF EXISTS alarm_priority,
    DROP COLUMN IF EXISTS acknowledged_by,
    DROP COLUMN IF EXISTS acknowledged_at,
    DROP COLUMN IF EXISTS cleared_at,
    DROP COLUMN IF EXISTS alarm_setpoint,
    DROP COLUMN IF EXISTS alarm_actual_value,
    DROP COLUMN IF EXISTS parent_alarm_id;

-- Remove views and functions
DROP VIEW IF EXISTS historian_raw.vw_active_alarms;
DROP VIEW IF EXISTS historian_raw.vw_system_events;
DROP VIEW IF EXISTS historian_raw.vw_data_quality;
DROP VIEW IF EXISTS historian_raw.vw_audit_trail;
DROP VIEW IF EXISTS historian_raw.vw_events_timeline;
DROP FUNCTION IF EXISTS acknowledge_alarm(BIGINT, TEXT, TEXT);
DROP FUNCTION IF EXISTS check_retention_health();
DROP FUNCTION IF EXISTS cleanup_old_events();
DROP FUNCTION IF EXISTS validate_writer_mapping_version(TEXT, BIGINT);

-- Remove tables
DROP TABLE IF EXISTS historian_meta.alarm_suppression_schedule;
DROP TABLE IF EXISTS historian_meta.data_quality_limits;

-- Revert sample_source
ALTER TABLE historian_raw.historian_timeseries 
    ALTER COLUMN sample_source TYPE CHAR(3);

-- Mark migration as rolled back
UPDATE historian_meta.schema_migrations 
SET status = 'ROLLED_BACK' 
WHERE migration_id = 2;
*/

-- ================= END OF HARDENING SCRIPT =================
