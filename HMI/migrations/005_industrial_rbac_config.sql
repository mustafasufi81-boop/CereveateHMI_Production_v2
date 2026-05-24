-- =====================================================
-- Migration 005: Industrial RBAC Configuration & Setup
-- Description: Initializes roles, SoD rules, operation permissions,
--              and required certifications
-- Dependencies: 004_industrial_rbac.sql
-- =====================================================

-- =====================================================
-- 1. INSERT STANDARD OPERATION TYPES
-- =====================================================

-- Define standard workflow roles for operations
INSERT INTO historian_meta.sod_rules (
    operation_type, requester_role, approver_role, executor_role, verifier_role,
    cannot_be_same_as, exception_allowed, exception_approver_role, description
) VALUES
-- ALARM OPERATIONS
('ALARM_ACKNOWLEDGE', 'OPERATOR', 'SUPERVISOR', 'OPERATOR', 'SAFETY_OFFICER',
 ARRAY['requester', 'approver'], FALSE, NULL, 'Alarm acknowledgment requires operator request & supervisor approval'),

('ALARM_CLEAR', 'SUPERVISOR', 'ADMIN', 'OPERATOR', 'SAFETY_OFFICER',
 ARRAY['requester', 'approver'], FALSE, NULL, 'Alarm clearing requires supervisor request & admin approval'),

-- TRIP OPERATIONS (Non-Safety)
('TRIP_CLEAR_NON_SAFETY', 'OPERATOR', 'SUPERVISOR', 'OPERATOR', NULL,
 ARRAY['requester', 'approver'], FALSE, NULL, 'Non-safety trip clearing requires operator request & supervisor approval'),

-- TRIP OPERATIONS (Safety-Critical)
('TRIP_CLEAR_SAFETY', 'SUPERVISOR', 'SAFETY_OFFICER', 'SAFETY_OFFICER', 'ADMIN',
 ARRAY['requester', 'approver'], TRUE, 'ADMIN', 'Safety trip clearing requires multi-stage SoD'),

('TRIP_OVERRIDE', 'OPERATOR', 'SAFETY_OFFICER', 'OPERATOR', 'SAFETY_OFFICER',
 ARRAY['requester', 'approver'], FALSE, NULL, 'Trip override requires operator request & safety officer approval with 2FA'),

-- INTERLOCK OPERATIONS (Non-Safety)
('INTERLOCK_DISABLE_NON_SAFETY', 'SUPERVISOR', 'ADMIN', 'SUPERVISOR', NULL,
 ARRAY['requester', 'approver'], FALSE, NULL, 'Operational interlock disable requires supervisor & admin approval'),

-- INTERLOCK OPERATIONS (Safety-Critical)
('INTERLOCK_DISABLE_SAFETY', 'SUPERVISOR', 'SAFETY_OFFICER', 'SAFETY_OFFICER', 'ADMIN',
 ARRAY['requester', 'approver'], FALSE, NULL, 'Safety interlock disable requires full SoD chain with 2FA'),

('INTERLOCK_OVERRIDE', 'SAFETY_OFFICER', 'ADMIN', 'SAFETY_OFFICER', 'ADMIN',
 ARRAY['approver', 'executor'], FALSE, NULL, 'Emergency override requires safety officer & admin')
ON CONFLICT (operation_type) DO NOTHING;

-- =====================================================
-- 2. CONFIGURE ROLE OPERATION PERMISSIONS
-- =====================================================

-- OPERATOR Role Permissions
INSERT INTO historian_meta.role_operation_permissions (
    role_id, operation_type, can_execute, requires_approval, requires_2fa, 
    requires_certification_type, max_daily_actions
)
SELECT 
    r.id,
    ops.operation_type,
    ops.can_execute,
    ops.requires_approval,
    ops.requires_2fa,
    ops.certification_type,
    ops.max_daily_actions
