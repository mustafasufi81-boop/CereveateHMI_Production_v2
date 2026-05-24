-- =====================================================
-- Migration: Enable MFA for All Users
-- Description: Sets mfa_enabled = TRUE for all users
--              This enforces Multi-Factor Authentication
--              for enhanced security across the system
-- Date: 2026-01-26
-- =====================================================

-- Enable MFA for all existing users
UPDATE historian_meta.users
SET mfa_enabled = TRUE
WHERE mfa_enabled = FALSE;

-- Verify the update
SELECT 
    COUNT(*) as total_users,
    COUNT(*) FILTER (WHERE mfa_enabled = TRUE) as mfa_enabled_users,
    COUNT(*) FILTER (WHERE mfa_enabled = FALSE) as mfa_disabled_users
FROM historian_meta.users;

-- Show affected users
SELECT 
    id,
    username,
    mfa_enabled,
    status,
    created_at
FROM historian_meta.users
ORDER BY id;

-- =====================================================
-- NOTES:
-- =====================================================
-- 1. Users with MFA enabled will be required to:
--    - Verify using their 6-digit MFA token (from registration)
--    - OR answer security questions (if configured)
--
-- 2. Default MFA token for users without custom token: 123456
--
-- 3. This change is immediate and affects all future logins
--
-- 4. To disable MFA for a specific user:
--    UPDATE historian_meta.users SET mfa_enabled = FALSE WHERE username = 'username';
-- =====================================================
