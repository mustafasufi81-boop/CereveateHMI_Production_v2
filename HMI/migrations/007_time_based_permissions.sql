-- =====================================================
-- Migration 007: Time-Based Permissions
-- Description: Implements temporary and time-restricted permissions
-- Dependencies: 006_two_person_rule.sql
-- =====================================================

-- =====================================================
-- 1. TEMPORARY PERMISSIONS TABLE
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.temporary_permissions (
    id SERIAL PRIMARY KEY,
    
    -- User Reference
    user_id INTEGER NOT NULL REFERENCES historian_meta.users(id) ON DELETE CASCADE,
    
    -- Permission Details
    permission_type VARCHAR(50) NOT NULL, -- 'tag', 'equipment', 'alarm', 'role_temporary'
    permission_target VARCHAR(255) NOT NULL, -- tag_id, equipment_id, alarm_category, or role_id
    permission_action VARCHAR(50) NOT NULL, -- 'view', 'write', 'start', 'stop', 'acknowledge', etc.
    
    -- Time Constraints
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    
    -- Granter Information
    granted_by INTEGER NOT NULL REFERENCES historian_meta.users(id),
    
    -- Revocation
    revoked_at TIMESTAMP,
    revoked_by INTEGER REFERENCES historian_meta.users(id),
    revoke_reason TEXT,
    
    -- Justification
    reason TEXT NOT NULL,
    approval_reference VARCHAR(255), -- Reference to approval if needed
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Auto-notification
    notify_before_expiry_minutes INTEGER DEFAULT 15,
    expiry_notification_sent BOOLEAN DEFAULT FALSE,
    
    -- Additional Context
    additional_data JSONB,
    
    -- Constraints
    CONSTRAINT chk_expires_after_granted CHECK (expires_at > granted_at)
);

-- Create indexes
CREATE INDEX idx_temp_perms_user ON historian_meta.temporary_permissions(user_id);
CREATE INDEX idx_temp_perms_type_target ON historian_meta.temporary_permissions(permission_type, permission_target);
CREATE INDEX idx_temp_perms_active ON historian_meta.temporary_permissions(is_active, expires_at);
CREATE INDEX idx_temp_perms_expires ON historian_meta.temporary_permissions(expires_at);
CREATE INDEX idx_temp_perms_granted_by ON historian_meta.temporary_permissions(granted_by);