FROM historian_meta.roles r,
(
    VALUES
    ('OPERATOR', 'ALARM_ACKNOWLEDGE', TRUE, FALSE, FALSE, 'EQUIPMENT_TRAINING', 50),
    ('OPERATOR', 'TRIP_CLEAR_NON_SAFETY', FALSE, FALSE, FALSE, NULL, NULL),
    ('OPERATOR', 'TRIP_OVERRIDE', TRUE, TRUE, FALSE, 'EQUIPMENT_TRAINING', 5),
    ('OPERATOR', 'INTERLOCK_DISABLE_NON_SAFETY', FALSE, FALSE, FALSE, NULL, NULL)
) AS ops(role_name, operation_type, can_execute, requires_approval, requires_2fa, certification_type, max_daily_actions)
WHERE r.name = ops.role_name
ON CONFLICT (role_id, operation_type) DO UPDATE
SET can_execute = EXCLUDED.can_execute,
    requires_approval = EXCLUDED.requires_approval,
    requires_2fa = EXCLUDED.requires_2fa;

-- SUPERVISOR Role Permissions
INSERT INTO historian_meta.role_operation_permissions (
    role_id, operation_type, can_execute, requires_approval, requires_2fa, 
    requires_certification_type, max_daily_actions
)
SELECT 
    r.id,
    ops.operation_type,
    ops.can_execute,
    ops.requires_approval,
    ops.requires_2fa,
    ops.certification_type,
    ops.max_daily_actions
FROM historian_meta.roles r,
(
    VALUES
    ('SUPERVISOR', 'ALARM_ACKNOWLEDGE', TRUE, FALSE, FALSE, 'EQUIPMENT_TRAINING', 100),
    ('SUPERVISOR', 'ALARM_CLEAR', TRUE, TRUE, FALSE, 'EQUIPMENT_TRAINING', 50),
    ('SUPERVISOR', 'TRIP_CLEAR_NON_SAFETY', TRUE, TRUE, FALSE, 'EQUIPMENT_TRAINING', 20),
    ('SUPERVISOR', 'TRIP_OVERRIDE', FALSE, TRUE, TRUE, 'EQUIPMENT_TRAINING', NULL),
    ('SUPERVISOR', 'INTERLOCK_DISABLE_NON_SAFETY', TRUE, TRUE, FALSE, 'EQUIPMENT_TRAINING', 10),
    ('SUPERVISOR', 'INTERLOCK_DISABLE_SAFETY', FALSE, FALSE, FALSE, NULL, NULL)
) AS ops(role_name, operation_type, can_execute, requires_approval, requires_2fa, certification_type, max_daily_actions)
WHERE r.name = ops.role_name
ON CONFLICT (role_id, operation_type) DO UPDATE
SET can_execute = EXCLUDED.can_execute,
    requires_approval = EXCLUDED.requires_approval,
    requires_2fa = EXCLUDED.requires_2fa;

-- SAFETY_OFFICER Role Permissions
INSERT INTO historian_meta.role_operation_permissions (
    role_id, operation_type, can_execute, requires_approval, requires_2fa, 
    requires_certification_type, max_daily_actions
)
SELECT 
    r.id,
    ops.operation_type,
    ops.can_execute,
    ops.requires_approval,
    ops.requires_2fa,
    ops.certification_type,
    ops.max_daily_actions
FROM historian_meta.roles r,
(
    VALUES
    ('SAFETY_OFFICER', 'ALARM_ACKNOWLEDGE', TRUE, FALSE, FALSE, 'SAFETY_SYSTEM_CERTIFIED', 100),
    ('SAFETY_OFFICER', 'ALARM_CLEAR', TRUE, FALSE, FALSE, 'SAFETY_SYSTEM_CERTIFIED', 100),
    ('SAFETY_OFFICER', 'TRIP_CLEAR_SAFETY', TRUE, TRUE, TRUE, 'SAFETY_SYSTEM_CERTIFIED', 10),
    ('SAFETY_OFFICER', 'TRIP_OVERRIDE', TRUE, FALSE, TRUE, 'SAFETY_SYSTEM_CERTIFIED', 10),
    ('SAFETY_OFFICER', 'INTERLOCK_DISABLE_SAFETY', TRUE, TRUE, TRUE, 'SAFETY_SYSTEM_CERTIFIED', 10),
    ('SAFETY_OFFICER', 'INTERLOCK_OVERRIDE', TRUE, TRUE, TRUE, 'SAFETY_SYSTEM_CERTIFIED', 5)
) AS ops(role_name, operation_type, can_execute, requires_approval, requires_2fa, certification_type, max_daily_actions)
WHERE r.name = ops.role_name
ON CONFLICT (role_id, operation_type) DO UPDATE
SET can_execute = EXCLUDED.can_execute,
    requires_approval = EXCLUDED.requires_approval,
    requires_2fa = EXCLUDED.requires_2fa;

