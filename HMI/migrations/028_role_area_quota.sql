-- Migration 028: Add max_areas_per_user quota column to roles
-- Safe to re-run: all changes are IF NOT EXISTS / DO NOTHING.
-- NULL means unlimited (admin-like roles). 0 means no area access allowed.

BEGIN;

-- Add quota column to roles
ALTER TABLE historian_meta.roles
    ADD COLUMN IF NOT EXISTS max_areas_per_user INTEGER DEFAULT NULL;

-- Sensible defaults for existing roles:
--   admin roles     → NULL (unlimited — they bypass area filters anyway)
--   non-admin roles → NULL for now (unlimited until explicitly set by admin)
-- Admin can tighten per-role quotas via the Roles tab.
-- No rows updated here — keep NULL (unlimited) as safe default.

COMMIT;
