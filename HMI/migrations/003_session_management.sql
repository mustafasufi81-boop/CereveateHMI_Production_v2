-- =====================================================
-- Migration 003: Session Management System
-- Description: Implements session tracking and concurrent login prevention
-- Dependencies: 002_audit_logging.sql
-- =====================================================

-- =====================================================
-- 1. USER SESSIONS TABLE
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.user_sessions (
    id SERIAL PRIMARY KEY,
    
    -- User Reference
    user_id INTEGER NOT NULL REFERENCES historian_meta.users(id) ON DELETE CASCADE,
    
    -- Session Token
    session_token VARCHAR(255) UNIQUE NOT NULL,
    
    -- Network Information
    ip_address VARCHAR(50),
    user_agent TEXT,
    
    -- Timing
    login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    logout_time TIMESTAMP,
    
    -- Session State
    is_active BOOLEAN DEFAULT TRUE,
    forced_logout BOOLEAN DEFAULT FALSE,
    logout_reason VARCHAR(255), -- 'user_logout', 'idle_timeout', 'absolute_timeout', 'admin_terminate', 'concurrent_limit'
    
    -- Additional Context
    device_type VARCHAR(50), -- 'desktop', 'tablet', 'mobile'
    browser VARCHAR(100),
    os VARCHAR(100)
);

-- Create indexes
CREATE INDEX idx_sessions_user_id ON historian_meta.user_sessions(user_id);
CREATE INDEX idx_sessions_token ON historian_meta.user_sessions(session_token);
CREATE INDEX idx_sessions_active ON historian_meta.user_sessions(is_active, user_id);
CREATE INDEX idx_sessions_last_activity ON historian_meta.user_sessions(last_activity DESC);
CREATE INDEX idx_sessions_login_time ON historian_meta.user_sessions(login_time DESC);

-- =====================================================
-- 2. EXTEND ROLES TABLE WITH SESSION SETTINGS
-- =====================================================
ALTER TABLE historian_meta.roles 
ADD COLUMN IF NOT EXISTS max_concurrent_sessions INTEGER DEFAULT 1,
ADD COLUMN IF NOT EXISTS idle_timeout_minutes INTEGER DEFAULT 30,
ADD COLUMN IF NOT EXISTS absolute_timeout_minutes INTEGER DEFAULT 480; -- 8 hours

-- Update default roles with session limits
UPDATE historian_meta.roles SET 
    max_concurrent_sessions = 1,
    idle_timeout_minutes = 30,
    absolute_timeout_minutes = 480
WHERE max_concurrent_sessions IS NULL;

-- Admin role gets more lenient limits
UPDATE historian_meta.roles SET 
    max_concurrent_sessions = 3,
    idle_timeout_minutes = 60,
    absolute_timeout_minutes = 720
WHERE is_admin = TRUE;

-- =====================================================
-- 3. SESSION ACTIVITY LOG
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.session_activity_log (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES historian_meta.user_sessions(id) ON DELETE CASCADE,
    activity_type VARCHAR(50) NOT NULL, -- 'page_view', 'api_call', 'control_action'
    activity_details JSONB,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_session_activity_session ON historian_meta.session_activity_log(session_id, timestamp DESC);
CREATE INDEX idx_session_activity_timestamp ON historian_meta.session_activity_log(timestamp DESC);

-- =====================================================
-- 4. ACTIVE SESSIONS VIEW
-- =====================================================
CREATE OR REPLACE VIEW historian_meta.active_sessions AS
SELECT 
    s.id as session_id,
    s.user_id,
    u.username,
    r.name as role_name,
    s.ip_address,
    s.device_type,
    s.browser,
    s.login_time,
    s.last_activity,
    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - s.last_activity))/60 as idle_minutes,
    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - s.login_time))/60 as session_duration_minutes,
    r.idle_timeout_minutes,
    r.absolute_timeout_minutes,
    CASE 
        WHEN EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - s.last_activity))/60 > r.idle_timeout_minutes THEN TRUE
        ELSE FALSE
    END as is_idle_expired,
    CASE 
        WHEN EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - s.login_time))/60 > r.absolute_timeout_minutes THEN TRUE
        ELSE FALSE
    END as is_absolute_expired
FROM historian_meta.user_sessions s
JOIN historian_meta.users u ON s.user_id = u.id
LEFT JOIN historian_meta.roles r ON u.role_id = r.id
WHERE s.is_active = TRUE
ORDER BY s.last_activity DESC;

