-- =============================================================================
-- Migration 027 — Phase 4a: Access Control Upgrade
-- Design reference: PLANT_AREA_ACCESS_CONTROL_DESIGN.md §16, §17, §26
-- Date: 2026-05-24
-- Author: Phase 4 implementation — all changes are ADDITIVE (safe to re-run)
-- =============================================================================

-- ── 1. users.allow_concurrent_sessions ─────────────────────────────────────
-- Allows specific users (e.g., Admin, Control Room) to hold multiple active
-- sessions simultaneously. Default false = single-session enforcement (per §17).
ALTER TABLE historian_meta.users
    ADD COLUMN IF NOT EXISTS allow_concurrent_sessions BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN historian_meta.users.allow_concurrent_sessions IS
    'If true, login does NOT supersede existing sessions. Admin users should have this true.';

-- ── 2. roles.admin_scope ───────────────────────────────────────────────────
-- Scaffold for future PlantAdmin support (§26 Phase 7).
-- NULL = full global admin (current behaviour), 'plant' = PlantAdmin (future).
ALTER TABLE historian_meta.roles
    ADD COLUMN IF NOT EXISTS admin_scope VARCHAR(20) DEFAULT NULL;

COMMENT ON COLUMN historian_meta.roles.admin_scope IS
    'NULL = global admin. Future: ''plant'' = restricted to assigned plant only.';

-- ── 3. user_sessions.device_name ───────────────────────────────────────────
-- Human-readable device label (§17.4, §27.4). e.g. "Control Room PC-3".
-- Populated from login request body: { "device_name": "..." }
ALTER TABLE historian_meta.user_sessions
    ADD COLUMN IF NOT EXISTS device_name VARCHAR(150) DEFAULT NULL;

COMMENT ON COLUMN historian_meta.user_sessions.device_name IS
    'Human-readable device label supplied by client at login. e.g. Control Room PC-3.';

-- ── 4. access_audit_log — migrate from TEXT to JSONB ──────────────────────
-- Design §5.3 and §13: old_areas/new_areas TEXT columns replaced by
-- old_state/new_state JSONB for structured compliance queries.
-- Strategy: add new JSONB columns, make old TEXT columns nullable (preserve data).
ALTER TABLE historian_meta.access_audit_log
    ADD COLUMN IF NOT EXISTS old_state JSONB DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS new_state JSONB DEFAULT NULL;

-- Make old TEXT columns nullable so new code writing JSONB does not need to fill them
DO $$
BEGIN
    -- Drop NOT NULL from old_areas if it exists
    ALTER TABLE historian_meta.access_audit_log ALTER COLUMN old_areas DROP NOT NULL;
EXCEPTION WHEN OTHERS THEN NULL; END $$;

DO $$
BEGIN
    ALTER TABLE historian_meta.access_audit_log ALTER COLUMN new_areas DROP NOT NULL;
EXCEPTION WHEN OTHERS THEN NULL; END $$;

-- GIN indexes for JSONB compliance search queries
CREATE INDEX IF NOT EXISTS idx_audit_log_old_state
    ON historian_meta.access_audit_log USING gin(old_state);
CREATE INDEX IF NOT EXISTS idx_audit_log_new_state
    ON historian_meta.access_audit_log USING gin(new_state);

COMMENT ON COLUMN historian_meta.access_audit_log.old_state IS
    'JSONB snapshot before change. e.g. {"areas":["Plant1/Area1"],"role":"Operator"}';
COMMENT ON COLUMN historian_meta.access_audit_log.new_state IS
    'JSONB snapshot after change. e.g. {"areas":["Plant1/Area1","FTP-1/POTLINE"],"role":"Operator"}';

-- ── 5. license_keys table ──────────────────────────────────────────────────
-- §16.2: Stores ECDSA-signed activation keys.
-- SECURITY NOTE: max_users column is CACHED DISPLAY ONLY.
-- Runtime enforcement uses _get_verified_max_users() which reads signed_payload.
-- A DB admin UPDATE on max_users does NOT bypass the limit check in Python.
CREATE TABLE IF NOT EXISTS historian_meta.license_keys (
    id               SERIAL PRIMARY KEY,
    key_hash         VARCHAR(128) NOT NULL UNIQUE,
    key_label        VARCHAR(200),
    signed_payload   TEXT NOT NULL,        -- base64url(payload).<base64url(ed25519_sig)>
    max_users        INTEGER NOT NULL DEFAULT 5,  -- CACHED DISPLAY — do not trust directly
    max_areas        INTEGER DEFAULT NULL,
    issued_to        VARCHAR(200),
    issued_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_until      TIMESTAMPTZ DEFAULT NULL,     -- NULL = perpetual
    is_active        BOOLEAN NOT NULL DEFAULT true,
    activated_by     INTEGER REFERENCES historian_meta.users(id) ON DELETE SET NULL,
    activated_at     TIMESTAMPTZ DEFAULT NULL,
    notes            TEXT DEFAULT NULL
);

-- Only one key active at a time
CREATE UNIQUE INDEX IF NOT EXISTS idx_license_keys_active
    ON historian_meta.license_keys(is_active)
    WHERE is_active = true;

COMMENT ON TABLE historian_meta.license_keys IS
    'Signed activation keys. max_users column is for display only — always verify signed_payload.';

-- ── 6. user_area_assignments — partial unique index ─────────────────────────
-- Replaces the old inline UNIQUE(user_id, plant_area_id) constraint.
-- Partial index: uniqueness only enforced on active rows (revoked_at IS NULL).
-- This allows history-preserving re-assignment (revoke → re-assign same area later).
DO $$
BEGIN
    -- Drop old inline UNIQUE constraint if it exists (name varies by PostgreSQL version)
    ALTER TABLE historian_meta.user_area_assignments
        DROP CONSTRAINT IF EXISTS user_area_assignments_user_id_plant_area_id_key;
EXCEPTION WHEN OTHERS THEN NULL; END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_area_active_unique
    ON historian_meta.user_area_assignments(user_id, plant_area_id)
    WHERE revoked_at IS NULL;

COMMENT ON INDEX historian_meta.idx_user_area_active_unique IS
    'Partial unique index: only one ACTIVE assignment per user per area. Revoked rows preserved for history.';

-- ── 7. Seed: set allow_concurrent_sessions = true for admin users ───────────
-- Admin users should be allowed concurrent sessions by default.
UPDATE historian_meta.users u
SET allow_concurrent_sessions = true
FROM historian_meta.roles r
WHERE r.id = u.role_id
  AND r.is_admin = true
  AND u.allow_concurrent_sessions = false;

-- =============================================================================
-- End of migration 027
-- Run check: SELECT column_name FROM information_schema.columns
--            WHERE table_schema='historian_meta' AND table_name='users'
--            AND column_name='allow_concurrent_sessions';
-- =============================================================================
