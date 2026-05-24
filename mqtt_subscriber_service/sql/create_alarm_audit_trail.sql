-- ============================================================================
-- Alarm Audit Trail Table
-- Purpose: Track complete history of all alarm state changes for compliance
-- Standard: ISA-18.2 Alarm Management
-- ============================================================================

-- Drop table if exists (for fresh deployment)
-- DROP TABLE IF EXISTS historian_raw.alarm_audit_trail CASCADE;

-- Create alarm audit trail table
CREATE TABLE IF NOT EXISTS historian_raw.alarm_audit_trail (
    audit_id BIGSERIAL PRIMARY KEY,
    event_id BIGINT NOT NULL,  -- Reference to historian_events.event_id
    tag_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    action_type TEXT NOT NULL CHECK (action_type IN ('RAISED', 'ACKNOWLEDGED', 'CLEARED', 'SUPPRESSED', 'UNSUPPRESSED', 'SHELVED', 'UNSHELVED')),
    action_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    performed_by TEXT NOT NULL,  -- Username/operator who performed the action
    previous_state TEXT,  -- Previous alarm_state (ACTIVE, ACKNOWLEDGED, CLEARED, SUPPRESSED)
    new_state TEXT NOT NULL,  -- New alarm_state after action
    alarm_priority INTEGER,  -- Priority at time of action (1-5)
    alarm_actual_value DOUBLE PRECISION,  -- Value at time of action
    alarm_setpoint DOUBLE PRECISION,  -- Setpoint/threshold
    action_reason TEXT,  -- Reason for action (e.g., clear_reason)
    action_notes TEXT,  -- Additional notes from operator
    session_id TEXT,  -- User session ID for tracking
    client_ip TEXT,  -- IP address of client who made the change
    metadata JSONB,  -- Additional context (location, shift, etc.)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_alarm_audit_event_id ON historian_raw.alarm_audit_trail(event_id);
CREATE INDEX IF NOT EXISTS idx_alarm_audit_tag_id ON historian_raw.alarm_audit_trail(tag_id);
CREATE INDEX IF NOT EXISTS idx_alarm_audit_timestamp ON historian_raw.alarm_audit_trail(action_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_alarm_audit_action_type ON historian_raw.alarm_audit_trail(action_type);
CREATE INDEX IF NOT EXISTS idx_alarm_audit_performed_by ON historian_raw.alarm_audit_trail(performed_by);
CREATE INDEX IF NOT EXISTS idx_alarm_audit_tag_time ON historian_raw.alarm_audit_trail(tag_id, action_timestamp DESC);

-- Foreign key constraint (optional - may fail if event is deleted)
-- ALTER TABLE historian_raw.alarm_audit_trail 
-- ADD CONSTRAINT fk_alarm_audit_event 
-- FOREIGN KEY (event_id) REFERENCES historian_raw.historian_events(event_id) 
-- ON DELETE CASCADE;

-- Comments for documentation
COMMENT ON TABLE historian_raw.alarm_audit_trail IS 
'Complete audit trail of all alarm state changes for ISA-18.2 compliance. 
Tracks who did what, when, and why for every alarm action.';

COMMENT ON COLUMN historian_raw.alarm_audit_trail.action_type IS 
'Type of action: RAISED (new alarm), ACKNOWLEDGED (operator ack), CLEARED (resolved), 
SUPPRESSED (temporarily hidden), UNSUPPRESSED (restored), SHELVED (long-term defer), UNSHELVED (restored)';

COMMENT ON COLUMN historian_raw.alarm_audit_trail.performed_by IS 
'Username or operator ID who performed the action. For RAISED actions, this is typically "SYSTEM"';

COMMENT ON COLUMN historian_raw.alarm_audit_trail.metadata IS 
'Additional context in JSON format: {shift: "A", location: "Control Room 1", workstation: "HMI-01", etc.}';

-- Grant permissions (opc_app_user role does not exist in this DB — skipped)
-- GRANT INSERT, SELECT ON historian_raw.alarm_audit_trail TO opc_app_user;
-- GRANT USAGE, SELECT ON SEQUENCE historian_raw.alarm_audit_trail_audit_id_seq TO opc_app_user;

-- ============================================================================
-- Create View for Easy Audit Trail Queries
-- ============================================================================

CREATE OR REPLACE VIEW historian_raw.v_alarm_audit_trail AS
SELECT 
    aat.audit_id,
    aat.event_id,
    aat.tag_id,
    COALESCE(tm.tag_name, aat.tag_id) as tag_name,
    tm.description as tag_description,
    tm.plant,
    tm.area,
    tm.equipment,
    aat.event_type,
    aat.action_type,
    aat.action_timestamp,
    aat.performed_by,
    aat.previous_state,
    aat.new_state,
    aat.alarm_priority,
    CASE 
        WHEN aat.alarm_priority = 5 THEN 'CRITICAL'
        WHEN aat.alarm_priority = 4 THEN 'HIGH'
        WHEN aat.alarm_priority = 3 THEN 'MEDIUM'
        WHEN aat.alarm_priority = 2 THEN 'LOW'
        WHEN aat.alarm_priority = 1 THEN 'INFO'
        ELSE 'UNKNOWN'
    END as priority_label,
    aat.alarm_actual_value,
    aat.alarm_setpoint,
    aat.action_reason,
    aat.action_notes,
    aat.session_id,
    aat.client_ip,
    aat.metadata,
    aat.created_at,
    -- Time between this action and previous action on same alarm
    LAG(aat.action_timestamp) OVER (PARTITION BY aat.event_id ORDER BY aat.action_timestamp) as previous_action_time,
    EXTRACT(EPOCH FROM (
        aat.action_timestamp - 
        LAG(aat.action_timestamp) OVER (PARTITION BY aat.event_id ORDER BY aat.action_timestamp)
    ))/60 as minutes_since_previous_action,
    -- Time since RAISED (first action) for this alarm event — gives ACK response time
    EXTRACT(EPOCH FROM (
        aat.action_timestamp -
        FIRST_VALUE(aat.action_timestamp) OVER (PARTITION BY aat.event_id ORDER BY aat.action_timestamp)
    ))/60 as minutes_since_raised,
    EXTRACT(EPOCH FROM (
        aat.action_timestamp -
        FIRST_VALUE(aat.action_timestamp) OVER (PARTITION BY aat.event_id ORDER BY aat.action_timestamp)
    )) as response_time_seconds
FROM historian_raw.alarm_audit_trail aat
LEFT JOIN historian_meta.tag_master tm ON aat.tag_id = tm.tag_id
ORDER BY aat.action_timestamp DESC;

COMMENT ON VIEW historian_raw.v_alarm_audit_trail IS 
'Enhanced view of alarm audit trail with tag names, priority labels, and timing calculations';

-- Grant view access (opc_app_user role does not exist in this DB — skipped)
-- GRANT SELECT ON historian_raw.v_alarm_audit_trail TO opc_app_user;

-- ============================================================================
-- Example Queries for Audit Trail Analysis
-- ============================================================================

-- 1. Get complete audit trail for a specific alarm
/*
SELECT 
    action_timestamp,
    action_type,
    performed_by,
    previous_state,
    new_state,
    action_reason,
    action_notes
FROM historian_raw.v_alarm_audit_trail
WHERE event_id = <alarm_event_id>
ORDER BY action_timestamp ASC;
*/

-- 2. Get all actions by a specific operator
/*
SELECT 
    tag_name,
    event_type,
    action_type,
    action_timestamp,
    action_reason
FROM historian_raw.v_alarm_audit_trail
WHERE performed_by = 'operator_username'
ORDER BY action_timestamp DESC
LIMIT 50;
*/

-- 3. Get alarms acknowledged within specific time range
/*
SELECT 
    tag_name,
    event_type,
    action_timestamp,
    performed_by,
    minutes_since_previous_action as response_time_minutes
FROM historian_raw.v_alarm_audit_trail
WHERE action_type = 'ACKNOWLEDGED'
  AND action_timestamp >= NOW() - INTERVAL '24 hours'
ORDER BY action_timestamp DESC;
*/

-- 4. Calculate average acknowledgment response times
/*
SELECT 
    performed_by,
    COUNT(*) as acks_count,
    AVG(minutes_since_previous_action) as avg_response_minutes,
    MIN(minutes_since_previous_action) as fastest_response_minutes,
    MAX(minutes_since_previous_action) as slowest_response_minutes
FROM historian_raw.v_alarm_audit_trail
WHERE action_type = 'ACKNOWLEDGED'
  AND action_timestamp >= NOW() - INTERVAL '7 days'
  AND minutes_since_previous_action IS NOT NULL
GROUP BY performed_by
ORDER BY avg_response_minutes ASC;
*/

-- 5. Get alarms that were never acknowledged (raised but not acked)
/*
SELECT 
    event_id,
    tag_name,
    event_type,
    action_timestamp as raised_at,
    alarm_priority
FROM historian_raw.v_alarm_audit_trail
WHERE action_type = 'RAISED'
  AND event_id NOT IN (
      SELECT DISTINCT event_id 
      FROM historian_raw.alarm_audit_trail 
      WHERE action_type = 'ACKNOWLEDGED'
  )
  AND action_timestamp >= NOW() - INTERVAL '24 hours'
ORDER BY alarm_priority DESC, action_timestamp DESC;
*/

-- ============================================================================
-- Verification Query
-- ============================================================================
SELECT 
    table_name,
    (SELECT COUNT(*) FROM information_schema.columns 
     WHERE table_schema='historian_raw' AND table_name='alarm_audit_trail') as column_count
FROM information_schema.tables
WHERE table_schema = 'historian_raw' 
  AND table_name = 'alarm_audit_trail';

-- Table created successfully. Use: SELECT * FROM historian_raw.v_alarm_audit_trail LIMIT 10;

-- ============================================================================
-- END OF SCRIPT
-- ============================================================================
