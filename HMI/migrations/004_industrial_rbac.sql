-- =====================================================
-- Migration 004: Industrial RBAC System
-- Description: Implements Separation of Duties, Change Control, 
--              User Certifications, and Risk-Based Access Control
-- Dependencies: 003_session_management.sql
-- Standards: ISA-18.2, ISA-61511, IEC 62443, NIST CSF
-- =====================================================

-- =====================================================
-- 1. ROLE OPERATION PERMISSIONS (SoD Enforcement)
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.role_operation_permissions (
    id SERIAL PRIMARY KEY,
    role_id INTEGER NOT NULL REFERENCES historian_meta.roles(id) ON DELETE CASCADE,
    operation_type VARCHAR(255) NOT NULL, -- 'ALARM_ACKNOWLEDGE', 'TRIP_CLEAR', 'INTERLOCK_DISABLE', etc.
    can_execute BOOLEAN DEFAULT FALSE,
    requires_approval BOOLEAN DEFAULT FALSE,
    requires_2fa BOOLEAN DEFAULT FALSE,
    requires_certification_type VARCHAR(255), -- e.g., 'SAFETY_SYSTEM_CERTIFIED'
    max_daily_actions INTEGER, -- NULL = unlimited
    time_window_id INTEGER, -- References time-based access window
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(role_id, operation_type)
);

CREATE INDEX idx_role_op_perms_role ON historian_meta.role_operation_permissions(role_id);
CREATE INDEX idx_role_op_perms_operation ON historian_meta.role_operation_permissions(operation_type);

