-- =====================================================
-- Migration 002: Comprehensive Audit Logging System
-- Description: Creates audit trail tables for tracking all user actions
-- Dependencies: 001_init_auth_rbac.sql
-- =====================================================

-- =====================================================
-- 1. USER ACTIONS AUDIT TABLE
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.user_actions_audit (
    id SERIAL PRIMARY KEY,
    
    -- User Information
    user_id INTEGER NOT NULL REFERENCES historian_meta.users(id) ON DELETE SET NULL,
    username VARCHAR(255) NOT NULL, -- Denormalized for immutability
    
    -- Action Details
    action_type VARCHAR(100) NOT NULL,
    action_category VARCHAR(50) NOT NULL, -- 'authentication', 'control', 'alarm', 'admin', 'data'
    
    -- Target Information
    target_entity VARCHAR(255), -- 'tag', 'equipment', 'user', 'role', 'alarm'
    target_id VARCHAR(255),
    target_name VARCHAR(255),
    
    -- Change Tracking
    old_value TEXT,
    new_value TEXT,
    
    -- Result
    success BOOLEAN DEFAULT TRUE,
    failure_reason TEXT,
    
    -- Session & Network
    ip_address VARCHAR(50),
    session_id VARCHAR(255),
    user_agent TEXT,
    
    -- Timestamp
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Additional Context
    additional_data JSONB
);

-- Create indexes for performance
CREATE INDEX idx_audit_user_id ON historian_meta.user_actions_audit(user_id);
CREATE INDEX idx_audit_username ON historian_meta.user_actions_audit(username);
CREATE INDEX idx_audit_timestamp ON historian_meta.user_actions_audit(timestamp DESC);
CREATE INDEX idx_audit_action_type ON historian_meta.user_actions_audit(action_type);
CREATE INDEX idx_audit_action_category ON historian_meta.user_actions_audit(action_category);
CREATE INDEX idx_audit_target ON historian_meta.user_actions_audit(target_entity, target_id);
CREATE INDEX idx_audit_session ON historian_meta.user_actions_audit(session_id);
CREATE INDEX idx_audit_success ON historian_meta.user_actions_audit(success, timestamp DESC);

-- Composite indexes for common queries
CREATE INDEX idx_audit_user_time ON historian_meta.user_actions_audit(user_id, timestamp DESC);
CREATE INDEX idx_audit_type_time ON historian_meta.user_actions_audit(action_type, timestamp DESC);

-- =====================================================
-- 2. AUDIT ACTION TYPES REFERENCE
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.audit_action_types (
    id SERIAL PRIMARY KEY,
    action_type VARCHAR(100) UNIQUE NOT NULL,
    action_category VARCHAR(50) NOT NULL,
    description TEXT,
    severity VARCHAR(20) DEFAULT 'info', -- 'info', 'warning', 'critical'
    requires_notification BOOLEAN DEFAULT FALSE,
    retention_days INTEGER DEFAULT 2555, -- 7 years default
    is_active BOOLEAN DEFAULT TRUE
);

-- Insert standard action types
INSERT INTO historian_meta.audit_action_types (action_type, action_category, description, severity, requires_notification) VALUES
-- Authentication
('LOGIN', 'authentication', 'User logged in successfully', 'info', FALSE),
('LOGIN_FAILED', 'authentication', 'Failed login attempt', 'warning', TRUE),
('LOGOUT', 'authentication', 'User logged out', 'info', FALSE),
('LOGOUT_FORCED', 'authentication', 'User forcefully logged out by admin', 'warning', TRUE),
('LOGOUT_TIMEOUT', 'authentication', 'User logged out due to inactivity', 'info', FALSE),
('MFA_ENABLED', 'authentication', 'MFA enabled for user', 'info', FALSE),
('MFA_DISABLED', 'authentication', 'MFA disabled for user', 'warning', TRUE),
('PASSWORD_CHANGED', 'authentication', 'Password changed', 'info', FALSE),
('PASSWORD_RESET', 'authentication', 'Password reset using backup key', 'warning', TRUE),

-- Control Operations
('SETPOINT_CHANGE', 'control', 'Setpoint value changed', 'warning', TRUE),
('MODE_CHANGE', 'control', 'Equipment mode changed', 'warning', TRUE),
('COMMAND_EXECUTE', 'control', 'Control command executed', 'warning', TRUE),
('EQUIPMENT_START', 'control', 'Equipment started', 'warning', TRUE),
('EQUIPMENT_STOP', 'control', 'Equipment stopped', 'warning', TRUE),
('EMERGENCY_STOP', 'control', 'Emergency stop triggered', 'critical', TRUE),
('INTERLOCK_OVERRIDE', 'control', 'Safety interlock overridden', 'critical', TRUE),

