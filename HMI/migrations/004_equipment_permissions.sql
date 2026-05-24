-- =====================================================
-- Migration 004: Equipment-Level Permissions
-- Description: Implements fine-grained control over individual equipment
-- Dependencies: 003_session_management.sql
-- =====================================================

-- =====================================================
-- 1. ROLE EQUIPMENT PERMISSIONS TABLE
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.role_equipment_permissions (
    id SERIAL PRIMARY KEY,
    
    -- Role Reference
    role_id INTEGER NOT NULL REFERENCES historian_meta.roles(id) ON DELETE CASCADE,
    
    -- Equipment Identification
    equipment_id VARCHAR(255) NOT NULL,
    equipment_type VARCHAR(100), -- 'COMPRESSOR', 'PUMP', 'VALVE', 'MOTOR', etc.
    
    -- View Permission
    can_view BOOLEAN DEFAULT TRUE,
    
    -- Control Permissions
    can_start BOOLEAN DEFAULT FALSE,
    can_stop BOOLEAN DEFAULT FALSE,
    can_change_mode BOOLEAN DEFAULT FALSE,
    can_change_setpoint BOOLEAN DEFAULT FALSE,
    
    -- Advanced Permissions
    can_emergency_stop BOOLEAN DEFAULT FALSE,
    can_override_interlock BOOLEAN DEFAULT FALSE,
    can_reset_alarm BOOLEAN DEFAULT FALSE,
    
    -- Time-based Permissions (optional)
    valid_from TIMESTAMP DEFAULT NULL,
    valid_until TIMESTAMP DEFAULT NULL,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES historian_meta.users(id),
    
    -- Ensure unique combination
    UNIQUE(role_id, equipment_id)
);

-- Create indexes
CREATE INDEX idx_role_equipment_perms_role ON historian_meta.role_equipment_permissions(role_id);
CREATE INDEX idx_role_equipment_perms_equipment ON historian_meta.role_equipment_permissions(equipment_id);
CREATE INDEX idx_role_equipment_perms_type ON historian_meta.role_equipment_permissions(equipment_type);
CREATE INDEX idx_role_equipment_perms_validity ON historian_meta.role_equipment_permissions(valid_from, valid_until);