-- =====================================================
-- 2. PERMISSION TEMPLATES TABLE
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.permission_templates (
    id SERIAL PRIMARY KEY,
    
    -- Template Identification
    template_code VARCHAR(100) UNIQUE NOT NULL,
    template_name VARCHAR(255) NOT NULL,
    description TEXT,
    
    -- Template Type
    template_type VARCHAR(50) NOT NULL, -- 'maintenance', 'training', 'contractor', 'emergency', 'audit'
    
    -- Default Duration
    default_duration_hours INTEGER NOT NULL DEFAULT 24,
    max_duration_hours INTEGER DEFAULT 168, -- 1 week max
    
    -- Permissions Granted
    permissions JSONB NOT NULL, -- Array of {type, target, action}
    
    -- Approval Requirements
    requires_approval BOOLEAN DEFAULT FALSE,
    required_approver_role_id INTEGER REFERENCES historian_meta.roles(id),
    
    -- Usage Tracking
    usage_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMP,
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES historian_meta.users(id),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX idx_perm_templates_code ON historian_meta.permission_templates(template_code);
CREATE INDEX idx_perm_templates_type ON historian_meta.permission_templates(template_type);
CREATE INDEX idx_perm_templates_active ON historian_meta.permission_templates(is_active);

-- Insert standard templates
INSERT INTO historian_meta.permission_templates (
    template_code, template_name, template_type, default_duration_hours, max_duration_hours,
    permissions, requires_approval, description
) VALUES
(
    'MAINTENANCE_48H',
    'Maintenance Access (48 hours)',
    'maintenance',
    48,
    72,
    '[{"type": "equipment", "action": "maintenance_mode"}, {"type": "alarm", "action": "acknowledge"}]',
    TRUE,
    'Standard 48-hour maintenance window access'
),
(
    'CONTRACTOR_ACCESS',
    'Contractor Limited Access',
    'contractor',
    8,
    24,
    '[{"type": "tag", "action": "view"}, {"type": "equipment", "action": "view"}]',
    TRUE,
    'Read-only access for contractors'
),
(
    'TRAINEE_30D',
    'Trainee Supervised Access',
    'training',
    720,
    720, -- 30 days
    '[{"type": "equipment", "action": "supervised_control"}, {"type": "alarm", "action": "view"}]',
    TRUE,
    '30-day supervised access for trainees'
),
(
    'EMERGENCY_ACCESS',
    'Emergency Elevated Access',
    'emergency',
    4,
    8,
    '[{"type": "equipment", "action": "emergency_control"}, {"type": "alarm", "action": "all"}]',
    FALSE,
    'Emergency elevated privileges'
),
(
    'WEEKEND_RESTRICTION',
    'Weekend Access Restriction',
    'audit',
    48,
    999999,
    '[{"type": "tag", "action": "no_write", "days": [0, 6]}]',
    FALSE,
    'Prevent modifications on weekends'
)
ON CONFLICT (template_code) DO NOTHING;

-- =====================================================
-- 3. TEMPORARY ACCESS REQUESTS TABLE
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.temporary_access_requests (
    id SERIAL PRIMARY KEY,
    
    -- Request Details
    user_id INTEGER NOT NULL REFERENCES historian_meta.users(id),
    requested_by INTEGER NOT NULL REFERENCES historian_meta.users(id), -- May be different from user_id
    template_id INTEGER REFERENCES historian_meta.permission_templates(id),
    
    -- Time Range
    requested_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    requested_end TIMESTAMP NOT NULL,
    requested_duration_hours INTEGER,
    
    -- Justification
    justification TEXT NOT NULL,
    business_need VARCHAR(255),
    
    -- Approval
    status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'approved', 'denied', 'expired', 'active', 'revoked'
    approved_by INTEGER REFERENCES historian_meta.users(id),
    approved_at TIMESTAMP,
    denied_by INTEGER REFERENCES historian_meta.users(id),
    denied_at TIMESTAMP,
    denial_reason TEXT,
    
    -- Execution
    granted_permissions_ids INTEGER[], -- Array of temporary_permissions IDs
    activated_at TIMESTAMP,
    revoked_at TIMESTAMP,
    
    -- Metadata
    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX idx_temp_access_req_user ON historian_meta.temporary_access_requests(user_id);
CREATE INDEX idx_temp_access_req_status ON historian_meta.temporary_access_requests(status);
CREATE INDEX idx_temp_access_req_requested_by ON historian_meta.temporary_access_requests(requested_by);

-- =====================================================
-- 4. ACTIVE TEMPORARY PERMISSIONS VIEW
-- =====================================================
CREATE OR REPLACE VIEW historian_meta.active_temporary_permissions AS
SELECT 
    tp.id,
    tp.user_id,
    u.username,
    tp.permission_type,
    tp.permission_target,
    tp.permission_action,
    tp.granted_at,
    tp.expires_at,
    tp.granted_by,
    gu.username as granted_by_username,
    tp.reason,
    EXTRACT(EPOCH FROM (tp.expires_at - CURRENT_TIMESTAMP))/3600 as hours_until_expiry,
    CASE 
        WHEN tp.expires_at < CURRENT_TIMESTAMP THEN 'expired'
        WHEN tp.expires_at < CURRENT_TIMESTAMP + INTERVAL '1 hour' THEN 'expiring_soon'
        ELSE 'active'
    END as status
FROM historian_meta.temporary_permissions tp
JOIN historian_meta.users u ON tp.user_id = u.id
JOIN historian_meta.users gu ON tp.granted_by = gu.id
WHERE tp.is_active = TRUE
  AND tp.revoked_at IS NULL
  AND tp.expires_at > CURRENT_TIMESTAMP
ORDER BY tp.expires_at ASC;

-- =====================================================
-- 5. USER PERMISSION SUMMARY VIEW (Including Temporary)
-- =====================================================
CREATE OR REPLACE VIEW historian_meta.user_permission_summary AS
SELECT 
    u.id as user_id,
    u.username,
    r.name as role_name,
    r.is_admin,
    
    -- Regular Permissions
    (SELECT COUNT(*) FROM historian_meta.role_tag_permissions WHERE role_id = u.role_id) as regular_tag_permissions,
    (SELECT COUNT(*) FROM historian_meta.role_equipment_permissions WHERE role_id = u.role_id) as regular_equipment_permissions,
    (SELECT COUNT(*) FROM historian_meta.role_alarm_permissions WHERE role_id = u.role_id) as regular_alarm_permissions,
    
    -- Temporary Permissions
    (SELECT COUNT(*) FROM historian_meta.temporary_permissions tp 
     WHERE tp.user_id = u.id AND tp.is_active = TRUE 
     AND tp.revoked_at IS NULL AND tp.expires_at > CURRENT_TIMESTAMP) as active_temporary_permissions,
    
    (SELECT MAX(tp.expires_at) FROM historian_meta.temporary_permissions tp 
     WHERE tp.user_id = u.id AND tp.is_active = TRUE 
     AND tp.revoked_at IS NULL AND tp.expires_at > CURRENT_TIMESTAMP) as next_temp_expiry,
    
    -- Pending Requests
    (SELECT COUNT(*) FROM historian_meta.temporary_access_requests tar 
     WHERE tar.user_id = u.id AND tar.status = 'pending') as pending_access_requests
    
FROM historian_meta.users u
LEFT JOIN historian_meta.roles r ON u.role_id = r.id
WHERE u.status = 'approved';

-- =====================================================
-- 6. FUNCTION: GRANT TEMPORARY PERMISSION
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.grant_temporary_permission(
    p_user_id INTEGER,
    p_granted_by INTEGER,
    p_permission_type VARCHAR(50),
    p_permission_target VARCHAR(255),
    p_permission_action VARCHAR(50),
    p_duration_hours INTEGER,
    p_reason TEXT,
    p_additional_data JSONB DEFAULT NULL
) RETURNS INTEGER AS $$
DECLARE
    v_permission_id INTEGER;
    v_expires_at TIMESTAMP;
BEGIN
    -- Calculate expiry time
    v_expires_at := CURRENT_TIMESTAMP + (p_duration_hours || ' hours')::INTERVAL;
    
    -- Create temporary permission
    INSERT INTO historian_meta.temporary_permissions (
        user_id, granted_by, permission_type, permission_target, permission_action,
        expires_at, reason, additional_data
    ) VALUES (
        p_user_id, p_granted_by, p_permission_type, p_permission_target, p_permission_action,
        v_expires_at, p_reason, p_additional_data
    ) RETURNING id INTO v_permission_id;
    
    -- Log the action
    PERFORM historian_meta.log_user_action(
        p_granted_by, 
        (SELECT username FROM historian_meta.users WHERE id = p_granted_by),
        'TEMP_PERMISSION_GRANTED',
        'admin',
        'temporary_permission',
        v_permission_id::TEXT,
        NULL,
        NULL,
        p_permission_type || ':' || p_permission_target || ':' || p_permission_action,
        TRUE,
        NULL,
        NULL,
        NULL,
        NULL,
        jsonb_build_object('user_id', p_user_id, 'duration_hours', p_duration_hours, 'expires_at', v_expires_at)
    );
    
    RETURN v_permission_id;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 7. FUNCTION: REVOKE TEMPORARY PERMISSION
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.revoke_temporary_permission(
    p_permission_id INTEGER,
    p_revoked_by INTEGER,
    p_revoke_reason TEXT
) RETURNS BOOLEAN AS $$
BEGIN
    UPDATE historian_meta.temporary_permissions
    SET is_active = FALSE,
        revoked_at = CURRENT_TIMESTAMP,
        revoked_by = p_revoked_by,
        revoke_reason = p_revoke_reason
    WHERE id = p_permission_id
      AND is_active = TRUE
      AND revoked_at IS NULL;
    
    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 8. FUNCTION: CHECK TEMPORARY PERMISSION
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.check_temporary_permission(
    p_user_id INTEGER,
    p_permission_type VARCHAR(50),
    p_permission_target VARCHAR(255),
    p_permission_action VARCHAR(50)
) RETURNS BOOLEAN AS $$
DECLARE
    v_has_permission BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 
        FROM historian_meta.temporary_permissions
        WHERE user_id = p_user_id
          AND permission_type = p_permission_type
          AND permission_target = p_permission_target
          AND permission_action = p_permission_action
          AND is_active = TRUE
          AND revoked_at IS NULL
          AND expires_at > CURRENT_TIMESTAMP
    ) INTO v_has_permission;
    
    RETURN v_has_permission;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 9. FUNCTION: APPLY PERMISSION TEMPLATE
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.apply_permission_template(
    p_user_id INTEGER,
    p_template_code VARCHAR(100),
    p_granted_by INTEGER,
    p_duration_hours INTEGER DEFAULT NULL,
    p_reason TEXT DEFAULT NULL
) RETURNS TABLE(
    permission_ids INTEGER[],
    expires_at TIMESTAMP
) AS $$
DECLARE
    v_template RECORD;
    v_permission RECORD;
    v_permission_ids INTEGER[] := ARRAY[]::INTEGER[];
    v_expires_at TIMESTAMP;
    v_duration INTEGER;
    v_permission_id INTEGER;
BEGIN
    -- Get template
    SELECT * INTO v_template
    FROM historian_meta.permission_templates
    WHERE template_code = p_template_code AND is_active = TRUE;
    
    IF v_template.id IS NULL THEN
        RAISE EXCEPTION 'Template % not found or inactive', p_template_code;
    END IF;
    
    -- Use template duration if not specified
    v_duration := COALESCE(p_duration_hours, v_template.default_duration_hours);
    
    -- Validate max duration
    IF v_duration > v_template.max_duration_hours THEN
        RAISE EXCEPTION 'Requested duration exceeds maximum of % hours', v_template.max_duration_hours;
    END IF;
    
    v_expires_at := CURRENT_TIMESTAMP + (v_duration || ' hours')::INTERVAL;
    
    -- Grant each permission in template
    FOR v_permission IN SELECT * FROM jsonb_array_elements(v_template.permissions)
    LOOP
        SELECT historian_meta.grant_temporary_permission(
            p_user_id,
            p_granted_by,
            v_permission.value->>'type',
            COALESCE(v_permission.value->>'target', '*'),
            v_permission.value->>'action',
            v_duration,
            COALESCE(p_reason, v_template.description),
            jsonb_build_object('template_id', v_template.id, 'template_code', p_template_code)
        ) INTO v_permission_id;
        
        v_permission_ids := array_append(v_permission_ids, v_permission_id);
    END LOOP;
    
    -- Update template usage
    UPDATE historian_meta.permission_templates
    SET usage_count = usage_count + 1,
        last_used_at = CURRENT_TIMESTAMP
    WHERE id = v_template.id;
    
    permission_ids := v_permission_ids;
    expires_at := v_expires_at;
    
    RETURN NEXT;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 10. FUNCTION: CLEANUP EXPIRED PERMISSIONS
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.cleanup_expired_permissions()
RETURNS INTEGER AS $$
DECLARE
    v_expired_count INTEGER;
BEGIN
    UPDATE historian_meta.temporary_permissions
    SET is_active = FALSE
    WHERE is_active = TRUE
      AND revoked_at IS NULL
      AND expires_at < CURRENT_TIMESTAMP;
    
    GET DIAGNOSTICS v_expired_count = ROW_COUNT;
    
    RETURN v_expired_count;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 11. FUNCTION: SEND EXPIRY NOTIFICATIONS
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.check_permission_expiry_notifications()
RETURNS TABLE(
    permission_id INTEGER,
    user_id INTEGER,
    username VARCHAR(255),
    permission_type VARCHAR(50),
    permission_target VARCHAR(255),
    minutes_until_expiry NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        tp.id,
        tp.user_id,
        u.username,
        tp.permission_type,
        tp.permission_target,
        EXTRACT(EPOCH FROM (tp.expires_at - CURRENT_TIMESTAMP))/60 as minutes_until_expiry
    FROM historian_meta.temporary_permissions tp
    JOIN historian_meta.users u ON tp.user_id = u.id
    WHERE tp.is_active = TRUE
      AND tp.revoked_at IS NULL
      AND tp.expiry_notification_sent = FALSE
      AND tp.expires_at > CURRENT_TIMESTAMP
      AND tp.expires_at <= CURRENT_TIMESTAMP + (tp.notify_before_expiry_minutes || ' minutes')::INTERVAL;
    
    -- Mark as notified
    UPDATE historian_meta.temporary_permissions tp
    SET expiry_notification_sent = TRUE
    WHERE tp.is_active = TRUE
      AND tp.revoked_at IS NULL
      AND tp.expiry_notification_sent = FALSE
      AND tp.expires_at > CURRENT_TIMESTAMP
      AND tp.expires_at <= CURRENT_TIMESTAMP + (tp.notify_before_expiry_minutes || ' minutes')::INTERVAL;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 12. FUNCTION: EXTEND TEMPORARY PERMISSION
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.extend_temporary_permission(
    p_permission_id INTEGER,
    p_extended_by INTEGER,
    p_additional_hours INTEGER,
    p_reason TEXT
) RETURNS TIMESTAMP AS $$
DECLARE
    v_new_expires_at TIMESTAMP;
BEGIN
    UPDATE historian_meta.temporary_permissions
    SET expires_at = expires_at + (p_additional_hours || ' hours')::INTERVAL,
        additional_data = COALESCE(additional_data, '{}'::jsonb) || 
                         jsonb_build_object(
                             'extensions', 
                             COALESCE((additional_data->'extensions')::INTEGER, 0) + 1,
                             'last_extended_at', CURRENT_TIMESTAMP,
                             'last_extended_by', p_extended_by,
                             'last_extension_reason', p_reason
                         )
    WHERE id = p_permission_id
      AND is_active = TRUE
      AND revoked_at IS NULL
    RETURNING expires_at INTO v_new_expires_at;
    
    RETURN v_new_expires_at;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 13. GRANTS
-- =====================================================
GRANT SELECT, INSERT, UPDATE ON historian_meta.temporary_permissions TO opc_app_user;
GRANT SELECT ON historian_meta.permission_templates TO opc_app_user;
GRANT SELECT, INSERT, UPDATE ON historian_meta.temporary_access_requests TO opc_app_user;
GRANT SELECT ON historian_meta.active_temporary_permissions TO opc_app_user;
GRANT SELECT ON historian_meta.user_permission_summary TO opc_app_user;
GRANT USAGE ON SEQUENCE historian_meta.temporary_permissions_id_seq TO opc_app_user;
GRANT USAGE ON SEQUENCE historian_meta.permission_templates_id_seq TO opc_app_user;
GRANT USAGE ON SEQUENCE historian_meta.temporary_access_requests_id_seq TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.grant_temporary_permission TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.revoke_temporary_permission TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.check_temporary_permission TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.apply_permission_template TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.cleanup_expired_permissions TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.check_permission_expiry_notifications TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.extend_temporary_permission TO opc_app_user;

-- =====================================================
-- MIGRATION COMPLETE
-- =====================================================
