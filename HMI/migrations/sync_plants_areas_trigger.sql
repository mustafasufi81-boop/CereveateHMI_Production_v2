-- ============================================================================
-- AUTO-SYNC PLANTS_AREAS WITH TAG_MASTER
-- ============================================================================
-- PURPOSE: Automatically maintain plants_areas table when tags are added/updated
--          in tag_master, ensuring report dropdown sources always match reality
-- ============================================================================

-- Function to sync plants_areas from tag_master
CREATE OR REPLACE FUNCTION historian_meta.sync_plants_areas_from_tags()
RETURNS TRIGGER AS $$
BEGIN
    -- When a tag is inserted or updated with server_progid, plant, area
    -- Ensure a corresponding plants_areas entry exists
    
    IF NEW.server_progid IS NOT NULL AND NEW.plant IS NOT NULL AND NEW.area IS NOT NULL THEN
        -- Insert or update plants_areas entry
        INSERT INTO historian_meta.plants_areas (
            plant, 
            area, 
            plant_code, 
            area_code, 
            server_progid, 
            display_name, 
            is_active,
            created_at,
            updated_at
        )
        VALUES (
            NEW.plant,
            NEW.area,
            UPPER(REPLACE(NEW.plant, '_', '')),  -- Generate plant_code
            UPPER(REPLACE(NEW.area, '_', '')),   -- Generate area_code
            NEW.server_progid,
            NEW.server_progid || ' - ' || NEW.plant || ' - ' || NEW.area,  -- Display name
            true,  -- Active by default
            NOW(),
            NOW()
        )
        ON CONFLICT (plant, area, server_progid) 
        DO UPDATE SET
            is_active = true,  -- Re-activate if it was disabled
            updated_at = NOW(),
            display_name = EXCLUDED.display_name;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger on INSERT/UPDATE of tag_master
DROP TRIGGER IF EXISTS trg_sync_plants_areas_on_tag_insert ON historian_meta.tag_master;
CREATE TRIGGER trg_sync_plants_areas_on_tag_insert
    AFTER INSERT OR UPDATE OF server_progid, plant, area, enabled
    ON historian_meta.tag_master
    FOR EACH ROW
    WHEN (NEW.enabled = true)
    EXECUTE FUNCTION historian_meta.sync_plants_areas_from_tags();

-- Function to deactivate plants_areas when no active tags remain
CREATE OR REPLACE FUNCTION historian_meta.deactivate_unused_plants_areas()
RETURNS void AS $$
BEGIN
    -- Mark plants_areas as inactive if no enabled tags reference them
    UPDATE historian_meta.plants_areas pa
    SET is_active = false, updated_at = NOW()
    WHERE pa.is_active = true
    AND pa.server_progid IS NOT NULL
    AND NOT EXISTS (
        SELECT 1 
        FROM historian_meta.tag_master tm
        WHERE tm.server_progid = pa.server_progid
        AND tm.plant = pa.plant
        AND tm.area = pa.area
        AND tm.enabled = true
    );
END;
$$ LANGUAGE plpgsql;

-- Schedule periodic cleanup (call this from a cron job or manually)
-- SELECT historian_meta.deactivate_unused_plants_areas();

-- ============================================================================
-- INITIAL SYNC: Populate plants_areas from existing tag_master data
-- ============================================================================
INSERT INTO historian_meta.plants_areas (
    plant, 
    area, 
    plant_code, 
    area_code, 
    server_progid, 
    display_name, 
    is_active,
    created_at,
    updated_at
)
SELECT DISTINCT
    tm.plant,
    tm.area,
    UPPER(REPLACE(tm.plant, '_', '')) as plant_code,
    UPPER(REPLACE(tm.area, '_', '')) as area_code,
    tm.server_progid,
    tm.server_progid || ' - ' || tm.plant || ' - ' || tm.area as display_name,
    true as is_active,
    NOW(),
    NOW()
FROM historian_meta.tag_master tm
WHERE tm.enabled = true
AND tm.server_progid IS NOT NULL
AND tm.plant IS NOT NULL
AND tm.area IS NOT NULL
ON CONFLICT (plant, area, server_progid) 
DO UPDATE SET
    is_active = true,
    updated_at = NOW(),
    display_name = EXCLUDED.display_name;

-- Deactivate entries that don't have tags
SELECT historian_meta.deactivate_unused_plants_areas();

-- ============================================================================
-- VERIFICATION QUERY
-- ============================================================================
SELECT 
    pa.server_progid,
    pa.plant,
    pa.area,
    pa.is_active,
    COUNT(tm.tag_id) as tag_count
FROM historian_meta.plants_areas pa
LEFT JOIN historian_meta.tag_master tm 
    ON tm.server_progid = pa.server_progid 
    AND tm.plant = pa.plant 
    AND tm.area = pa.area
    AND tm.enabled = true
WHERE pa.server_progid IS NOT NULL
GROUP BY pa.server_progid, pa.plant, pa.area, pa.is_active
ORDER BY pa.is_active DESC, pa.server_progid, pa.plant, pa.area;

-- ============================================================================
-- USAGE NOTES:
-- ============================================================================
-- 1. When you add tags to tag_master with server_progid/plant/area, 
--    plants_areas will auto-update (trigger runs automatically)
--
-- 2. To clean up unused entries (no tags), run manually:
--    SELECT historian_meta.deactivate_unused_plants_areas();
--
-- 3. The trigger only activates when tags are enabled=true
--
-- 4. Report dropdown will automatically show correct sources
-- ============================================================================