-- =====================================================
-- 5. USER CONCURRENT SESSIONS VIEW
-- =====================================================
CREATE OR REPLACE VIEW historian_meta.user_concurrent_sessions AS
SELECT 
    u.id as user_id,
    u.username,
    r.name as role_name,
    r.max_concurrent_sessions,
    COUNT(s.id) as active_session_count,
    CASE 
        WHEN COUNT(s.id) >= r.max_concurrent_sessions THEN TRUE
        ELSE FALSE
    END as is_at_limit
FROM historian_meta.users u
LEFT JOIN historian_meta.roles r ON u.role_id = r.id
LEFT JOIN historian_meta.user_sessions s ON u.id = s.user_id AND s.is_active = TRUE
GROUP BY u.id, u.username, r.name, r.max_concurrent_sessions
HAVING COUNT(s.id) > 0
ORDER BY active_session_count DESC;

-- =====================================================
-- 6. FUNCTION: CREATE SESSION
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.create_session(
    p_user_id INTEGER,
    p_session_token VARCHAR(255),
    p_ip_address VARCHAR(50),
    p_user_agent TEXT,
    p_device_type VARCHAR(50) DEFAULT NULL,
    p_browser VARCHAR(100) DEFAULT NULL,
    p_os VARCHAR(100) DEFAULT NULL
) RETURNS INTEGER AS $$
DECLARE
    v_session_id INTEGER;
    v_role_max_sessions INTEGER;
    v_current_session_count INTEGER;
    v_oldest_session_id INTEGER;
BEGIN
    -- Get role's max concurrent sessions
    SELECT r.max_concurrent_sessions INTO v_role_max_sessions
    FROM historian_meta.users u
    JOIN historian_meta.roles r ON u.role_id = r.id
    WHERE u.id = p_user_id;
    
    -- Count active sessions for this user
    SELECT COUNT(*) INTO v_current_session_count
    FROM historian_meta.user_sessions
    WHERE user_id = p_user_id AND is_active = TRUE;
    
    -- If at limit, terminate oldest session
    IF v_current_session_count >= v_role_max_sessions THEN
        SELECT id INTO v_oldest_session_id
        FROM historian_meta.user_sessions
        WHERE user_id = p_user_id AND is_active = TRUE
        ORDER BY last_activity ASC
        LIMIT 1;
        
        UPDATE historian_meta.user_sessions
        SET is_active = FALSE,
            forced_logout = TRUE,
            logout_time = CURRENT_TIMESTAMP,
            logout_reason = 'concurrent_limit'
        WHERE id = v_oldest_session_id;
    END IF;
    
    -- Create new session
    INSERT INTO historian_meta.user_sessions (
        user_id, session_token, ip_address, user_agent,
        device_type, browser, os
    ) VALUES (
        p_user_id, p_session_token, p_ip_address, p_user_agent,
        p_device_type, p_browser, p_os
    ) RETURNING id INTO v_session_id;
    
    RETURN v_session_id;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 7. FUNCTION: UPDATE SESSION ACTIVITY
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.update_session_activity(
    p_session_token VARCHAR(255),
    p_activity_type VARCHAR(50) DEFAULT 'api_call',
    p_activity_details JSONB DEFAULT NULL
) RETURNS BOOLEAN AS $$
DECLARE
    v_session_id INTEGER;
BEGIN
    -- Update last activity
    UPDATE historian_meta.user_sessions
    SET last_activity = CURRENT_TIMESTAMP
    WHERE session_token = p_session_token AND is_active = TRUE
    RETURNING id INTO v_session_id;
    
    IF v_session_id IS NULL THEN
        RETURN FALSE;
    END IF;
    
    -- Optionally log activity
    IF p_activity_details IS NOT NULL THEN
        INSERT INTO historian_meta.session_activity_log (session_id, activity_type, activity_details)
        VALUES (v_session_id, p_activity_type, p_activity_details);
    END IF;
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 8. FUNCTION: END SESSION
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.end_session(
    p_session_token VARCHAR(255),
    p_logout_reason VARCHAR(255) DEFAULT 'user_logout',
    p_forced BOOLEAN DEFAULT FALSE
) RETURNS BOOLEAN AS $$
BEGIN
    UPDATE historian_meta.user_sessions
    SET is_active = FALSE,
        forced_logout = p_forced,
        logout_time = CURRENT_TIMESTAMP,
        logout_reason = p_logout_reason
    WHERE session_token = p_session_token AND is_active = TRUE;
    
    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 9. FUNCTION: TERMINATE ALL USER SESSIONS
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.terminate_user_sessions(
    p_user_id INTEGER,
    p_logout_reason VARCHAR(255) DEFAULT 'admin_terminate'
) RETURNS INTEGER AS $$
DECLARE
    v_terminated_count INTEGER;
