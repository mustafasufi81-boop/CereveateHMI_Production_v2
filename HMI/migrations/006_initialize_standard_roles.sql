-- =====================================================
-- Migration 006: Initialize Standard Roles and Alarm Permissions
-- Description: Creates OPERATOR, SUPERVISOR, SAFETY_OFFICER roles and 
--              configures role_alarm_permissions for each
-- Dependencies: 005_industrial_rbac_config.sql
-- =====================================================

-- =====================================================
-- PART 1: CREATE STANDARD ROLES (if they don't exist)
-- =====================================================

INSERT INTO historian_meta.roles (name, description, is_admin)
VALUES
  ('OPERATOR', 'Operator with acknowledge-only permissions', FALSE),
  ('SUPERVISOR', 'Supervisor with approval authority for major operations', FALSE),
  ('SAFETY_OFFICER', 'Safety system certified officer with safety-critical permissions', FALSE),
  ('ADMIN', 'Full system administrator with unrestricted access', TRUE)
ON CONFLICT (name) DO NOTHING;

-- NOTE: The 'Admin', 'Operator', 'Viewer' roles from migration 001 should still exist for legacy support
-- But we recommend using the uppercase role names above for new configurations

-- =====================================================
-- PART 2: CONFIGURE ALARM PERMISSIONS
-- =====================================================

-- OPERATOR: Can acknowledge alarms only
INSERT INTO historian_meta.role_alarm_permissions 
  (role_id, alarm_category, can_view, can_acknowledge, can_silence, can_clear, requires_approval_to_clear, created_at)
SELECT r.id, arg, TRUE, TRUE, FALSE, FALSE, FALSE, NOW()
FROM historian_meta.roles r, (
  VALUES ('*'), ('PRESSURE'), ('TEMPERATURE'), ('SPEED'), ('FLOW'), ('VIBRATION')
) AS categories(arg)
WHERE r.name = 'OPERATOR'
ON CONFLICT (role_id, alarm_category) DO UPDATE
SET can_view = TRUE, can_acknowledge = TRUE, can_silence = FALSE, can_clear = FALSE, requires_approval_to_clear = FALSE;

-- SUPERVISOR: Can acknowledge and clear alarms (clearing requires approval)
INSERT INTO historian_meta.role_alarm_permissions 
  (role_id, alarm_category, can_view, can_acknowledge, can_silence, can_clear, requires_approval_to_clear, created_at)
SELECT r.id, arg, TRUE, TRUE, FALSE, TRUE, TRUE, NOW()
FROM historian_meta.roles r, (
  VALUES ('*'), ('PRESSURE'), ('TEMPERATURE'), ('SPEED'), ('FLOW'), ('VIBRATION')
) AS categories(arg)
WHERE r.name = 'SUPERVISOR'
ON CONFLICT (role_id, alarm_category) DO UPDATE
SET can_view = TRUE, can_acknowledge = TRUE, can_silence = FALSE, can_clear = TRUE, requires_approval_to_clear = TRUE;

-- SAFETY_OFFICER: Full alarm control (no approval needed due to certification)
INSERT INTO historian_meta.role_alarm_permissions 
  (role_id, alarm_category, can_view, can_acknowledge, can_silence, can_clear, requires_approval_to_clear, created_at)
SELECT r.id, arg, TRUE, TRUE, FALSE, TRUE, FALSE, NOW()
FROM historian_meta.roles r, (
  VALUES ('*'), ('PRESSURE'), ('TEMPERATURE'), ('SPEED'), ('FLOW'), ('VIBRATION')
) AS categories(arg)
WHERE r.name = 'SAFETY_OFFICER'
ON CONFLICT (role_id, alarm_category) DO UPDATE
SET can_view = TRUE, can_acknowledge = TRUE, can_silence = FALSE, can_clear = TRUE, requires_approval_to_clear = FALSE;

-- ADMIN: Full control (via is_admin flag, so we don't need explicit permission)
-- The RBAC service checks is_admin first and grants full access
-- Still, we add it for consistency in role_alarm_permissions table
INSERT INTO historian_meta.role_alarm_permissions 
  (role_id, alarm_category, can_view, can_acknowledge, can_silence, can_clear, requires_approval_to_clear, created_at)
SELECT r.id, arg, TRUE, TRUE, TRUE, TRUE, FALSE, NOW()
FROM historian_meta.roles r, (
  VALUES ('*'), ('PRESSURE'), ('TEMPERATURE'), ('SPEED'), ('FLOW'), ('VIBRATION')
) AS categories(arg)
WHERE r.name = 'ADMIN'
ON CONFLICT (role_id, alarm_category) DO UPDATE
SET can_view = TRUE, can_acknowledge = TRUE, can_silence = TRUE, can_clear = TRUE, requires_approval_to_clear = FALSE;

-- =====================================================
-- PART 3: CONFIGURE TRIP PERMISSIONS (for completeness)
-- =====================================================

-- OPERATOR: Can acknowledge and clear non-safety trips (requires approval)
INSERT INTO historian_meta.role_trip_permissions 
  (role_id, trip_category, equipment_id, can_view, can_clear_non_safety, can_clear_safety, can_override, requires_approval_to_clear, requires_approval_to_override, requires_2fa_to_override)
SELECT r.id, 'NON_SAFETY', NULL, TRUE, FALSE, FALSE, TRUE, FALSE, TRUE, FALSE
FROM historian_meta.roles r WHERE r.name = 'OPERATOR'
ON CONFLICT (role_id, trip_category, equipment_id) DO UPDATE
SET can_view = TRUE, can_clear_non_safety = FALSE, can_override = TRUE, requires_approval_to_override = TRUE;

-- SUPERVISOR: Can clear non-safety trips (requires approval), acknowledge and clear safety trips
INSERT INTO historian_meta.role_trip_permissions 
  (role_id, trip_category, equipment_id, can_view, can_clear_non_safety, can_clear_safety, can_override, requires_approval_to_clear, requires_approval_to_override, requires_2fa_to_override)
SELECT r.id, trip_type, NULL, TRUE, 
  CASE WHEN trip_type = 'NON_SAFETY' THEN TRUE ELSE FALSE END,
  CASE WHEN trip_type = 'SAFETY' THEN TRUE ELSE FALSE END,
  FALSE, TRUE, TRUE, TRUE
FROM historian_meta.roles r,
(VALUES ('NON_SAFETY'), ('SAFETY')) AS categories(trip_type)
WHERE r.name = 'SUPERVISOR'
ON CONFLICT (role_id, trip_category, equipment_id) DO UPDATE
SET can_view = TRUE, can_clear_non_safety = TRUE, can_clear_safety = TRUE, requires_approval_to_clear = TRUE;

-- SAFETY_OFFICER: Can clear all trips with 2FA requirement
INSERT INTO historian_meta.role_trip_permissions 
  (role_id, trip_category, equipment_id, can_view, can_clear_non_safety, can_clear_safety, can_override, requires_approval_to_clear, requires_approval_to_override, requires_2fa_to_override)
SELECT r.id, trip_type, NULL, TRUE, 
  CASE WHEN trip_type = 'NON_SAFETY' THEN TRUE ELSE FALSE END,
  CASE WHEN trip_type = 'SAFETY' THEN TRUE ELSE FALSE END,
  TRUE, TRUE, FALSE, TRUE
FROM historian_meta.roles r,
(VALUES ('NON_SAFETY'), ('SAFETY')) AS categories(trip_type)
WHERE r.name = 'SAFETY_OFFICER'
ON CONFLICT (role_id, trip_category, equipment_id) DO UPDATE
SET can_view = TRUE, can_clear_non_safety = TRUE, can_clear_safety = TRUE, can_override = TRUE, requires_2fa_to_override = TRUE;

-- ADMIN: Unrestricted
INSERT INTO historian_meta.role_trip_permissions 
  (role_id, trip_category, equipment_id, can_view, can_clear_non_safety, can_clear_safety, can_override, requires_approval_to_clear, requires_approval_to_override, requires_2fa_to_override)
SELECT r.id, trip_type, NULL, TRUE, TRUE, TRUE, TRUE, FALSE, FALSE, FALSE
FROM historian_meta.roles r,
(VALUES ('NON_SAFETY'), ('SAFETY')) AS categories(trip_type)
WHERE r.name = 'ADMIN'
ON CONFLICT (role_id, trip_category, equipment_id) DO UPDATE
SET can_view = TRUE, can_clear_non_safety = TRUE, can_clear_safety = TRUE, can_override = TRUE;

-- =====================================================
-- PART 4: CONFIGURE INTERLOCK PERMISSIONS (for completeness)
-- =====================================================

-- OPERATOR: View only
INSERT INTO historian_meta.role_interlock_permissions 
  (role_id, interlock_category, equipment_id, can_view, can_disable_non_safety, can_disable_safety, can_override, requires_approval_to_disable, requires_approval_to_override, requires_2fa_to_override)
SELECT r.id, lock_type, NULL, TRUE, FALSE, FALSE, FALSE, FALSE, FALSE, FALSE
FROM historian_meta.roles r,
(VALUES ('NON_SAFETY'), ('SAFETY')) AS categories(lock_type)
WHERE r.name = 'OPERATOR'
ON CONFLICT (role_id, interlock_category, equipment_id) DO UPDATE
SET can_view = TRUE, can_disable_non_safety = FALSE, can_disable_safety = FALSE, can_override = FALSE;

-- SUPERVISOR: Can disable non-safety interlocks (requires approval)
INSERT INTO historian_meta.role_interlock_permissions 
  (role_id, interlock_category, equipment_id, can_view, can_disable_non_safety, can_disable_safety, can_override, requires_approval_to_disable, requires_approval_to_override, requires_2fa_to_override)
SELECT r.id, lock_type, NULL, TRUE,
  CASE WHEN lock_type = 'NON_SAFETY' THEN TRUE ELSE FALSE END,
  FALSE, FALSE, TRUE, FALSE, FALSE
FROM historian_meta.roles r,
(VALUES ('NON_SAFETY'), ('SAFETY')) AS categories(lock_type)
WHERE r.name = 'SUPERVISOR'
ON CONFLICT (role_id, interlock_category, equipment_id) DO UPDATE
SET can_view = TRUE, can_disable_non_safety = TRUE, can_disable_safety = FALSE, requires_approval_to_disable = TRUE;

-- SAFETY_OFFICER: Full control with 2FA
INSERT INTO historian_meta.role_interlock_permissions 
  (role_id, interlock_category, equipment_id, can_view, can_disable_non_safety, can_disable_safety, can_override, requires_approval_to_disable, requires_approval_to_override, requires_2fa_to_override)
SELECT r.id, lock_type, NULL, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE
FROM historian_meta.roles r,
(VALUES ('NON_SAFETY'), ('SAFETY')) AS categories(lock_type)
WHERE r.name = 'SAFETY_OFFICER'
ON CONFLICT (role_id, interlock_category, equipment_id) DO UPDATE
SET can_view = TRUE, can_disable_non_safety = TRUE, can_disable_safety = TRUE, can_override = TRUE, requires_2fa_to_override = TRUE;

-- ADMIN: Unrestricted
INSERT INTO historian_meta.role_interlock_permissions 
  (role_id, interlock_category, equipment_id, can_view, can_disable_non_safety, can_disable_safety, can_override, requires_approval_to_disable, requires_approval_to_override, requires_2fa_to_override)
SELECT r.id, lock_type, NULL, TRUE, TRUE, TRUE, TRUE, FALSE, FALSE, FALSE
FROM historian_meta.roles r,
(VALUES ('NON_SAFETY'), ('SAFETY')) AS categories(lock_type)
WHERE r.name = 'ADMIN'
ON CONFLICT (role_id, interlock_category, equipment_id) DO UPDATE
SET can_view = TRUE, can_disable_non_safety = TRUE, can_disable_safety = TRUE, can_override = TRUE;

-- =====================================================
-- PART 5: VERIFY PERMISSIONS WERE CREATED
-- =====================================================

\echo ''
\echo '======================================================================'
\echo 'Role Permissions Configuration Summary'
\echo '======================================================================'
\echo ''

-- Show created roles
\echo 'Roles Created:'
SELECT name, is_admin, created_at FROM historian_meta.roles 
WHERE name IN ('OPERATOR', 'SUPERVISOR', 'SAFETY_OFFICER', 'ADMIN')
ORDER BY is_admin DESC, name;

\echo ''
\echo 'Alarm Permissions by Role:'
SELECT 
  r.name as role,
  COUNT(*) as permission_categories,
  r.is_admin as is_admin
FROM historian_meta.roles r
LEFT JOIN historian_meta.role_alarm_permissions rap ON r.id = rap.role_id
WHERE r.name IN ('OPERATOR', 'SUPERVISOR', 'SAFETY_OFFICER', 'ADMIN')
GROUP BY r.id, r.name, r.is_admin
ORDER BY r.is_admin DESC;

\echo ''
\echo 'Alarm Permissions Details:'
SELECT 
  r.name as role,
  COUNT(rap.id) as total_permissions,
  SUM(CASE WHEN rap.can_clear = TRUE THEN 1 ELSE 0 END) as can_clear_permissions,
  SUM(CASE WHEN rap.requires_approval_to_clear = TRUE THEN 1 ELSE 0 END) as requires_approval_permissions
FROM historian_meta.roles r
LEFT JOIN historian_meta.role_alarm_permissions rap ON r.id = rap.role_id
WHERE r.name IN ('OPERATOR', 'SUPERVISOR', 'SAFETY_OFFICER', 'ADMIN')
GROUP BY r.id, r.name
ORDER BY r.name;

\echo ''
\echo '======================================================================'
\echo 'Migration 006 Complete'
\echo '======================================================================'
\echo ''

