-- =============================================================================
-- Migration 030 — plants_areas: add server_progid column (OPC Server / Topic level)
--
-- Design rationale:
--   The full access hierarchy is:
--     OPC Server (server_progid / MQTT topic) → Plant → Area → Tag
--   Migration 029 only captured Plant + Area.  This migration adds server_progid
--   so admins can assign access at the correct level of the hierarchy.
--
-- Changes:
--   1. ALTER plants_areas — add server_progid column (nullable for backward compat)
--   2. UPDATE existing rows with server_progid from tag_master
--   3. Drop old UNIQUE(plant, area) constraint, add UNIQUE(server_progid, plant, area)
--   4. Rebuild idx_plants_areas_codes to include server_progid
--   5. Sync new (server_progid, plant, area) combos from tag_master
--   6. Update display_name to include server_progid prefix
-- =============================================================================

-- ── 1. Add server_progid column ───────────────────────────────────────────────
ALTER TABLE historian_meta.plants_areas
    ADD COLUMN IF NOT EXISTS server_progid VARCHAR(200) DEFAULT NULL;

COMMENT ON COLUMN historian_meta.plants_areas.server_progid IS
    'OPC server ProgID or MQTT topic/PLC name that owns this Plant/Area. '
    'Matches tag_master.server_progid. NULL = unknown/legacy row.';

-- ── 2. Populate server_progid from tag_master ─────────────────────────────────
-- For each existing plant/area row, find the most common server_progid in tag_master.
-- This handles the common case where one OPC server owns a given plant/area.
UPDATE historian_meta.plants_areas pa
SET server_progid = (
    SELECT tm.server_progid
    FROM historian_meta.tag_master tm
    WHERE tm.plant = pa.plant
      AND tm.area  = pa.area
      AND tm.server_progid IS NOT NULL
    GROUP BY tm.server_progid
    ORDER BY COUNT(*) DESC
    LIMIT 1
)
WHERE pa.server_progid IS NULL;

-- ── 3. Fix unique constraint to include server_progid ─────────────────────────
-- Drop old (plant, area) unique constraint safely (it may have a generated name)
DO $$
DECLARE
    v_cname TEXT;
BEGIN
    SELECT conname INTO v_cname
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'historian_meta'
      AND t.relname = 'plants_areas'
      AND c.contype = 'u'
    LIMIT 1;

    IF v_cname IS NOT NULL THEN
        EXECUTE format('ALTER TABLE historian_meta.plants_areas DROP CONSTRAINT IF EXISTS %I', v_cname);
    END IF;
END$$;

-- Add new unique constraint covering server_progid + plant + area
-- COALESCE so NULLs don't break uniqueness (each NULL is treated as empty string)
CREATE UNIQUE INDEX IF NOT EXISTS idx_plants_areas_server_plant_area_unique
    ON historian_meta.plants_areas(
        COALESCE(server_progid, ''),
        plant,
        area
    );

-- ── 4. Rebuild code index to include server_progid ───────────────────────────
DROP INDEX IF EXISTS historian_meta.idx_plants_areas_codes;
CREATE INDEX IF NOT EXISTS idx_plants_areas_codes
    ON historian_meta.plants_areas(server_progid, plant_code, area_code);

-- ── 5. Sync any NEW (server_progid, plant, area) combos from tag_master ──────
-- This picks up combos that do NOT yet have a row in plants_areas
INSERT INTO historian_meta.plants_areas
    (server_progid, plant_code, area_code, plant, area, display_name)
SELECT DISTINCT
    tm.server_progid,
    UPPER(REGEXP_REPLACE(tm.plant, '[^A-Za-z0-9]', '', 'g')),
    UPPER(REGEXP_REPLACE(tm.area,  '[^A-Za-z0-9]', '', 'g')),
    tm.plant,
    tm.area,
    COALESCE(tm.server_progid, 'Unknown') || ' › ' || tm.plant || ' › ' || tm.area
FROM historian_meta.tag_master tm
WHERE tm.plant       IS NOT NULL
  AND tm.area        IS NOT NULL
  AND tm.server_progid IS NOT NULL
ON CONFLICT DO NOTHING;   -- idx_plants_areas_server_plant_area_unique handles dupes

-- ── 6. Update display_name to show the full path ─────────────────────────────
UPDATE historian_meta.plants_areas
SET display_name = COALESCE(server_progid, 'Unknown') || ' › ' || plant || ' › ' || area
WHERE display_name NOT LIKE '%›%';   -- only update rows that have old-style display_name

SELECT
    server_progid,
    plant,
    area,
    display_name,
    is_active
FROM historian_meta.plants_areas
ORDER BY server_progid, plant, area;