-- Alarm Operations
('ALARM_ACKNOWLEDGE', 'alarm', 'Alarm acknowledged', 'info', FALSE),
('ALARM_CLEARED', 'alarm', 'Alarm cleared', 'info', FALSE),
('ALARM_SILENCE', 'alarm', 'Alarm silenced', 'warning', TRUE),
('ALARM_SHELVE', 'alarm', 'Alarm shelved', 'warning', TRUE),
('ALARM_UNSHELVE', 'alarm', 'Alarm unshelved', 'info', FALSE),

-- Administrative
('USER_CREATED', 'admin', 'New user created', 'info', FALSE),
('USER_APPROVED', 'admin', 'User approved', 'info', FALSE),
('USER_REVOKED', 'admin', 'User access revoked', 'warning', TRUE),
('ROLE_ASSIGNED', 'admin', 'Role assigned to user', 'warning', TRUE),
('ROLE_CREATED', 'admin', 'New role created', 'info', FALSE),
('ROLE_DELETED', 'admin', 'Role deleted', 'warning', TRUE),
('PERMISSION_GRANTED', 'admin', 'Permission granted', 'warning', TRUE),
('PERMISSION_REVOKED', 'admin', 'Permission revoked', 'warning', TRUE),
('SESSION_TERMINATED', 'admin', 'User session terminated by admin', 'warning', TRUE),

-- Data Operations
('DATA_EXPORT', 'data', 'Data exported', 'info', FALSE),
('REPORT_GENERATED', 'data', 'Report generated', 'info', FALSE),
('CONFIG_CHANGED', 'data', 'Configuration changed', 'warning', TRUE),
('BACKUP_CREATED', 'data', 'System backup created', 'info', FALSE)
ON CONFLICT (action_type) DO NOTHING;

-- =====================================================
-- 3. AUDIT STATISTICS VIEW
-- =====================================================
CREATE OR REPLACE VIEW historian_meta.audit_statistics AS
SELECT 
    DATE(timestamp) as audit_date,
    action_category,
    COUNT(*) as total_actions,
    COUNT(*) FILTER (WHERE success = TRUE) as successful_actions,
    COUNT(*) FILTER (WHERE success = FALSE) as failed_actions,
    COUNT(DISTINCT user_id) as unique_users,
    COUNT(DISTINCT ip_address) as unique_ips
FROM historian_meta.user_actions_audit
WHERE timestamp >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY DATE(timestamp), action_category
ORDER BY audit_date DESC, action_category;

-- =====================================================
-- 4. CRITICAL ACTIONS VIEW (Last 24 hours)
-- =====================================================
CREATE OR REPLACE VIEW historian_meta.recent_critical_actions AS
SELECT 
    a.id,
    a.timestamp,
    a.username,
    a.action_type,
    a.target_entity,
    a.target_name,
    a.old_value,
    a.new_value,
    a.ip_address,
    aat.severity
FROM historian_meta.user_actions_audit a
JOIN historian_meta.audit_action_types aat ON a.action_type = aat.action_type
WHERE a.timestamp >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
  AND aat.severity IN ('warning', 'critical')
ORDER BY a.timestamp DESC;

-- =====================================================
-- 5. USER ACTIVITY SUMMARY VIEW
-- =====================================================
CREATE OR REPLACE VIEW historian_meta.user_activity_summary AS
SELECT 
    u.id as user_id,
    u.username,
    r.name as role_name,
    COUNT(a.id) as total_actions,
    MAX(a.timestamp) as last_action,
    COUNT(a.id) FILTER (WHERE a.action_category = 'control') as control_actions,
    COUNT(a.id) FILTER (WHERE a.action_category = 'alarm') as alarm_actions,
    COUNT(a.id) FILTER (WHERE a.success = FALSE) as failed_actions
FROM historian_meta.users u
LEFT JOIN historian_meta.roles r ON u.role_id = r.id
LEFT JOIN historian_meta.user_actions_audit a ON u.id = a.user_id 
    AND a.timestamp >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY u.id, u.username, r.name
ORDER BY total_actions DESC;

-- =====================================================
-- 6. PARTITIONING SETUP (For large-scale deployments)
-- =====================================================
-- Note: For systems expecting >10M audit records, consider table partitioning by month
-- This is commented out by default, enable if needed