-- =====================================================
-- 2. EQUIPMENT REGISTRY TABLE
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.equipment_registry (
    id SERIAL PRIMARY KEY,
    
    -- Equipment Identification
    equipment_id VARCHAR(255) UNIQUE NOT NULL,
    equipment_name VARCHAR(255) NOT NULL,
    equipment_type VARCHAR(100) NOT NULL,
    
    -- Location
    plant VARCHAR(255),
    area VARCHAR(255),
    
    -- Classification
    criticality VARCHAR(50), -- 'low', 'medium', 'high', 'critical'
    safety_classified BOOLEAN DEFAULT FALSE,
    
    -- Control Mode
    current_mode VARCHAR(50), -- 'auto', 'manual', 'hand', 'off', 'fault'
    default_mode VARCHAR(50) DEFAULT 'auto',
    
    -- Permission Requirements
    requires_two_person_rule BOOLEAN DEFAULT FALSE,
    requires_supervisor_approval BOOLEAN DEFAULT FALSE,
    
    -- Associated Tags
    tags JSONB, -- Array of tag IDs associated with this equipment
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_operational BOOLEAN DEFAULT TRUE,
    
    -- Metadata
    description TEXT,
    manufacturer VARCHAR(255),
    model VARCHAR(255),
    commissioned_date DATE,
    last_maintenance_date DATE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX idx_equipment_registry_id ON historian_meta.equipment_registry(equipment_id);
CREATE INDEX idx_equipment_registry_type ON historian_meta.equipment_registry(equipment_type);
CREATE INDEX idx_equipment_registry_location ON historian_meta.equipment_registry(plant, area);
CREATE INDEX idx_equipment_registry_criticality ON historian_meta.equipment_registry(criticality);
CREATE INDEX idx_equipment_registry_active ON historian_meta.equipment_registry(is_active);

-- =====================================================
-- 3. EQUIPMENT TYPES REFERENCE TABLE
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.equipment_types (
    id SERIAL PRIMARY KEY,
    type_code VARCHAR(100) UNIQUE NOT NULL,
    type_name VARCHAR(255) NOT NULL,
    category VARCHAR(100), -- 'rotating', 'static', 'control', 'safety'
    default_permissions JSONB, -- Default permission set for this type
    typical_operations JSONB, -- List of typical operations
    icon VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE
);

-- Insert standard equipment types
INSERT INTO historian_meta.equipment_types (type_code, type_name, category, default_permissions) VALUES
('COMPRESSOR', 'Compressor', 'rotating', '{"can_view": true, "can_start": false, "can_stop": false, "can_change_setpoint": false}'),
('PUMP', 'Pump', 'rotating', '{"can_view": true, "can_start": false, "can_stop": false, "can_change_setpoint": false}'),
('VALVE', 'Valve', 'control', '{"can_view": true, "can_start": false, "can_stop": false, "can_change_setpoint": false}'),
('MOTOR', 'Motor', 'rotating', '{"can_view": true, "can_start": false, "can_stop": false}'),
('HEAT_EXCHANGER', 'Heat Exchanger', 'static', '{"can_view": true, "can_change_setpoint": false}'),
('TANK', 'Tank', 'static', '{"can_view": true}'),
('REACTOR', 'Reactor', 'static', '{"can_view": true, "can_change_setpoint": false}'),
('TURBINE', 'Turbine', 'rotating', '{"can_view": true, "can_start": false, "can_stop": false, "can_emergency_stop": false}'),
('FAN', 'Fan', 'rotating', '{"can_view": true, "can_start": false, "can_stop": false}'),
('CONVEYOR', 'Conveyor', 'rotating', '{"can_view": true, "can_start": false, "can_stop": false}')
ON CONFLICT (type_code) DO NOTHING;

-- =====================================================
-- 4. USER EQUIPMENT PERMISSIONS VIEW
-- =====================================================
CREATE OR REPLACE VIEW historian_meta.user_equipment_permissions AS
SELECT 
    u.id as user_id,
    u.username,
    r.id as role_id,
    r.name as role_name,
    r.is_admin,
    rep.equipment_id,
    e.equipment_name,
    e.equipment_type,
    e.plant,
    e.area,
    e.criticality,
    rep.can_view,
    rep.can_start,
    rep.can_stop,
    rep.can_change_mode,
    rep.can_change_setpoint,
    rep.can_emergency_stop,
    rep.can_override_interlock,
    rep.can_reset_alarm,
    rep.valid_from,
    rep.valid_until,
    CASE 
        WHEN rep.valid_from IS NOT NULL AND rep.valid_from > CURRENT_TIMESTAMP THEN FALSE
        WHEN rep.valid_until IS NOT NULL AND rep.valid_until < CURRENT_TIMESTAMP THEN FALSE
        ELSE TRUE
    END as is_currently_valid
FROM historian_meta.users u
JOIN historian_meta.roles r ON u.role_id = r.id
JOIN historian_meta.role_equipment_permissions rep ON r.id = rep.role_id
LEFT JOIN historian_meta.equipment_registry e ON rep.equipment_id = e.equipment_id
WHERE u.status = 'approved';

-- =====================================================
-- 5. EQUIPMENT PERMISSIONS SUMMARY VIEW
-- =====================================================
CREATE OR REPLACE VIEW historian_meta.equipment_permissions_summary AS
SELECT 
    e.equipment_id,
    e.equipment_name,
    e.equipment_type,
    e.plant,
    e.area,
    e.criticality,
    COUNT(DISTINCT r.id) as roles_with_access,
    COUNT(DISTINCT u.id) as users_with_access,
    MAX(CASE WHEN rep.can_start THEN 1 ELSE 0 END) = 1 as any_can_start,
    MAX(CASE WHEN rep.can_stop THEN 1 ELSE 0 END) = 1 as any_can_stop,
    MAX(CASE WHEN rep.can_emergency_stop THEN 1 ELSE 0 END) = 1 as any_can_emergency_stop
FROM historian_meta.equipment_registry e
LEFT JOIN historian_meta.role_equipment_permissions rep ON e.equipment_id = rep.equipment_id
LEFT JOIN historian_meta.roles r ON rep.role_id = r.id
LEFT JOIN historian_meta.users u ON r.id = u.role_id AND u.status = 'approved'
GROUP BY e.equipment_id, e.equipment_name, e.equipment_type, e.plant, e.area, e.criticality
ORDER BY e.criticality DESC, e.equipment_name;

-- =====================================================
-- 6. FUNCTION: CHECK USER EQUIPMENT PERMISSION
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.check_user_equipment_permission(
    p_user_id INTEGER,
    p_equipment_id VARCHAR(255),
    p_permission_type VARCHAR(50) -- 'view', 'start', 'stop', 'change_mode', 'change_setpoint', 'emergency_stop'
) RETURNS BOOLEAN AS $$
DECLARE
    v_is_admin BOOLEAN;
    v_has_permission BOOLEAN := FALSE;
BEGIN
    -- Check if user is admin (full access)
    SELECT r.is_admin INTO v_is_admin
    FROM historian_meta.users u
    JOIN historian_meta.roles r ON u.role_id = r.id
    WHERE u.id = p_user_id;
    
    IF v_is_admin THEN
        RETURN TRUE;
    END IF;
    
    -- Check specific equipment permission
    SELECT 
        CASE p_permission_type
            WHEN 'view' THEN rep.can_view
            WHEN 'start' THEN rep.can_start
            WHEN 'stop' THEN rep.can_stop
            WHEN 'change_mode' THEN rep.can_change_mode
            WHEN 'change_setpoint' THEN rep.can_change_setpoint
            WHEN 'emergency_stop' THEN rep.can_emergency_stop
            WHEN 'override_interlock' THEN rep.can_override_interlock
            WHEN 'reset_alarm' THEN rep.can_reset_alarm
            ELSE FALSE
        END INTO v_has_permission
    FROM historian_meta.users u
    JOIN historian_meta.role_equipment_permissions rep ON u.role_id = rep.role_id
    WHERE u.id = p_user_id 
      AND rep.equipment_id = p_equipment_id
      AND (rep.valid_from IS NULL OR rep.valid_from <= CURRENT_TIMESTAMP)
      AND (rep.valid_until IS NULL OR rep.valid_until >= CURRENT_TIMESTAMP);
    
    RETURN COALESCE(v_has_permission, FALSE);
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 7. FUNCTION: GET USER EQUIPMENT PERMISSIONS
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.get_user_equipment_permissions(
    p_user_id INTEGER,
    p_equipment_id VARCHAR(255) DEFAULT NULL
) RETURNS TABLE(
    equipment_id VARCHAR(255),
    equipment_name VARCHAR(255),
    equipment_type VARCHAR(100),
    can_view BOOLEAN,
    can_start BOOLEAN,
    can_stop BOOLEAN,
    can_change_mode BOOLEAN,
    can_change_setpoint BOOLEAN,
    can_emergency_stop BOOLEAN,
    can_override_interlock BOOLEAN,
    can_reset_alarm BOOLEAN
) AS $$
BEGIN
    -- If user is admin, return all equipment with full permissions
    IF EXISTS (
        SELECT 1 FROM historian_meta.users u
        JOIN historian_meta.roles r ON u.role_id = r.id
        WHERE u.id = p_user_id AND r.is_admin = TRUE
    ) THEN
        RETURN QUERY
        SELECT 
            e.equipment_id,
            e.equipment_name,
            e.equipment_type,
            TRUE::BOOLEAN as can_view,
            TRUE::BOOLEAN as can_start,
            TRUE::BOOLEAN as can_stop,
            TRUE::BOOLEAN as can_change_mode,
            TRUE::BOOLEAN as can_change_setpoint,
            TRUE::BOOLEAN as can_emergency_stop,
            TRUE::BOOLEAN as can_override_interlock,
            TRUE::BOOLEAN as can_reset_alarm
        FROM historian_meta.equipment_registry e
        WHERE (p_equipment_id IS NULL OR e.equipment_id = p_equipment_id)
          AND e.is_active = TRUE;
    ELSE
        -- Return user's specific permissions
        RETURN QUERY
        SELECT 
            rep.equipment_id,
            e.equipment_name,
            e.equipment_type,
            rep.can_view,
            rep.can_start,
            rep.can_stop,
            rep.can_change_mode,
            rep.can_change_setpoint,
            rep.can_emergency_stop,
            rep.can_override_interlock,
            rep.can_reset_alarm
        FROM historian_meta.users u
        JOIN historian_meta.role_equipment_permissions rep ON u.role_id = rep.role_id
        LEFT JOIN historian_meta.equipment_registry e ON rep.equipment_id = e.equipment_id
        WHERE u.id = p_user_id
          AND (p_equipment_id IS NULL OR rep.equipment_id = p_equipment_id)
          AND (rep.valid_from IS NULL OR rep.valid_from <= CURRENT_TIMESTAMP)
          AND (rep.valid_until IS NULL OR rep.valid_until >= CURRENT_TIMESTAMP);
    END IF;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 8. FUNCTION: ADD EQUIPMENT PERMISSION
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.add_equipment_permission(
    p_role_id INTEGER,
    p_equipment_id VARCHAR(255),
    p_can_view BOOLEAN DEFAULT TRUE,
    p_can_start BOOLEAN DEFAULT FALSE,
    p_can_stop BOOLEAN DEFAULT FALSE,
    p_can_change_mode BOOLEAN DEFAULT FALSE,
    p_can_change_setpoint BOOLEAN DEFAULT FALSE,
    p_can_emergency_stop BOOLEAN DEFAULT FALSE,
    p_can_override_interlock BOOLEAN DEFAULT FALSE,
    p_can_reset_alarm BOOLEAN DEFAULT FALSE,
    p_valid_from TIMESTAMP DEFAULT NULL,
    p_valid_until TIMESTAMP DEFAULT NULL
) RETURNS INTEGER AS $$
DECLARE
    v_permission_id INTEGER;
    v_equipment_type VARCHAR(100);
BEGIN
    -- Get equipment type
    SELECT equipment_type INTO v_equipment_type
    FROM historian_meta.equipment_registry
    WHERE equipment_id = p_equipment_id;
    
    -- Insert or update permission
    INSERT INTO historian_meta.role_equipment_permissions (
        role_id, equipment_id, equipment_type,
        can_view, can_start, can_stop, can_change_mode, can_change_setpoint,
        can_emergency_stop, can_override_interlock, can_reset_alarm,
        valid_from, valid_until
    ) VALUES (
        p_role_id, p_equipment_id, v_equipment_type,
        p_can_view, p_can_start, p_can_stop, p_can_change_mode, p_can_change_setpoint,
        p_can_emergency_stop, p_can_override_interlock, p_can_reset_alarm,
        p_valid_from, p_valid_until
    )
    ON CONFLICT (role_id, equipment_id) DO UPDATE SET
        can_view = EXCLUDED.can_view,
        can_start = EXCLUDED.can_start,
        can_stop = EXCLUDED.can_stop,
        can_change_mode = EXCLUDED.can_change_mode,
        can_change_setpoint = EXCLUDED.can_change_setpoint,
        can_emergency_stop = EXCLUDED.can_emergency_stop,
        can_override_interlock = EXCLUDED.can_override_interlock,
        can_reset_alarm = EXCLUDED.can_reset_alarm,
        valid_from = EXCLUDED.valid_from,
        valid_until = EXCLUDED.valid_until
    RETURNING id INTO v_permission_id;
    
    RETURN v_permission_id;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 9. TRIGGER: UPDATE EQUIPMENT UPDATED_AT
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.update_equipment_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_equipment_registry_updated_at
    BEFORE UPDATE ON historian_meta.equipment_registry
    FOR EACH ROW
    EXECUTE FUNCTION historian_meta.update_equipment_updated_at();

-- =====================================================
-- 10. GRANTS
-- =====================================================
GRANT SELECT, INSERT, UPDATE ON historian_meta.role_equipment_permissions TO opc_app_user;
GRANT SELECT ON historian_meta.equipment_registry TO opc_app_user;
GRANT SELECT ON historian_meta.equipment_types TO opc_app_user;
GRANT SELECT ON historian_meta.user_equipment_permissions TO opc_app_user;
GRANT SELECT ON historian_meta.equipment_permissions_summary TO opc_app_user;
GRANT USAGE ON SEQUENCE historian_meta.role_equipment_permissions_id_seq TO opc_app_user;
GRANT USAGE ON SEQUENCE historian_meta.equipment_registry_id_seq TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.check_user_equipment_permission TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.get_user_equipment_permissions TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.add_equipment_permission TO opc_app_user;

-- =====================================================
-- MIGRATION COMPLETE
-- =====================================================