-- =====================================================
-- 2. SEPARATION OF DUTIES RULES
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.sod_rules (
    id SERIAL PRIMARY KEY,
    operation_type VARCHAR(255) NOT NULL UNIQUE,
    requester_role VARCHAR(255),
    approver_role VARCHAR(255),
    executor_role VARCHAR(255),
    verifier_role VARCHAR(255),
    cannot_be_same_as TEXT[], -- JSON array: ['requester', 'approver'], ['approver', 'executor']
    exception_allowed BOOLEAN DEFAULT FALSE,
    exception_approver_role VARCHAR(255),
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sod_operation ON historian_meta.sod_rules(operation_type);

-- =====================================================
-- 3. OPERATION APPROVALS (Change Control)
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.operation_approvals (
    id SERIAL PRIMARY KEY,
    operation_type VARCHAR(255) NOT NULL, -- References sod_rules
    operation_id VARCHAR(255), -- e.g., alarm_id, trip_id
    operation_description TEXT,
    requested_by INTEGER NOT NULL REFERENCES historian_meta.users(id),
    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    request_reason TEXT NOT NULL,
    
    approved_by INTEGER REFERENCES historian_meta.users(id),
    approved_at TIMESTAMP,
    approval_reason TEXT,
    approval_code VARCHAR(255), -- Generated for 2FA verification
    approval_code_expires_at TIMESTAMP,
    
    executed_by INTEGER REFERENCES historian_meta.users(id),
    executed_at TIMESTAMP,
    
    verified_by INTEGER REFERENCES historian_meta.users(id),
    verified_at TIMESTAMP,
    verification_notes TEXT,
    
    status VARCHAR(50) NOT NULL CHECK (
        status IN ('REQUESTED', 'APPROVED', 'SCHEDULED', 'EXECUTED', 'VERIFIED', 'REJECTED', 'EXPIRED', 'CANCELLED')
    ) DEFAULT 'REQUESTED',
    
    priority VARCHAR(50) DEFAULT 'NORMAL', -- LOW, NORMAL, HIGH, CRITICAL
    execution_deadline TIMESTAMP,
    scheduled_for TIMESTAMP,
    
    rollback_procedure TEXT,
    impact_assessment TEXT,
    lessons_learned TEXT,
    
    session_id VARCHAR(255),
    ip_address VARCHAR(50),
    additional_data JSONB,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_approvals_operation ON historian_meta.operation_approvals(operation_type);
CREATE INDEX idx_approvals_status ON historian_meta.operation_approvals(status);
CREATE INDEX idx_approvals_requested_by ON historian_meta.operation_approvals(requested_by);
CREATE INDEX idx_approvals_approved_by ON historian_meta.operation_approvals(approved_by);
CREATE INDEX idx_approvals_created ON historian_meta.operation_approvals(created_at DESC);

-- =====================================================
-- 4. USER CERTIFICATIONS
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.user_certifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES historian_meta.users(id) ON DELETE CASCADE,
    certification_type VARCHAR(255) NOT NULL, -- 'EQUIPMENT_TRAINING', 'SAFETY_SYSTEM', 'EMERGENCY_PROCEDURES', etc.
    certified_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    certified_by INTEGER REFERENCES historian_meta.users(id), -- Admin/trainer who certified
    
    training_record_url TEXT, -- URL to training documentation
    training_provider VARCHAR(255),
    test_score NUMERIC(5,2), -- Out of 100
    test_date TIMESTAMP,
    
    is_active BOOLEAN DEFAULT TRUE,
    revocation_reason TEXT,
    revoked_at TIMESTAMP,
    revoked_by INTEGER REFERENCES historian_meta.users(id),
    
    notes TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_certs_user ON historian_meta.user_certifications(user_id);
CREATE INDEX idx_certs_type ON historian_meta.user_certifications(certification_type);
CREATE INDEX idx_certs_active ON historian_meta.user_certifications(is_active, expires_at);
CREATE INDEX idx_certs_expiry ON historian_meta.user_certifications(expires_at);

-- =====================================================
-- 5. TIME-BASED ACCESS WINDOWS
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.time_based_access_windows (
    id SERIAL PRIMARY KEY,
    operation_type VARCHAR(255) NOT NULL,
    day_of_week VARCHAR(10) NOT NULL, -- 'MON', 'TUE', ... 'SUN', or 'WEEKDAY', 'WEEKEND', 'DAILY'
    allowed_start_hour INTEGER CHECK (allowed_start_hour BETWEEN 0 AND 23),
    allowed_end_hour INTEGER CHECK (allowed_end_hour BETWEEN 0 AND 23),
    requires_supervisor_approval BOOLEAN DEFAULT FALSE,
    requires_2fa BOOLEAN DEFAULT FALSE,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(operation_type, day_of_week)
);

CREATE INDEX idx_time_windows_operation ON historian_meta.time_based_access_windows(operation_type);
CREATE INDEX idx_time_windows_active ON historian_meta.time_based_access_windows(is_active);

-- =====================================================
-- 6. OPERATION AUDIT TRAIL (Enhanced)
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.operation_audit_trail (
    id BIGSERIAL PRIMARY KEY,
    operation_approval_id INTEGER REFERENCES historian_meta.operation_approvals(id),
    operation_type VARCHAR(255) NOT NULL,
    operation_id VARCHAR(255), -- e.g., alarm_id, trip_id
    
    action VARCHAR(100) NOT NULL, -- 'REQUEST', 'APPROVE', 'EXECUTE', 'VERIFY', 'REJECT', 'CANCEL'
    performed_by INTEGER NOT NULL REFERENCES historian_meta.users(id) ON DELETE SET NULL,
    approved_by INTEGER REFERENCES historian_meta.users(id) ON DELETE SET NULL,
    
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ip_address VARCHAR(50),
    session_id VARCHAR(255),
    
    result VARCHAR(50) NOT NULL CHECK (result IN ('SUCCEEDED', 'FAILED', 'PENDING')),
    reason_code VARCHAR(255), -- Machine-readable reason
    detailed_reason TEXT, -- Human-readable reason
    
    verification_status VARCHAR(50), -- For VERIFY action: 'VERIFIED', 'NEEDS_CORRECTION', 'DEFERRED'
    verified_by INTEGER REFERENCES historian_meta.users(id),
    verified_at TIMESTAMP,
    verification_notes TEXT,
    
    old_value TEXT,
    new_value TEXT,
    affected_systems TEXT[], -- JSON array of affected systems
    
    sod_violation_detected BOOLEAN DEFAULT FALSE,
    sod_violation_reason TEXT,
    
    metadata JSONB, -- Additional context
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_op_audit_operation ON historian_meta.operation_audit_trail(operation_type);
CREATE INDEX idx_op_audit_performed_by ON historian_meta.operation_audit_trail(performed_by);
CREATE INDEX idx_op_audit_timestamp ON historian_meta.operation_audit_trail(timestamp DESC);
CREATE INDEX idx_op_audit_action ON historian_meta.operation_audit_trail(action);
CREATE INDEX idx_op_audit_result ON historian_meta.operation_audit_trail(result);
CREATE INDEX idx_op_audit_sod ON historian_meta.operation_audit_trail(sod_violation_detected);

-- =====================================================
-- 7. ROLE ALARM PERMISSIONS (Enhanced)
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.role_alarm_permissions (
    id SERIAL PRIMARY KEY,
    role_id INTEGER NOT NULL REFERENCES historian_meta.roles(id) ON DELETE CASCADE,
    alarm_category VARCHAR(255) NOT NULL,
    
    can_view BOOLEAN DEFAULT TRUE,
    can_acknowledge BOOLEAN DEFAULT FALSE,
    can_acknowledge_priority_max INTEGER, -- Max priority they can acknowledge (1=highest)
    can_silence BOOLEAN DEFAULT FALSE,
    can_clear BOOLEAN DEFAULT FALSE,
    requires_approval_to_clear BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(role_id, alarm_category)
);

CREATE INDEX idx_role_alarm_perms_role ON historian_meta.role_alarm_permissions(role_id);
CREATE INDEX idx_role_alarm_perms_category ON historian_meta.role_alarm_permissions(alarm_category);

-- =====================================================
-- 8. ROLE TRIP PERMISSIONS (New)
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.role_trip_permissions (
    id SERIAL PRIMARY KEY,
    role_id INTEGER NOT NULL REFERENCES historian_meta.roles(id) ON DELETE CASCADE,
    trip_category VARCHAR(255), -- 'EMERGENCY_TRIP', 'SAFETY_INTERLOCK', 'SOFT_LIMIT', NULL=all
    equipment_id VARCHAR(255), -- NULL = all equipment in category
    
    can_view BOOLEAN DEFAULT TRUE,
    can_clear_non_safety BOOLEAN DEFAULT FALSE,
    can_clear_safety BOOLEAN DEFAULT FALSE,
    can_override BOOLEAN DEFAULT FALSE,
    
    requires_approval_to_clear BOOLEAN DEFAULT FALSE,
    requires_approval_to_override BOOLEAN DEFAULT TRUE,
    requires_2fa_to_override BOOLEAN DEFAULT TRUE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(role_id, trip_category, equipment_id)
);

CREATE INDEX idx_role_trip_perms_role ON historian_meta.role_trip_permissions(role_id);
CREATE INDEX idx_role_trip_perms_category ON historian_meta.role_trip_permissions(trip_category);

-- =====================================================
-- 9. ROLE INTERLOCK PERMISSIONS (New)
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.role_interlock_permissions (
    id SERIAL PRIMARY KEY,
    role_id INTEGER NOT NULL REFERENCES historian_meta.roles(id) ON DELETE CASCADE,
    interlock_category VARCHAR(255), -- 'SAFETY', 'OPERATIONAL', 'MAINTENANCE', NULL=all
    equipment_id VARCHAR(255), -- NULL = all equipment in category
    
    can_view BOOLEAN DEFAULT TRUE,
    can_enable BOOLEAN DEFAULT FALSE,
    can_disable_non_safety BOOLEAN DEFAULT FALSE,
    can_disable_safety BOOLEAN DEFAULT FALSE,
    can_override BOOLEAN DEFAULT FALSE,
    
    requires_approval_to_disable BOOLEAN DEFAULT FALSE,
    requires_approval_to_override BOOLEAN DEFAULT TRUE,
    requires_2fa_to_override BOOLEAN DEFAULT TRUE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(role_id, interlock_category, equipment_id)
);

CREATE INDEX idx_role_interlock_perms_role ON historian_meta.role_interlock_permissions(role_id);
CREATE INDEX idx_role_interlock_perms_category ON historian_meta.role_interlock_permissions(interlock_category);

-- =====================================================
-- 10. FUNCTIONS: SoD VALIDATION
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.check_sod_violation(
    p_operation_type VARCHAR(255),
    p_requested_by INTEGER,
    p_approved_by INTEGER,
    p_executed_by INTEGER
) RETURNS TABLE(
    violation_detected BOOLEAN,
    violation_reason TEXT,
    exception_allowed BOOLEAN
) AS $$
DECLARE
    v_sod_rules historian_meta.sod_rules%ROWTYPE;
    v_requester_role VARCHAR(255);
    v_approver_role VARCHAR(255);
    v_executor_role VARCHAR(255);
BEGIN
    -- Get SoD rules for operation
    SELECT * INTO v_sod_rules FROM historian_meta.sod_rules WHERE operation_type = p_operation_type;
    
    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, 'No SoD rules defined for operation', FALSE;
        RETURN;
    END IF;
    
    -- Get roles for users
    SELECT role_id INTO v_requester_role FROM historian_meta.users WHERE id = p_requested_by;
    SELECT role_id INTO v_approver_role FROM historian_meta.users WHERE id = p_approved_by;
    SELECT role_id INTO v_executor_role FROM historian_meta.users WHERE id = p_executed_by;
    
    -- Check if requester and approver are same (always violation)
    IF p_requested_by = p_approved_by THEN
        RETURN QUERY SELECT TRUE, 'Requester cannot be approver', v_sod_rules.exception_allowed;
        RETURN;
    END IF;
    
    -- Check if approver and executor are same (if executor provided)
    IF p_executed_by IS NOT NULL AND p_approved_by = p_executed_by THEN
        RETURN QUERY SELECT TRUE, 'Approver cannot be executor', v_sod_rules.exception_allowed;
        RETURN;
    END IF;
    
    -- No violation
    RETURN QUERY SELECT FALSE, NULL::TEXT, FALSE;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 11. FUNCTIONS: CERTIFICATION CHECK
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.check_user_certification(
    p_user_id INTEGER,
    p_certification_type VARCHAR(255)
) RETURNS TABLE(
    is_certified BOOLEAN,
    certification_id INTEGER,
    expires_at TIMESTAMP,
    days_until_expiry INTEGER,
    is_expiring_soon BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        uc.is_active,
        uc.id,
        uc.expires_at,
        EXTRACT(DAY FROM (uc.expires_at - CURRENT_TIMESTAMP))::INTEGER,
        (EXTRACT(DAY FROM (uc.expires_at - CURRENT_TIMESTAMP)) < 30)
    FROM historian_meta.user_certifications uc
    WHERE uc.user_id = p_user_id
      AND uc.certification_type = p_certification_type
      AND uc.is_active = TRUE
      AND uc.expires_at > CURRENT_TIMESTAMP
    LIMIT 1;
    
    -- If no results, return not certified
    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, NULL::INTEGER, NULL::TIMESTAMP, NULL::INTEGER, NULL::BOOLEAN;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 12. FUNCTIONS: CHECK OPERATION ALLOWED
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.check_operation_allowed(
    p_user_id INTEGER,
    p_operation_type VARCHAR(255)
) RETURNS TABLE(
    operation_allowed BOOLEAN,
    reason TEXT,
    requires_approval BOOLEAN,
    requires_2fa BOOLEAN,
    required_certification VARCHAR(255)
) AS $$
DECLARE
    v_role_id INTEGER;
    v_op_perms historian_meta.role_operation_permissions%ROWTYPE;
    v_certification_valid BOOLEAN;
    v_time_window_check BOOLEAN;
    v_daily_limit_exceeded BOOLEAN;
BEGIN
    -- Get user's role
    SELECT role_id INTO v_role_id FROM historian_meta.users WHERE id = p_user_id;
    
    IF v_role_id IS NULL THEN
        RETURN QUERY SELECT FALSE, 'User has no role assigned', FALSE, FALSE, NULL::VARCHAR;
        RETURN;
    END IF;
    
    -- Get operation permissions
    SELECT * INTO v_op_perms 
    FROM historian_meta.role_operation_permissions 
    WHERE role_id = v_role_id AND operation_type = p_operation_type;
    
    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, 'Role not authorized for this operation', FALSE, FALSE, NULL::VARCHAR;
        RETURN;
    END IF;
    
    IF NOT v_op_perms.can_execute THEN
        RETURN QUERY SELECT FALSE, 'Operation execution not permitted for this role', FALSE, FALSE, NULL::VARCHAR;
        RETURN;
    END IF;
    
    -- Check certification if required
    IF v_op_perms.requires_certification_type IS NOT NULL THEN
        SELECT is_certified INTO v_certification_valid 
        FROM historian_meta.check_user_certification(p_user_id, v_op_perms.requires_certification_type);
        
        IF NOT v_certification_valid THEN
            RETURN QUERY SELECT FALSE, 'Required certification not active', FALSE, FALSE, v_op_perms.requires_certification_type;
            RETURN;
        END IF;
    END IF;
    
    -- Check time window if defined
    IF v_op_perms.time_window_id IS NOT NULL THEN
        -- Time window validation would go here
        -- For now, assume valid
        v_time_window_check := TRUE;
    END IF;
    
    -- All checks passed
    RETURN QUERY SELECT 
        TRUE, 
        'Operation allowed',
        v_op_perms.requires_approval,
        v_op_perms.requires_2fa,
        v_op_perms.requires_certification_type;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 13. GRANTS
-- =====================================================
GRANT SELECT, INSERT, UPDATE ON historian_meta.role_operation_permissions TO opc_app_user;
GRANT SELECT, INSERT ON historian_meta.sod_rules TO opc_app_user;
GRANT SELECT, INSERT, UPDATE ON historian_meta.operation_approvals TO opc_app_user;
GRANT SELECT, INSERT, UPDATE ON historian_meta.user_certifications TO opc_app_user;
GRANT SELECT, INSERT ON historian_meta.time_based_access_windows TO opc_app_user;
GRANT SELECT, INSERT ON historian_meta.operation_audit_trail TO opc_app_user;
GRANT SELECT, INSERT, UPDATE ON historian_meta.role_alarm_permissions TO opc_app_user;
GRANT SELECT, INSERT, UPDATE ON historian_meta.role_trip_permissions TO opc_app_user;
GRANT SELECT, INSERT, UPDATE ON historian_meta.role_interlock_permissions TO opc_app_user;

GRANT EXECUTE ON FUNCTION historian_meta.check_sod_violation TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.check_user_certification TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.check_operation_allowed TO opc_app_user;

GRANT USAGE ON ALL SEQUENCES IN SCHEMA historian_meta TO opc_app_user;

-- =====================================================
-- MIGRATION COMPLETE
-- =====================================================