/*
-- Convert to partitioned table
CREATE TABLE historian_meta.user_actions_audit_new (
    LIKE historian_meta.user_actions_audit INCLUDING ALL
) PARTITION BY RANGE (timestamp);

-- Create partitions for current and next 12 months
CREATE TABLE historian_meta.audit_2026_02 PARTITION OF historian_meta.user_actions_audit_new
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

-- Add more partitions as needed
-- Then migrate data and rename table
*/

-- =====================================================
-- 7. AUDIT LOG RETENTION POLICY
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.audit_retention_config (
    id SERIAL PRIMARY KEY,
    action_category VARCHAR(50) UNIQUE NOT NULL,
    retention_days INTEGER NOT NULL DEFAULT 2555, -- 7 years
    archive_after_days INTEGER DEFAULT 90,
    archive_location VARCHAR(255),
    last_purge_date DATE,
    is_active BOOLEAN DEFAULT TRUE
);

-- Insert default retention policies
INSERT INTO historian_meta.audit_retention_config (action_category, retention_days, archive_after_days) VALUES
('authentication', 2555, 90), -- 7 years, archive after 90 days
('control', 2555, 90),        -- 7 years for compliance
('alarm', 1825, 90),          -- 5 years
('admin', 2555, 90),          -- 7 years
('data', 365, 90)             -- 1 year
ON CONFLICT (action_category) DO NOTHING;

-- =====================================================
-- 8. FUNCTION: LOG USER ACTION
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.log_user_action(
    p_user_id INTEGER,
    p_username VARCHAR(255),
    p_action_type VARCHAR(100),
    p_action_category VARCHAR(50),
    p_target_entity VARCHAR(255) DEFAULT NULL,
    p_target_id VARCHAR(255) DEFAULT NULL,
    p_target_name VARCHAR(255) DEFAULT NULL,
    p_old_value TEXT DEFAULT NULL,
    p_new_value TEXT DEFAULT NULL,
    p_success BOOLEAN DEFAULT TRUE,
    p_failure_reason TEXT DEFAULT NULL,
    p_ip_address VARCHAR(50) DEFAULT NULL,
    p_session_id VARCHAR(255) DEFAULT NULL,
    p_user_agent TEXT DEFAULT NULL,
    p_additional_data JSONB DEFAULT NULL
) RETURNS INTEGER AS $$
DECLARE
    v_audit_id INTEGER;
BEGIN
    INSERT INTO historian_meta.user_actions_audit (
        user_id, username, action_type, action_category,
        target_entity, target_id, target_name,
        old_value, new_value, success, failure_reason,
        ip_address, session_id, user_agent, additional_data
    ) VALUES (
        p_user_id, p_username, p_action_type, p_action_category,
        p_target_entity, p_target_id, p_target_name,
        p_old_value, p_new_value, p_success, p_failure_reason,
        p_ip_address, p_session_id, p_user_agent, p_additional_data
    ) RETURNING id INTO v_audit_id;
    
    RETURN v_audit_id;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 9. FUNCTION: ARCHIVE OLD AUDIT LOGS
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.archive_old_audit_logs()
RETURNS TABLE(action_category VARCHAR(50), archived_count BIGINT) AS $$
DECLARE
    v_category RECORD;
    v_count BIGINT;
BEGIN
    FOR v_category IN 
        SELECT action_category, archive_after_days 
        FROM historian_meta.audit_retention_config 
        WHERE is_active = TRUE AND archive_after_days IS NOT NULL
    LOOP
        -- In production, this would move to archive storage
        -- For now, we just mark them as archived in a separate table
        
        SELECT COUNT(*) INTO v_count
        FROM historian_meta.user_actions_audit
        WHERE action_category = v_category.action_category
          AND timestamp < CURRENT_DATE - v_category.archive_after_days * INTERVAL '1 day';
        
        action_category := v_category.action_category;
        archived_count := v_count;
        
        RETURN NEXT;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 10. GRANTS
-- =====================================================
-- Grant appropriate permissions
GRANT SELECT ON historian_meta.user_actions_audit TO opc_app_user;
GRANT INSERT ON historian_meta.user_actions_audit TO opc_app_user;
GRANT SELECT ON historian_meta.audit_action_types TO opc_app_user;
GRANT SELECT ON historian_meta.audit_statistics TO opc_app_user;
GRANT SELECT ON historian_meta.recent_critical_actions TO opc_app_user;
GRANT SELECT ON historian_meta.user_activity_summary TO opc_app_user;
GRANT USAGE ON SEQUENCE historian_meta.user_actions_audit_id_seq TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.log_user_action TO opc_app_user;

-- =====================================================
-- MIGRATION COMPLETE
-- =====================================================