-- ADMIN Role Permissions (All operations allowed)
INSERT INTO historian_meta.role_operation_permissions (
    role_id, operation_type, can_execute, requires_approval, requires_2fa, 
    requires_certification_type
)
SELECT 
    r.id,
    sod.operation_type,
    TRUE,
    FALSE,
    FALSE,
    NULL
FROM historian_meta.roles r, historian_meta.sod_rules sod
WHERE (r.is_admin = TRUE OR r.name = 'ADMIN')
ON CONFLICT (role_id, operation_type) DO UPDATE
SET can_execute = TRUE,
    requires_approval = FALSE;

-- =====================================================
-- 3. CONFIGURE TIME-BASED ACCESS WINDOWS
-- =====================================================
INSERT INTO historian_meta.time_based_access_windows (
    operation_type, day_of_week, allowed_start_hour, allowed_end_hour,
    requires_supervisor_approval, requires_2fa, description, is_active
) VALUES
-- Normal operations Monday-Friday, 6 AM to 10 PM
('ALARM_ACKNOWLEDGE', 'WEEKDAY', 6, 22, FALSE, FALSE, 'Normal business hours', TRUE),
('ALARM_CLEAR', 'WEEKDAY', 6, 22, FALSE, FALSE, 'Normal business hours', TRUE),
('TRIP_CLEAR_NON_SAFETY', 'WEEKDAY', 6, 22, FALSE, FALSE, 'Normal business hours', TRUE),
('INTERLOCK_DISABLE_NON_SAFETY', 'WEEKDAY', 6, 22, FALSE, FALSE, 'Normal business hours', TRUE),

-- Maintenance windows Saturday-Sunday, 8 AM to 6 PM
('INTERLOCK_DISABLE_SAFETY', 'SAT', 8, 18, TRUE, FALSE, 'Maintenance window', TRUE),
('INTERLOCK_DISABLE_SAFETY', 'SUN', 8, 18, TRUE, FALSE, 'Maintenance window', TRUE),

-- Safety operations restricted to specific hours (Wed/Fri 2-4 PM)
('TRIP_OVERRIDE', 'WED', 14, 16, FALSE, FALSE, 'Scheduled safety window', TRUE),
('TRIP_OVERRIDE', 'FRI', 14, 16, FALSE, FALSE, 'Scheduled safety window', TRUE),

-- Emergency operations 24/7
('INTERLOCK_OVERRIDE', 'DAILY', 0, 23, FALSE, TRUE, 'Emergency only - 24/7', TRUE)
ON CONFLICT (operation_type, day_of_week) DO NOTHING;

-- =====================================================
-- 4. INSERT SAMPLE CERTIFICATIONS
-- =====================================================
-- Define certification types (reference data)
CREATE TABLE IF NOT EXISTS historian_meta.certification_types (
    id SERIAL PRIMARY KEY,
    certification_type VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    validity_months INTEGER DEFAULT 12,
    renewal_notice_days INTEGER DEFAULT 30,
    requires_exam BOOLEAN DEFAULT FALSE,
    minimum_training_hours INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE
);

INSERT INTO historian_meta.certification_types (
    certification_type, description, validity_months, renewal_notice_days,
    requires_exam, minimum_training_hours
) VALUES
('EQUIPMENT_TRAINING', 'Basic equipment operation & safety', 12, 30, TRUE, 8),
('SAFETY_SYSTEM_CERTIFIED', 'Advanced safety system knowledge', 6, 30, TRUE, 16),
('EMERGENCY_PROCEDURES', 'Emergency response procedures', 12, 30, FALSE, 4),
('INTERLOCK_MANAGEMENT', 'Interlock system management', 12, 30, TRUE, 12),
('TRIP_OVERRIDE_AUTHORIZED', 'Authorized for trip override', 6, 30, TRUE, 8)
ON CONFLICT DO NOTHING;