BEGIN
    UPDATE historian_meta.user_sessions
    SET is_active = FALSE,
        forced_logout = TRUE,
        logout_time = CURRENT_TIMESTAMP,
        logout_reason = p_logout_reason
    WHERE user_id = p_user_id AND is_active = TRUE;
    
    GET DIAGNOSTICS v_terminated_count = ROW_COUNT;
    RETURN v_terminated_count;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 10. FUNCTION: CLEANUP EXPIRED SESSIONS
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.cleanup_expired_sessions()
RETURNS TABLE(
    expired_type VARCHAR(20),
    expired_count INTEGER
) AS $$
DECLARE
    v_idle_count INTEGER := 0;
    v_absolute_count INTEGER := 0;
BEGIN
    -- Expire idle sessions
    UPDATE historian_meta.user_sessions s
    SET is_active = FALSE,
        forced_logout = TRUE,
        logout_time = CURRENT_TIMESTAMP,
        logout_reason = 'idle_timeout'
    FROM historian_meta.users u
    JOIN historian_meta.roles r ON u.role_id = r.id
    WHERE s.user_id = u.id
      AND s.is_active = TRUE
      AND EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - s.last_activity))/60 > r.idle_timeout_minutes;
    
    GET DIAGNOSTICS v_idle_count = ROW_COUNT;
    
    -- Expire sessions exceeding absolute timeout
    UPDATE historian_meta.user_sessions s
    SET is_active = FALSE,
        forced_logout = TRUE,
        logout_time = CURRENT_TIMESTAMP,
        logout_reason = 'absolute_timeout'
    FROM historian_meta.users u
    JOIN historian_meta.roles r ON u.role_id = r.id
    WHERE s.user_id = u.id
      AND s.is_active = TRUE
      AND EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - s.login_time))/60 > r.absolute_timeout_minutes;
    
    GET DIAGNOSTICS v_absolute_count = ROW_COUNT;
    
    -- Return results
    expired_type := 'idle';
    expired_count := v_idle_count;
    RETURN NEXT;
    
    expired_type := 'absolute';
    expired_count := v_absolute_count;
    RETURN NEXT;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 11. FUNCTION: VALIDATE SESSION
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.validate_session(
    p_session_token VARCHAR(255)
) RETURNS TABLE(
    is_valid BOOLEAN,
    user_id INTEGER,
    username VARCHAR(255),
    role_name VARCHAR(255),
    is_admin BOOLEAN,
    session_id INTEGER,
    idle_minutes NUMERIC,
    warning_message TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        s.is_active as is_valid,
        u.id as user_id,
        u.username,
        r.name as role_name,
        COALESCE(r.is_admin, FALSE) as is_admin,
        s.id as session_id,
        ROUND(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - s.last_activity))/60, 2) as idle_minutes,
        CASE 
            WHEN NOT s.is_active THEN 'Session expired or logged out'
            WHEN EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - s.last_activity))/60 > (r.idle_timeout_minutes * 0.8) 
                THEN 'Session will expire soon due to inactivity'
            WHEN EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - s.login_time))/60 > (r.absolute_timeout_minutes * 0.9)
                THEN 'Session will expire soon due to maximum duration'
            ELSE NULL
        END as warning_message
    FROM historian_meta.user_sessions s
    JOIN historian_meta.users u ON s.user_id = u.id
    LEFT JOIN historian_meta.roles r ON u.role_id = r.id
    WHERE s.session_token = p_session_token
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 12. SCHEDULED JOB: Auto-cleanup (PostgreSQL Cron Extension)
-- =====================================================
-- Note: Requires pg_cron extension
-- Uncomment the lines below if pg_cron is installed

-- Install pg_cron if not already
-- CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Schedule cleanup every 5 minutes (uncomment to enable)
-- SELECT cron.schedule('cleanup-expired-sessions', '*/5 * * * *', 
--     'SELECT historian_meta.cleanup_expired_sessions();'
-- );

-- =====================================================
-- 13. GRANTS
-- =====================================================
GRANT SELECT, INSERT, UPDATE ON historian_meta.user_sessions TO opc_app_user;
GRANT SELECT, INSERT ON historian_meta.session_activity_log TO opc_app_user;
GRANT SELECT ON historian_meta.active_sessions TO opc_app_user;
GRANT SELECT ON historian_meta.user_concurrent_sessions TO opc_app_user;
GRANT USAGE ON SEQUENCE historian_meta.user_sessions_id_seq TO opc_app_user;
GRANT USAGE ON SEQUENCE historian_meta.session_activity_log_id_seq TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.create_session TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.update_session_activity TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.end_session TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.terminate_user_sessions TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.cleanup_expired_sessions TO opc_app_user;
GRANT EXECUTE ON FUNCTION historian_meta.validate_session TO opc_app_user;

-- =====================================================
-- MIGRATION COMPLETE
-- =====================================================
