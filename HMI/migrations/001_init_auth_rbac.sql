-- =====================================================
-- Migration: Initialize Authentication and RBAC System
-- Description: Creates all tables needed for user authentication,
--              role-based access control, and permissions management
-- =====================================================

-- Create schema if not exists
CREATE SCHEMA IF NOT EXISTS historian_meta;

-- =====================================================
-- 1. USERS TABLE
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    
    -- MFA Fields
    mfa_enabled BOOLEAN DEFAULT FALSE,
    mfa_secret TEXT,
    
    -- Security Questions (JSON array of {question, answer_hash})
    security_questions JSONB,
    
    -- Backup Key for Password Recovery
    backup_key_hash TEXT,
    backup_key_expiry TIMESTAMP,
    
    -- Account Security
    failed_login_attempts INTEGER DEFAULT 0,
    lockout_until TIMESTAMP,
    
    -- User Status & Role
    status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'approved', 'revoked'
    role_id INTEGER,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index on username for faster lookups
CREATE INDEX IF NOT EXISTS idx_users_username ON historian_meta.users(username);
CREATE INDEX IF NOT EXISTS idx_users_status ON historian_meta.users(status);
CREATE INDEX IF NOT EXISTS idx_users_role_id ON historian_meta.users(role_id);

-- =====================================================
-- 2. ROLES TABLE
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.roles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index on name
CREATE INDEX IF NOT EXISTS idx_roles_name ON historian_meta.roles(name);

-- =====================================================
-- 3. ROLE TAG PERMISSIONS (Plant/Area Level)
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.role_tag_permissions (
    id SERIAL PRIMARY KEY,
    role_id INTEGER NOT NULL REFERENCES historian_meta.roles(id) ON DELETE CASCADE,
    plant VARCHAR(255) NOT NULL,
    area VARCHAR(255) NOT NULL,
    can_view BOOLEAN DEFAULT TRUE,
    can_write BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Ensure unique combination of role, plant, and area
    UNIQUE(role_id, plant, area)
);

-- Create indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_role_tag_perms_role ON historian_meta.role_tag_permissions(role_id);
CREATE INDEX IF NOT EXISTS idx_role_tag_perms_plant_area ON historian_meta.role_tag_permissions(plant, area);

-- =====================================================
-- 4. ROLE SPECIFIC TAG PERMISSIONS (Individual Tags)
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.role_specific_tag_permissions (
    id SERIAL PRIMARY KEY,
    role_id INTEGER NOT NULL REFERENCES historian_meta.roles(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL,
    can_view BOOLEAN DEFAULT TRUE,
    can_write BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Ensure unique combination of role and tag
    UNIQUE(role_id, tag_id)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_role_specific_tag_perms_role ON historian_meta.role_specific_tag_permissions(role_id);
CREATE INDEX IF NOT EXISTS idx_role_specific_tag_perms_tag ON historian_meta.role_specific_tag_permissions(tag_id);

-- =====================================================
-- 5. ROLE ALARM PERMISSIONS
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.role_alarm_permissions (
    id SERIAL PRIMARY KEY,
    role_id INTEGER NOT NULL REFERENCES historian_meta.roles(id) ON DELETE CASCADE,
    alarm_category VARCHAR(255) NOT NULL,
    can_view BOOLEAN DEFAULT TRUE,
    can_acknowledge BOOLEAN DEFAULT FALSE,
    can_silence BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Ensure unique combination of role and alarm category
    UNIQUE(role_id, alarm_category)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_role_alarm_perms_role ON historian_meta.role_alarm_permissions(role_id);
CREATE INDEX IF NOT EXISTS idx_role_alarm_perms_category ON historian_meta.role_alarm_permissions(alarm_category);

-- =====================================================
-- 6. SYSTEM ALERTS TABLE
-- =====================================================
CREATE TABLE IF NOT EXISTS historian_meta.system_alerts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES historian_meta.users(id) ON DELETE SET NULL,
    alert_type VARCHAR(100) NOT NULL, -- 'ACCOUNT_LOCKOUT', 'PASSWORD_RESET', etc.
    message TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_system_alerts_user ON historian_meta.system_alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_system_alerts_type ON historian_meta.system_alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_system_alerts_created ON historian_meta.system_alerts(created_at DESC);

-- =====================================================
-- 7. ADD FOREIGN KEY CONSTRAINT FOR USERS.ROLE_ID
-- =====================================================
-- Add foreign key constraint if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'users_role_id_fkey'
    ) THEN
        ALTER TABLE historian_meta.users 
        ADD CONSTRAINT users_role_id_fkey 
        FOREIGN KEY (role_id) REFERENCES historian_meta.roles(id) ON DELETE SET NULL;
    END IF;
END $$;

-- =====================================================
-- 8. INSERT DEFAULT ROLES
-- =====================================================
-- Insert default admin role if it doesn't exist
INSERT INTO historian_meta.roles (name, description, is_admin)
VALUES ('Admin', 'Full system administrator with all permissions', TRUE)
ON CONFLICT (name) DO NOTHING;

-- Insert default operator role if it doesn't exist
INSERT INTO historian_meta.roles (name, description, is_admin)
VALUES ('Operator', 'Standard operator with limited permissions', FALSE)
ON CONFLICT (name) DO NOTHING;

-- Insert default viewer role if it doesn't exist
INSERT INTO historian_meta.roles (name, description, is_admin)
VALUES ('Viewer', 'Read-only access to system data', FALSE)
ON CONFLICT (name) DO NOTHING;

-- =====================================================
-- 9. CREATE UPDATED_AT TRIGGER FUNCTION
-- =====================================================
CREATE OR REPLACE FUNCTION historian_meta.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to users table
DROP TRIGGER IF EXISTS update_users_updated_at ON historian_meta.users;
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON historian_meta.users
    FOR EACH ROW
    EXECUTE FUNCTION historian_meta.update_updated_at_column();

-- Apply trigger to roles table
DROP TRIGGER IF EXISTS update_roles_updated_at ON historian_meta.roles;
CREATE TRIGGER update_roles_updated_at
    BEFORE UPDATE ON historian_meta.roles
    FOR EACH ROW
    EXECUTE FUNCTION historian_meta.update_updated_at_column();

-- =====================================================
-- MIGRATION COMPLETE
-- =====================================================
-- This migration creates the complete authentication and RBAC system
-- including users, roles, permissions for tags and alarms, and system alerts.
