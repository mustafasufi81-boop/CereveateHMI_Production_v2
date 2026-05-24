-- =====================================================
-- Migration 004b: Add Clear Alarm Permissions Columns
-- Description: Adds can_clear and requires_approval_to_clear columns
--              to role_alarm_permissions table
-- Dependencies: 004_industrial_rbac.sql (or 001_init_auth_rbac.sql)
-- =====================================================

-- =====================================================
-- ADD MISSING COLUMNS TO role_alarm_permissions
-- =====================================================

ALTER TABLE historian_meta.role_alarm_permissions
ADD COLUMN IF NOT EXISTS can_clear BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS requires_approval_to_clear BOOLEAN DEFAULT FALSE;

\echo ''
\echo '======================================================================'
\echo 'Migration 004b Complete: Added clear alarm permission columns'
\echo '======================================================================'
\echo ''

-- Verify columns exist
\echo 'role_alarm_permissions table structure:'
SELECT 
    column_name, 
    data_type, 
    is_nullable,
    column_default
FROM information_schema.columns 
WHERE table_schema = 'historian_meta' 
  AND table_name = 'role_alarm_permissions'
ORDER BY ordinal_position;

\echo ''

