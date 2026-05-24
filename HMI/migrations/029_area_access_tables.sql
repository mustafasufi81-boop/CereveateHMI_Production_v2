-- =============================================================================
-- Migration 029 — Area Access: Core Tables
-- Design reference: PLANT_AREA_ACCESS_CONTROL_DESIGN.md §4, §5, §6
-- Date: 2026-05-24
-- Author: Phase 3 implementation — all changes are ADDITIVE (safe to re-run)
--
-- Creates the three tables required for the area-based data-scoping feature:
--   1. plants_areas          — registry of all known plant/area combinations
--   2. user_area_assignments — which users are assigned to which areas
--   3. access_audit_log      — compliance trail of every assignment change
--
-- NOTE: Migration 027 already ALTERs these tables (adds JSONB columns + indexes).
--       Run 029 BEFORE 027 on a fresh install. On an existing install where 027
--       already ran, run 029 first — all CREATE TABLE IF NOT EXISTS are safe.
-- =============================================================================

-- ── 1. plants_areas ──────────────────────────────────────────────────────────
-- Central registry of valid plant/area combinations.
-- Immutable codes (plant_code, area_code) are generated once on insert and
-- never updated — they serve as stable identifiers for downstream references.
-- Tags are linked by matching plants_areas.plant = tag_master.plant, etc.
CREATE TABLE IF NOT EXISTS historian_meta.plants_areas (
    id           SERIAL PRIMARY KEY,
    plant_code   VARCHAR(50)  NOT NULL,       -- immutable, UPPER, alphanumeric only
    area_code    VARCHAR(50)  NOT NULL,       -- immutable, UPPER, alphanumeric only
    plant        VARCHAR(200) NOT NULL,       -- human-readable plant name
    area         VARCHAR(200) NOT NULL,       -- human-readable area name
    display_name VARCHAR(300) NOT NULL,       -- pre-computed "Plant — Area" label
    description  TEXT         DEFAULT NULL,
    is_active    BOOLEAN      NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    -- (plant, area) pair is the business key — must be globally unique
    UNIQUE(plant, area)
);

CREATE INDEX IF NOT EXISTS idx_plants_areas_active
    ON historian_meta.plants_areas(is_active);
CREATE INDEX IF NOT EXISTS idx_plants_areas_codes
    ON historian_meta.plants_areas(plant_code, area_code);

COMMENT ON TABLE historian_meta.plants_areas IS
    'Registry of all plant/area combinations. Users are granted access to specific rows. '
    'Tags are linked by (plant, area) match with tag_master.';
COMMENT ON COLUMN historian_meta.plants_areas.plant_code IS
    'Immutable code: UPPER(REGEXP_REPLACE(plant, ''[^A-Za-z0-9]'', '''')). '
    'Set once at creation — do NOT update.';
COMMENT ON COLUMN historian_meta.plants_areas.area_code IS
    'Immutable code: UPPER(REGEXP_REPLACE(area, ''[^A-Za-z0-9]'', '''')). '
    'Set once at creation — do NOT update.';


-- ── 2. user_area_assignments ──────────────────────────────────────────────────
-- Tracks which plant_area each user has been granted access to.
-- Rows are NEVER deleted — revoked assignments keep history (revoked_at IS NOT NULL).
-- The partial unique index ensures at most one ACTIVE assignment per user per area.
CREATE TABLE IF NOT EXISTS historian_meta.user_area_assignments (
    id             SERIAL PRIMARY KEY,
    user_id        INTEGER     NOT NULL REFERENCES historian_meta.users(id) ON DELETE CASCADE,
    plant_area_id  INTEGER     NOT NULL REFERENCES historian_meta.plants_areas(id) ON DELETE RESTRICT,
    assigned_by    INTEGER              REFERENCES historian_meta.users(id) ON DELETE SET NULL,
    assigned_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at     TIMESTAMPTZ          DEFAULT NULL   -- NULL = currently active
);

-- Partial unique index: at most one ACTIVE assignment per (user, area).
-- Revoked rows (revoked_at IS NOT NULL) are excluded — they are history.
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_area_active_unique
    ON historian_meta.user_area_assignments(user_id, plant_area_id)
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_user_area_assignments_user
    ON historian_meta.user_area_assignments(user_id);
CREATE INDEX IF NOT EXISTS idx_user_area_assignments_area
    ON historian_meta.user_area_assignments(plant_area_id);

COMMENT ON TABLE historian_meta.user_area_assignments IS
    'Grants a user access to a specific plant/area. '
    'Revoked rows (revoked_at IS NOT NULL) are preserved for audit history.';
COMMENT ON COLUMN historian_meta.user_area_assignments.revoked_at IS
    'NULL = currently active. Non-null = revoked at that timestamp. Never deleted.';


-- ── 3. access_audit_log ───────────────────────────────────────────────────────
-- Immutable compliance trail — one row per area assignment change.
-- old_state / new_state are JSONB snapshots (§5.3); old_areas / new_areas are
-- legacy TEXT columns (kept nullable for backward-compat; new writes use JSONB).
CREATE TABLE IF NOT EXISTS historian_meta.access_audit_log (
    id               SERIAL PRIMARY KEY,
    admin_user_id    INTEGER              REFERENCES historian_meta.users(id) ON DELETE SET NULL,
    admin_username   VARCHAR(255) NOT NULL,
    admin_ip         VARCHAR(45)  DEFAULT NULL,
    target_user_id   INTEGER              REFERENCES historian_meta.users(id) ON DELETE SET NULL,
    target_username  VARCHAR(255) NOT NULL,
    action           VARCHAR(50)  NOT NULL,  -- e.g. 'REPLACE', 'GRANT', 'REVOKE'
    old_areas        TEXT         DEFAULT NULL,  -- legacy TEXT (nullable per migration 027)
    new_areas        TEXT         DEFAULT NULL,  -- legacy TEXT (nullable per migration 027)
    old_state        JSONB        DEFAULT NULL,  -- JSONB snapshot before change (§5.3)
    new_state        JSONB        DEFAULT NULL,  -- JSONB snapshot after change (§5.3)
    notes            TEXT         DEFAULT NULL,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_target_user
    ON historian_meta.access_audit_log(target_user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_admin_user
    ON historian_meta.access_audit_log(admin_user_id);

-- created_at / timestamp column may differ on existing installs — add IF NOT EXISTS
ALTER TABLE historian_meta.access_audit_log
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_audit_log_created_at
    ON historian_meta.access_audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_old_state
    ON historian_meta.access_audit_log USING gin(old_state)
    WHERE old_state IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_log_new_state
    ON historian_meta.access_audit_log USING gin(new_state)
    WHERE new_state IS NOT NULL;

COMMENT ON TABLE historian_meta.access_audit_log IS
    'Immutable compliance trail of every area-access assignment change. '
    'One row per change event. Never update or delete rows.';
