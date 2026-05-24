-- =====================================================
-- Migration 006: Two-Person Rule for Critical Operations
-- Description: Implements approval workflow for safety-critical operations
-- Dependencies: 005_shift_based_access.sql
-- =====================================================

-- =====================================================
-- 1. CRITICAL OPERATIONS TABLE
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.critical_operations (
    id SERIAL PRIMARY KEY,
    
    -- Operation Identification
    operation_code VARCHAR(100) UNIQUE NOT NULL,
    operation_name VARCHAR(255) NOT NULL,
    operation_category VARCHAR(50) NOT NULL, -- 'emergency_stop', 'interlock_override', 'mode_change', 'setpoint_critical'
    
    -- Target
    equipment_type VARCHAR(100),
    tag_pattern VARCHAR(255), -- Regex pattern for matching tags
    
    -- Approval Requirements
    requires_approval BOOLEAN DEFAULT TRUE,
    approval_timeout_minutes INTEGER DEFAULT 5,
    required_approver_role_id INTEGER REFERENCES historian_meta.roles(id),
    approver_must_be_different_user BOOLEAN DEFAULT TRUE,
    
    -- Severity
    severity VARCHAR(20) DEFAULT 'high', -- 'medium', 'high', 'critical'
    
    -- Description
    description TEXT,
    safety_implications TEXT,
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX idx_critical_ops_code ON historian_meta.critical_operations(operation_code);
CREATE INDEX idx_critical_ops_category ON historian_meta.critical_operations(operation_category);
CREATE INDEX idx_critical_ops_severity ON historian_meta.critical_operations(severity);
CREATE INDEX idx_critical_ops_active ON historian_meta.critical_operations(is_active);

-- Insert standard critical operations
INSERT INTO historian_meta.critical_operations (
    operation_code, operation_name, operation_category, approval_timeout_minutes, severity, description
) VALUES
('EMERGENCY_STOP', 'Emergency Stop', 'emergency_stop', 3, 'critical', 'Immediate shutdown of equipment'),
('INTERLOCK_OVERRIDE', 'Safety Interlock Override', 'interlock_override', 5, 'critical', 'Override safety interlocks'),
('MODE_TO_MANUAL', 'Change Mode to Manual', 'mode_change', 5, 'high', 'Switch equipment from auto to manual control'),
('SETPOINT_MAJOR_CHANGE', 'Major Setpoint Change (>20%)', 'setpoint_critical', 5, 'high', 'Large setpoint adjustments'),
('BATCH_ABORT', 'Abort Batch Process', 'emergency_stop', 3, 'critical', 'Emergency batch abort'),
('BYPASS_ALARM', 'Bypass Critical Alarm', 'interlock_override', 5, 'high', 'Temporarily bypass alarm'),
('FORCE_START', 'Force Start with Warnings', 'mode_change', 5, 'high', 'Start equipment despite warnings'),
('SYSTEM_RESET', 'Full System Reset', 'emergency_stop', 5, 'critical', 'Reset all equipment to default state')
ON CONFLICT (operation_code) DO NOTHING;

-- =====================================================
-- 2. OPERATION APPROVALS TABLE
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.operation_approvals (
    id SERIAL PRIMARY KEY,
    
    -- Operation Reference
    operation_id VARCHAR(255) UNIQUE NOT NULL, -- UUID for this specific approval request
    critical_operation_id INTEGER REFERENCES historian_meta.critical_operations(id),
    operation_type VARCHAR(100) NOT NULL,
    
    -- Requester Information
    requested_by INTEGER NOT NULL REFERENCES historian_meta.users(id),
    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Approver Information
    approver_id INTEGER REFERENCES historian_meta.users(id),
    approved_at TIMESTAMP,
    denied_at TIMESTAMP,
    denial_reason TEXT,
    
    -- Target Information
    target_equipment VARCHAR(255),
    target_tag VARCHAR(255),
    target_value JSONB, -- The proposed change
    current_value JSONB, -- Current value for reference
    
    -- Status
    status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'approved', 'denied', 'expired', 'executed', 'cancelled'
    expires_at TIMESTAMP,
    
    -- Execution
    execution_completed_at TIMESTAMP,
    execution_result JSONB,
    execution_success BOOLEAN,
    
    -- Additional Context
    justification TEXT,
    notes TEXT,
    priority VARCHAR(20) DEFAULT 'normal', -- 'low', 'normal', 'high', 'urgent'
    
    -- Network Info
    requester_ip VARCHAR(50),
    requester_session_id VARCHAR(255),
    approver_ip VARCHAR(50),
    approver_session_id VARCHAR(255)
);

-- Create indexes
CREATE INDEX idx_op_approvals_operation_id ON historian_meta.operation_approvals(operation_id);
CREATE INDEX idx_op_approvals_requested_by ON historian_meta.operation_approvals(requested_by);
CREATE INDEX idx_op_approvals_approver ON historian_meta.operation_approvals(approver_id);
CREATE INDEX idx_op_approvals_status ON historian_meta.operation_approvals(status);
CREATE INDEX idx_op_approvals_requested_at ON historian_meta.operation_approvals(requested_at DESC);
CREATE INDEX idx_op_approvals_expires_at ON historian_meta.operation_approvals(expires_at);
CREATE INDEX idx_op_approvals_target ON historian_meta.operation_approvals(target_equipment, target_tag);

-- =====================================================
-- 3. APPROVAL NOTIFICATIONS TABLE
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.approval_notifications (
    id SERIAL PRIMARY KEY,
    
    -- Approval Reference
    approval_id INTEGER NOT NULL REFERENCES historian_meta.operation_approvals(id) ON DELETE CASCADE,
    
    -- Recipient
    notified_user_id INTEGER NOT NULL REFERENCES historian_meta.users(id),
    
    -- Notification
    notification_type VARCHAR(50) DEFAULT 'pending_approval', -- 'pending_approval', 'approved', 'denied', 'expired'
    notification_method VARCHAR(50), -- 'in_app', 'email', 'sms', 'push'
    
    -- Status
    is_read BOOLEAN DEFAULT FALSE,
    read_at TIMESTAMP,
    
    -- Metadata
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX idx_approval_notif_approval ON historian_meta.approval_notifications(approval_id);
CREATE INDEX idx_approval_notif_user ON historian_meta.approval_notifications(notified_user_id);
CREATE INDEX idx_approval_notif_read ON historian_meta.approval_notifications(is_read, notified_user_id);

-- =====================================================
-- 4. PENDING APPROVALS VIEW
-- =====================================================
CREATE OR REPLACE VIEW historian_meta.pending_approvals AS
SELECT 
    oa.id,
    oa.operation_id,
    co.operation_name,
    co.operation_category,
    co.severity,
    oa.requested_by,
    ru.username as requester_username,
    oa.requested_at,
    oa.target_equipment,
    oa.target_tag,
    oa.target_value,
    oa.current_value,
    oa.justification,
    oa.priority,
    oa.expires_at,
    EXTRACT(EPOCH FROM (oa.expires_at - CURRENT_TIMESTAMP))/60 as minutes_until_expiry,
    co.required_approver_role_id,
    r.name as required_approver_role_name
FROM historian_meta.operation_approvals oa
JOIN historian_meta.users ru ON oa.requested_by = ru.id
LEFT JOIN historian_meta.critical_operations co ON oa.critical_operation_id = co.id
LEFT JOIN historian_meta.roles r ON co.required_approver_role_id = r.id
WHERE oa.status = 'pending'
  AND oa.expires_at > CURRENT_TIMESTAMP
ORDER BY oa.priority DESC, oa.requested_at ASC;

-- =====================================================
-- 5. USER PENDING APPROVALS VIEW
-- =====================================================
CREATE OR REPLACE VIEW historian_meta.user_pending_approvals AS
SELECT 
    u.id as user_id,
    u.username,
    r.id as role_id,
    r.name as role_name,
    pa.*
FROM historian_meta.users u
JOIN historian_meta.roles r ON u.role_id = r.id
CROSS JOIN historian_meta.pending_approvals pa
WHERE (pa.required_approver_role_id IS NULL OR pa.required_approver_role_id = r.id)
  AND u.id != pa.requested_by -- Can't approve own requests
  AND u.status = 'approved';

-- =====================================================
-- 6. APPROVAL STATISTICS VIEW
-- =====================================================
CREATE OR REPLACE VIEW historian_meta.approval_statistics AS
SELECT 
    DATE(requested_at) as approval_date,
    operation_type,
    COUNT(*) as total_requests,
    COUNT(*) FILTER (WHERE status = 'approved') as approved_count,
    COUNT(*) FILTER (WHERE status = 'denied') as denied_count,
    COUNT(*) FILTER (WHERE status = 'expired') as expired_count,
    COUNT(*) FILTER (WHERE status = 'executed') as executed_count,
    AVG(EXTRACT(EPOCH FROM (approved_at - requested_at))) FILTER (WHERE approved_at IS NOT NULL) as avg_approval_time_seconds
FROM historian_meta.operation_approvals
WHERE requested_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY DATE(requested_at), operation_type
ORDER BY approval_date DESC, operation_type;

-- =====================================================
-- 7. FUNCTION: REQUEST CRITICAL OPERATION APPROVAL
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.request_critical_operation_approval(
    p_operation_code VARCHAR(100),
    p_requested_by INTEGER,
    p_target_equipment VARCHAR(255),
    p_target_tag VARCHAR(255),
    p_target_value JSONB,
    p_current_value JSONB,
    p_justification TEXT,
    p_priority VARCHAR(20) DEFAULT 'normal',
    p_requester_ip VARCHAR(50) DEFAULT NULL,
    p_requester_session_id VARCHAR(255) DEFAULT NULL
) RETURNS TABLE(
    approval_id INTEGER,
    operation_id VARCHAR(255),
    expires_at TIMESTAMP,
    required_approver_role_id INTEGER,
    timeout_minutes INTEGER
) AS $$
DECLARE
    v_operation_id VARCHAR(255);
    v_approval_id INTEGER;
    v_critical_op_id INTEGER;
    v_timeout_minutes INTEGER;
    v_required_role_id INTEGER;
    v_expires_at TIMESTAMP;
BEGIN
    -- Generate unique operation ID
    v_operation_id := 'OP-' || TO_CHAR(CURRENT_TIMESTAMP, 'YYYYMMDD-HH24MISS') || '-' || 
                      LPAD(p_requested_by::TEXT, 4, '0') || '-' || 
                      LPAD(FLOOR(RANDOM() * 10000)::TEXT, 4, '0');
    
    -- Get critical operation details
    SELECT id, approval_timeout_minutes, required_approver_role_id
    INTO v_critical_op_id, v_timeout_minutes, v_required_role_id
    FROM historian_meta.critical_operations
    WHERE operation_code = p_operation_code AND is_active = TRUE;
    
    IF v_critical_op_id IS NULL THEN
        RAISE EXCEPTION 'Critical operation % not found or inactive', p_operation_code;
    END IF;
    
    -- Calculate expiry time
    v_expires_at := CURRENT_TIMESTAMP + (v_timeout_minutes || ' minutes')::INTERVAL;
    
    -- Create approval request
    INSERT INTO historian_meta.operation_approvals (
        operation_id, critical_operation_id, operation_type,
        requested_by, target_equipment, target_tag,
        target_value, current_value, justification, priority,
        expires_at, requester_ip, requester_session_id
    ) VALUES (
        v_operation_id, v_critical_op_id, p_operation_code,
        p_requested_by, p_target_equipment, p_target_tag,
        p_target_value, p_current_value, p_justification, p_priority,
        v_expires_at, p_requester_ip, p_requester_session_id
    ) RETURNING id INTO v_approval_id;
    
    -- Create notifications for eligible approvers
    INSERT INTO historian_meta.approval_notifications (approval_id, notified_user_id, notification_type)
    SELECT v_approval_id, u.id, 'pending_approval'
    FROM historian_meta.users u
    WHERE u.status = 'approved'
      AND u.id != p_requested_by
      AND (v_required_role_id IS NULL OR u.role_id = v_required_role_id);
    
    -- Return approval details
    approval_id := v_approval_id;
    operation_id := v_operation_id;
    expires_at := v_expires_at;
    required_approver_role_id := v_required_role_id;
    timeout_minutes := v_timeout_minutes;
    
    RETURN NEXT;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 8. FUNCTION: APPROVE CRITICAL OPERATION
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.approve_critical_operation(
    p_operation_id VARCHAR(255),
    p_approver_id INTEGER,
    p_approver_ip VARCHAR(50) DEFAULT NULL,
    p_approver_session_id VARCHAR(255) DEFAULT NULL
) RETURNS TABLE(
    success BOOLEAN,
    message TEXT,
    approval_id INTEGER
) AS $$
DECLARE
    v_approval_id INTEGER;
    v_requested_by INTEGER;
    v_status VARCHAR(50);
    v_expires_at TIMESTAMP;
    v_approver_must_be_different BOOLEAN;
BEGIN
    -- Get approval details
    SELECT id, requested_by, status, expires_at, co.approver_must_be_different_user
    INTO v_approval_id, v_requested_by, v_status, v_expires_at, v_approver_must_be_different
    FROM historian_meta.operation_approvals oa
    LEFT JOIN historian_meta.critical_operations co ON oa.critical_operation_id = co.id
    WHERE oa.operation_id = p_operation_id;
    
    IF v_approval_id IS NULL THEN
        success := FALSE;
        message := 'Operation not found';
        RETURN NEXT;
        RETURN;
    END IF;
    
    -- Check if already processed
    IF v_status != 'pending' THEN
        success := FALSE;
        message := 'Operation already ' || v_status;
        approval_id := v_approval_id;
        RETURN NEXT;
        RETURN;
    END IF;
    
    -- Check if expired
    IF v_expires_at < CURRENT_TIMESTAMP THEN
        UPDATE historian_meta.operation_approvals
        SET status = 'expired'
        WHERE id = v_approval_id;
        
        success := FALSE;
        message := 'Operation request has expired';
        approval_id := v_approval_id;
        RETURN NEXT;
        RETURN;
    END IF;
    
    -- Check if approver is same as requester
    IF v_approver_must_be_different AND p_approver_id = v_requested_by THEN
        success := FALSE;
        message := 'Cannot approve your own request';
        approval_id := v_approval_id;
        RETURN NEXT;
        RETURN;
    END IF;
    
    -- Approve the operation
    UPDATE historian_meta.operation_approvals
    SET status = 'approved',
        approver_id = p_approver_id,
        approved_at = CURRENT_TIMESTAMP,
        approver_ip = p_approver_ip,
        approver_session_id = p_approver_session_id
    WHERE id = v_approval_id;
    
    -- Notify requester
    INSERT INTO historian_meta.approval_notifications (approval_id, notified_user_id, notification_type)
    VALUES (v_approval_id, v_requested_by, 'approved');
    
    success := TRUE;
    message := 'Operation approved successfully';
    approval_id := v_approval_id;
    
    RETURN NEXT;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 9. FUNCTION: DENY CRITICAL OPERATION
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.deny_critical_operation(
    p_operation_id VARCHAR(255),
    p_approver_id INTEGER,
    p_denial_reason TEXT
) RETURNS BOOLEAN AS $$
DECLARE
    v_approval_id INTEGER;
    v_requested_by INTEGER;
BEGIN
    UPDATE historian_meta.operation_approvals
    SET status = 'denied',
        approver_id = p_approver_id,
        denied_at = CURRENT_TIMESTAMP,
        denial_reason = p_denial_reason
    WHERE operation_id = p_operation_id
      AND status = 'pending'
    RETURNING id, requested_by INTO v_approval_id, v_requested_by;
    
    IF v_approval_id IS NULL THEN
        RETURN FALSE;
    END IF;
    
    -- Notify requester
    INSERT INTO historian_meta.approval_notifications (approval_id, notified_user_id, notification_type)
    VALUES (v_approval_id, v_requested_by, 'denied');
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 10. FUNCTION: MARK OPERATION EXECUTED
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.mark_operation_executed(
    p_operation_id VARCHAR(255),
    p_execution_result JSONB,
    p_execution_success BOOLEAN DEFAULT TRUE
) RETURNS BOOLEAN AS $$
BEGIN
    UPDATE historian_meta.operation_approvals
    SET status = 'executed',
        execution_completed_at = CURRENT_TIMESTAMP,
        execution_result = p_execution_result,
        execution_success = p_execution_success
    WHERE operation_id = p_operation_id
      AND status = 'approved';
    
    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 11. FUNCTION: EXPIRE OLD APPROVALS
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.expire_old_approvals()
RETURNS INTEGER AS $$
DECLARE
    v_expired_count INTEGER;
BEGIN
    UPDATE historian_meta.operation_approvals
    SET status = 'expired'
    WHERE status = 'pending'
      AND expires_at < CURRENT_TIMESTAMP;
    
    GET DIAGNOSTICS v_expired_count = ROW_COUNT;
    
    RETURN v_expired_count;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 12. GRANTS
-- =====================================================
GRANT SELECT ON historian_meta.critical_operations TO opc_app_user;
GRANT SELECT, INSERT, UPDATE ON historian_meta.operation_approvals TO opc_app_user;
GRANT SELECT, INSERT, UPDATE ON historian_meta.approval_notifications TO opc_app_user;
GRANT SELECT ON historian_meta.pending_approvals TO opc_app_user;
GRANT SELECT ON historian_meta.user_pending_approvals TO opc_app_user;
GRANT SELECT ON historian_meta.approval_statistics TO opc_app_user;
GRANT USAGE ON SEQUENCE historian_meta.critical_operations_id_seq TO opc_app_user;
GRANT USAGE ON SEQUENCE historian_meta.operation_approvals_id_seq TO opc_app_user;
GRANT USAGE ON SEQUENCE historian_meta.approval_notifications_id_seq TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.request_critical_operation_approval TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.approve_critical_operation TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.deny_critical_operation TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.mark_operation_executed TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.expire_old_approvals TO opc_app_user;

-- =====================================================
-- MIGRATION COMPLETE
-- =====================================================