-- =====================================================
-- 5. CREATE VIEWS FOR COMPLIANCE REPORTING
-- =====================================================

-- View: Users with expiring certifications
CREATE OR REPLACE VIEW historian_meta.expiring_certifications_view AS
SELECT 
    u.id as user_id,
    u.username,
    r.name as role_name,
    uc.certification_type,
    uc.expires_at,
    EXTRACT(DAY FROM (uc.expires_at - CURRENT_TIMESTAMP))::INTEGER as days_remaining,
    CASE 
        WHEN EXTRACT(DAY FROM (uc.expires_at - CURRENT_TIMESTAMP)) < 7 THEN 'CRITICAL'
        WHEN EXTRACT(DAY FROM (uc.expires_at - CURRENT_TIMESTAMP)) < 30 THEN 'WARNING'
        ELSE 'OK'
    END as status,
    uc.certified_by,
    uc.training_provider
FROM historian_meta.users u
JOIN historian_meta.roles r ON u.role_id = r.id
JOIN historian_meta.user_certifications uc ON u.id = uc.user_id
WHERE uc.is_active = TRUE
  AND uc.expires_at <= CURRENT_TIMESTAMP + INTERVAL '30 days'
ORDER BY uc.expires_at ASC;

-- View: Pending approvals (uses actual operation_approvals schema)
CREATE OR REPLACE VIEW historian_meta.pending_approvals_view AS
SELECT 
    oa.id,
    oa.operation_type,
    oa.operation_id,
    u_req.username as requested_by,
    oa.requested_at,
    COALESCE(oa.justification, '') as request_reason,
    oa.status,
    oa.priority,
    oa.expires_at as execution_deadline,
    EXTRACT(HOUR FROM (COALESCE(oa.expires_at, CURRENT_TIMESTAMP + INTERVAL '24 hours') - CURRENT_TIMESTAMP))::INTEGER as hours_remaining
FROM historian_meta.operation_approvals oa
JOIN historian_meta.users u_req ON oa.requested_by = u_req.id
WHERE oa.status IN ('REQUESTED')
ORDER BY oa.priority DESC, oa.requested_at ASC;

-- View: User operation permissions expanded
CREATE OR REPLACE VIEW historian_meta.user_operation_permissions_view AS
SELECT 
    u.id as user_id,
    u.username,
    r.name as role_name,
    rop.operation_type,
    rop.can_execute,
    rop.requires_approval,
    rop.requires_2fa,
    rop.requires_certification_type,
    rop.max_daily_actions,
    CASE 
        WHEN rop.requires_certification_type IS NULL THEN TRUE
        ELSE EXISTS(
            SELECT 1 FROM historian_meta.user_certifications uc
            WHERE uc.user_id = u.id
              AND uc.certification_type = rop.requires_certification_type
              AND uc.is_active = TRUE
              AND uc.expires_at > CURRENT_TIMESTAMP
        )
    END as certification_valid
FROM historian_meta.users u
JOIN historian_meta.roles r ON u.role_id = r.id
LEFT JOIN historian_meta.role_operation_permissions rop ON r.id = rop.role_id
WHERE u.status = 'approved'
ORDER BY r.name, rop.operation_type;

-- =====================================================
-- 6. GRANT PERMISSIONS ON VIEWS
-- =====================================================
GRANT SELECT ON historian_meta.expiring_certifications_view TO opc_app_user;
GRANT SELECT ON historian_meta.pending_approvals_view TO opc_app_user;
GRANT SELECT ON historian_meta.user_operation_permissions_view TO opc_app_user;
GRANT SELECT ON historian_meta.certification_types TO opc_app_user;

-- =====================================================
-- MIGRATION COMPLETE
-- =====================================================
