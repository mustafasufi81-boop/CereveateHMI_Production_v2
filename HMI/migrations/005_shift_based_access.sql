-- =====================================================
-- Migration 005: Shift-Based Access Control
-- Description: Implements time-based access restrictions by shift
-- Dependencies: 004_equipment_permissions.sql
-- =====================================================

-- =====================================================
-- 1. SHIFTS TABLE
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.shifts (
    id SERIAL PRIMARY KEY,
    
    -- Shift Information
    shift_code VARCHAR(50) UNIQUE NOT NULL,
    shift_name VARCHAR(255) NOT NULL,
    description TEXT,
    
    -- Time Configuration
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    
    -- Days of Week (0=Sunday, 6=Saturday)
    days_of_week INTEGER[] NOT NULL,
    
    -- Shift Type
    shift_type VARCHAR(50) DEFAULT 'regular', -- 'regular', 'maintenance', 'weekend', 'holiday'
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX idx_shifts_code ON historian_meta.shifts(shift_code);
CREATE INDEX idx_shifts_active ON historian_meta.shifts(is_active);
CREATE INDEX idx_shifts_type ON historian_meta.shifts(shift_type);

-- Insert default shifts
INSERT INTO historian_meta.shifts (shift_code, shift_name, start_time, end_time, days_of_week, shift_type) VALUES
('SHIFT_A', 'Morning Shift (A)', '06:00:00', '14:00:00', ARRAY[1,2,3,4,5], 'regular'),
('SHIFT_B', 'Afternoon Shift (B)', '14:00:00', '22:00:00', ARRAY[1,2,3,4,5], 'regular'),
('SHIFT_C', 'Night Shift (C)', '22:00:00', '06:00:00', ARRAY[1,2,3,4,5], 'regular'),
('WEEKEND_DAY', 'Weekend Day Shift', '08:00:00', '20:00:00', ARRAY[0,6], 'weekend'),
('MAINTENANCE', 'Maintenance Window', '02:00:00', '06:00:00', ARRAY[0,1,2,3,4,5,6], 'maintenance')
ON CONFLICT (shift_code) DO NOTHING;

-- =====================================================
-- 2. ROLE SHIFT ASSIGNMENTS
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.role_shift_assignments (
    id SERIAL PRIMARY KEY,
    
    -- Role and Shift
    role_id INTEGER NOT NULL REFERENCES historian_meta.roles(id) ON DELETE CASCADE,
    shift_id INTEGER NOT NULL REFERENCES historian_meta.shifts(id) ON DELETE CASCADE,
    
    -- Assignment Details
    is_primary_shift BOOLEAN DEFAULT TRUE,
    can_access_outside_shift BOOLEAN DEFAULT FALSE, -- Allow access outside assigned shift with warning
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(role_id, shift_id)
);

-- Create indexes
CREATE INDEX idx_role_shift_role ON historian_meta.role_shift_assignments(role_id);
CREATE INDEX idx_role_shift_shift ON historian_meta.role_shift_assignments(shift_id);

-- =====================================================
-- 3. USER SHIFT ASSIGNMENTS (Individual Level)
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.user_shift_assignments (
    id SERIAL PRIMARY KEY,
    
    -- User and Shift
    user_id INTEGER NOT NULL REFERENCES historian_meta.users(id) ON DELETE CASCADE,
    shift_id INTEGER NOT NULL REFERENCES historian_meta.shifts(id) ON DELETE CASCADE,
    
    -- Date Range (optional - for temporary assignments)
    valid_from DATE DEFAULT CURRENT_DATE,
    valid_until DATE DEFAULT NULL,
    
    -- Assignment Details
    is_primary_shift BOOLEAN DEFAULT TRUE,
    override_role_restriction BOOLEAN DEFAULT FALSE, -- Allow user to work different shift than role
    
    -- Metadata
    assigned_by INTEGER REFERENCES historian_meta.users(id),
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    
    UNIQUE(user_id, shift_id, valid_from)
);

-- Create indexes
CREATE INDEX idx_user_shift_user ON historian_meta.user_shift_assignments(user_id);
CREATE INDEX idx_user_shift_shift ON historian_meta.user_shift_assignments(shift_id);
CREATE INDEX idx_user_shift_validity ON historian_meta.user_shift_assignments(valid_from, valid_until);

-- =====================================================
-- 4. EXTEND EXISTING TABLES WITH SHIFT RESTRICTIONS
-- =====================================================

-- Add shift restriction to tag permissions
ALTER TABLE historian_meta.role_tag_permissions 
ADD COLUMN IF NOT EXISTS shift_restriction VARCHAR(50) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS allowed_days INTEGER[] DEFAULT NULL,
ADD COLUMN IF NOT EXISTS allowed_time_start TIME DEFAULT NULL,
ADD COLUMN IF NOT EXISTS allowed_time_end TIME DEFAULT NULL;

-- Add shift restriction to equipment permissions
ALTER TABLE historian_meta.role_equipment_permissions
ADD COLUMN IF NOT EXISTS shift_restriction VARCHAR(50) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS allowed_days INTEGER[] DEFAULT NULL,
ADD COLUMN IF NOT EXISTS allowed_time_start TIME DEFAULT NULL,
ADD COLUMN IF NOT EXISTS allowed_time_end TIME DEFAULT NULL;

-- Add shift-aware session settings to roles
ALTER TABLE historian_meta.roles
ADD COLUMN IF NOT EXISTS enforce_shift_restrictions BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS auto_logout_at_shift_end BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS shift_end_warning_minutes INTEGER DEFAULT 15;

-- =====================================================
-- 5. SHIFT HANDOVER NOTES
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.shift_handover_notes (
    id SERIAL PRIMARY KEY,
    
    -- Shift Information
    from_shift_id INTEGER REFERENCES historian_meta.shifts(id),
    to_shift_id INTEGER REFERENCES historian_meta.shifts(id),
    handover_date DATE NOT NULL,
    
    -- User Information
    created_by INTEGER NOT NULL REFERENCES historian_meta.users(id),
    acknowledged_by INTEGER REFERENCES historian_meta.users(id),
    
    -- Content
    note_category VARCHAR(50), -- 'safety', 'operations', 'maintenance', 'alarm', 'general'
    priority VARCHAR(20) DEFAULT 'normal', -- 'low', 'normal', 'high', 'urgent'
    subject VARCHAR(255),
    content TEXT NOT NULL,
    
    -- Status
    is_acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_at TIMESTAMP,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX idx_shift_handover_date ON historian_meta.shift_handover_notes(handover_date DESC);
CREATE INDEX idx_shift_handover_from ON historian_meta.shift_handover_notes(from_shift_id);
CREATE INDEX idx_shift_handover_to ON historian_meta.shift_handover_notes(to_shift_id);
CREATE INDEX idx_shift_handover_ack ON historian_meta.shift_handover_notes(is_acknowledged);
CREATE INDEX idx_shift_handover_priority ON historian_meta.shift_handover_notes(priority);

-- =====================================================
-- 6. CURRENT SHIFT VIEW
-- =====================================================
CREATE OR REPLACE VIEW historian_meta.current_active_shifts AS
SELECT 
    s.id,
    s.shift_code,
    s.shift_name,
    s.start_time,
    s.end_time,
    s.shift_type,
    CASE 
        WHEN s.start_time < s.end_time THEN
            CURRENT_TIME BETWEEN s.start_time AND s.end_time
        ELSE -- Shift crosses midnight
            CURRENT_TIME >= s.start_time OR CURRENT_TIME <= s.end_time
    END as is_currently_active,
    EXTRACT(DOW FROM CURRENT_TIMESTAMP)::INTEGER = ANY(s.days_of_week) as is_valid_day
FROM historian_meta.shifts s
WHERE s.is_active = TRUE;

-- =====================================================
-- 7. USER CURRENT SHIFT VIEW
-- =====================================================
CREATE OR REPLACE VIEW historian_meta.user_current_shift_status AS
SELECT 
    u.id as user_id,
    u.username,
    r.name as role_name,
    s.shift_code,
    s.shift_name,
    s.start_time,
    s.end_time,
    CASE 
        WHEN s.start_time < s.end_time THEN
            CURRENT_TIME BETWEEN s.start_time AND s.end_time
        ELSE
            CURRENT_TIME >= s.start_time OR CURRENT_TIME <= s.end_time
    END as is_in_shift,
    r.enforce_shift_restrictions,
    usa.is_primary_shift,
    usa.override_role_restriction
FROM historian_meta.users u
LEFT JOIN historian_meta.roles r ON u.role_id = r.id
LEFT JOIN historian_meta.user_shift_assignments usa ON u.id = usa.user_id
    AND (usa.valid_from IS NULL OR usa.valid_from <= CURRENT_DATE)
    AND (usa.valid_until IS NULL OR usa.valid_until >= CURRENT_DATE)
LEFT JOIN historian_meta.shifts s ON usa.shift_id = s.id
WHERE u.status = 'approved' AND s.is_active = TRUE
    AND EXTRACT(DOW FROM CURRENT_TIMESTAMP)::INTEGER = ANY(s.days_of_week);

-- =====================================================
-- 8. FUNCTION: GET CURRENT SHIFT
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.get_current_shift(
    p_check_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) RETURNS TABLE(
    shift_id INTEGER,
    shift_code VARCHAR(50),
    shift_name VARCHAR(255),
    start_time TIME,
    end_time TIME,
    shift_type VARCHAR(50)
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        s.id,
        s.shift_code,
        s.shift_name,
        s.start_time,
        s.end_time,
        s.shift_type
    FROM historian_meta.shifts s
    WHERE s.is_active = TRUE
      AND EXTRACT(DOW FROM p_check_time)::INTEGER = ANY(s.days_of_week)
      AND (
          CASE 
              WHEN s.start_time < s.end_time THEN
                  (p_check_time::TIME BETWEEN s.start_time AND s.end_time)
              ELSE -- Shift crosses midnight
                  (p_check_time::TIME >= s.start_time OR p_check_time::TIME <= s.end_time)
          END
      )
    ORDER BY shift_type = 'regular' DESC, s.shift_code
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 9. FUNCTION: CHECK USER SHIFT ACCESS
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.check_user_shift_access(
    p_user_id INTEGER,
    p_check_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) RETURNS TABLE(
    has_access BOOLEAN,
    current_shift_code VARCHAR(50),
    user_assigned_shift VARCHAR(50),
    is_in_assigned_shift BOOLEAN,
    warning_message TEXT,
    minutes_until_shift_end INTEGER
) AS $$
DECLARE
    v_role_enforces_shift BOOLEAN;
    v_can_access_outside BOOLEAN;
    v_user_shift_id INTEGER;
    v_current_shift_id INTEGER;
    v_current_shift_code VARCHAR(50);
    v_user_shift_code VARCHAR(50);
    v_shift_end_time TIME;
    v_minutes_remaining INTEGER;
BEGIN
    -- Get role shift enforcement setting
    SELECT r.enforce_shift_restrictions INTO v_role_enforces_shift
    FROM historian_meta.users u
    JOIN historian_meta.roles r ON u.role_id = r.id
    WHERE u.id = p_user_id;
    
    -- If shift restrictions not enforced, allow access
    IF NOT COALESCE(v_role_enforces_shift, FALSE) THEN
        has_access := TRUE;
        warning_message := NULL;
        RETURN NEXT;
        RETURN;
    END IF;
    
    -- Get current shift
    SELECT s.id, s.shift_code, s.end_time 
    INTO v_current_shift_id, v_current_shift_code, v_shift_end_time
    FROM historian_meta.get_current_shift(p_check_time) s;
    
    -- Get user's assigned shift(s)
    SELECT usa.shift_id, s.shift_code, usa.can_access_outside_shift
    INTO v_user_shift_id, v_user_shift_code, v_can_access_outside
    FROM historian_meta.user_shift_assignments usa
    JOIN historian_meta.shifts s ON usa.shift_id = s.id
    WHERE usa.user_id = p_user_id
      AND (usa.valid_from IS NULL OR usa.valid_from <= p_check_time::DATE)
      AND (usa.valid_until IS NULL OR usa.valid_until >= p_check_time::DATE)
      AND usa.is_primary_shift = TRUE
    LIMIT 1;
    
    -- Calculate minutes until shift end
    IF v_shift_end_time IS NOT NULL THEN
        v_minutes_remaining := EXTRACT(EPOCH FROM (v_shift_end_time - p_check_time::TIME))/60;
        IF v_minutes_remaining < 0 THEN
            v_minutes_remaining := v_minutes_remaining + 1440; -- Add 24 hours if negative (crossed midnight)
        END IF;
    END IF;
    
    -- Determine access
    IF v_user_shift_id = v_current_shift_id THEN
        -- User is in their assigned shift
        has_access := TRUE;
        is_in_assigned_shift := TRUE;
        
        -- Check if nearing shift end
        IF v_minutes_remaining <= 15 THEN
            warning_message := 'Your shift ends in ' || v_minutes_remaining || ' minutes';
        END IF;
    ELSIF v_can_access_outside THEN
        -- User can access outside shift with warning
        has_access := TRUE;
        is_in_assigned_shift := FALSE;
        warning_message := 'You are accessing outside your assigned shift (' || v_user_shift_code || ')';
    ELSE
        -- Access denied
        has_access := FALSE;
        is_in_assigned_shift := FALSE;
        warning_message := 'Access denied: You are not assigned to the current shift';
    END IF;
    
    current_shift_code := v_current_shift_code;
    user_assigned_shift := v_user_shift_code;
    minutes_until_shift_end := v_minutes_remaining;
    
    RETURN NEXT;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 10. FUNCTION: ADD SHIFT HANDOVER NOTE
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.add_shift_handover_note(
    p_from_shift_id INTEGER,
    p_to_shift_id INTEGER,
    p_created_by INTEGER,
    p_category VARCHAR(50),
    p_priority VARCHAR(20),
    p_subject VARCHAR(255),
    p_content TEXT
) RETURNS INTEGER AS $$
DECLARE
    v_note_id INTEGER;
BEGIN
    INSERT INTO historian_meta.shift_handover_notes (
        from_shift_id, to_shift_id, handover_date,
        created_by, note_category, priority, subject, content
    ) VALUES (
        p_from_shift_id, p_to_shift_id, CURRENT_DATE,
        p_created_by, p_category, p_priority, p_subject, p_content
    ) RETURNING id INTO v_note_id;
    
    RETURN v_note_id;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 11. FUNCTION: ACKNOWLEDGE HANDOVER NOTE
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.acknowledge_handover_note(
    p_note_id INTEGER,
    p_acknowledged_by INTEGER
) RETURNS BOOLEAN AS $$
BEGIN
    UPDATE historian_meta.shift_handover_notes
    SET is_acknowledged = TRUE,
        acknowledged_by = p_acknowledged_by,
        acknowledged_at = CURRENT_TIMESTAMP
    WHERE id = p_note_id;
    
    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 12. TRIGGER: UPDATE SHIFT UPDATED_AT
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.update_shift_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_shifts_updated_at
    BEFORE UPDATE ON historian_meta.shifts
    FOR EACH ROW
    EXECUTE FUNCTION historian_meta.update_shift_updated_at();

CREATE TRIGGER update_shift_handover_updated_at
    BEFORE UPDATE ON historian_meta.shift_handover_notes
    FOR EACH ROW
    EXECUTE FUNCTION historian_meta.update_shift_updated_at();

-- =====================================================
-- 13. GRANTS
-- =====================================================
GRANT SELECT, INSERT, UPDATE ON historian_meta.shifts TO opc_app_user;
GRANT SELECT, INSERT, UPDATE ON historian_meta.role_shift_assignments TO opc_app_user;
GRANT SELECT, INSERT, UPDATE ON historian_meta.user_shift_assignments TO opc_app_user;
GRANT SELECT, INSERT, UPDATE ON historian_meta.shift_handover_notes TO opc_app_user;
GRANT SELECT ON historian_meta.current_active_shifts TO opc_app_user;
GRANT SELECT ON historian_meta.user_current_shift_status TO opc_app_user;
GRANT USAGE ON SEQUENCE historian_meta.shifts_id_seq TO opc_app_user;
GRANT USAGE ON SEQUENCE historian_meta.role_shift_assignments_id_seq TO opc_app_user;
GRANT USAGE ON SEQUENCE historian_meta.user_shift_assignments_id_seq TO opc_app_user;
GRANT USAGE ON SEQUENCE historian_meta.shift_handover_notes_id_seq TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.get_current_shift TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.check_user_shift_access TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.add_shift_handover_note TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.acknowledge_handover_note TO opc_app_user;

-- =====================================================
-- MIGRATION COMPLETE
-- =====================================================
