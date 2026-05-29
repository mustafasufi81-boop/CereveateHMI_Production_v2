-- ============================================================================
-- COMPLETE PLANTS_AREAS AUTO-SYNC SYSTEM
-- ============================================================================
-- Syncs plants_areas table with tag_master automatically
-- Handles user_area_assignments FK relationships
-- ============================================================================

-- Step 1: Drop conflicting unique index if it exists
-- (older constraint on plant, area, COALESCE(server_progid,''))
DROP INDEX IF EXISTS historian_meta.idx_plants_areas_server_plant_area_unique;

-- Step 2: Create sync function
CREATE OR REPLACE FUNCTION historian_meta.sync_plants_areas_from_tags()
RETURNS void AS $$
BEGIN
    -- Insert or activate entries from tag_master
    INSERT INTO historian_meta.plants_areas (
        plant_code,
        area_code,
        plant,
        area,
        display_name,
        server_progid,
        is_active,
        created_at
    )
    SELECT DISTINCT
        UPPER(REPLACE(tm.plant, '_', '')) as plant_code,
        UPPER(REPLACE(tm.area, '_', '')) as area_code,
        tm.plant,
        tm.area,
        tm.server_progid || ' - ' || tm.plant || ' - ' || tm.area as display_name,
        tm.server_progid,
        true as is_active,
        NOW()
    FROM historian_meta.tag_master tm
    WHERE tm.enabled = true
    AND tm.server_progid IS NOT NULL
    AND tm.plant IS NOT NULL
    AND tm.area IS NOT NULL
    ON CONFLICT (plant_code, area_code, server_progid) 
    DO UPDATE SET
        is_active = true,
        display_name = EXCLUDED.display_name;
    
    -- Deactivate entries that have no tags
    UPDATE historian_meta.plants_areas pa
    SET is_active = false
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
    
    RAISE NOTICE 'Plants_areas synced from tag_master';
END;
$$ LANGUAGE plpgsql;

-- Step 2: Create trigger function
CREATE OR REPLACE FUNCTION historian_meta.trigger_sync_plants_areas()
RETURNS TRIGGER AS $$
BEGIN
    -- Auto-sync whenever tags are modified
    PERFORM historian_meta.sync_plants_areas_from_tags();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Step 3: Create trigger on tag_master
DROP TRIGGER IF EXISTS trg_auto_sync_plants_areas ON historian_meta.tag_master;
CREATE TRIGGER trg_auto_sync_plants_areas
    AFTER INSERT OR UPDATE OF server_progid, plant, area, enabled OR DELETE
    ON historian_meta.tag_master
    FOR EACH STATEMENT
    EXECUTE FUNCTION historian_meta.trigger_sync_plants_areas();

-- Step 4: Initial sync
SELECT historian_meta.sync_plants_areas_from_tags();

-- Step 5: Verification
SELECT 
    pa.id,
    pa.server_progid,
    pa.plant,
    pa.area,
    pa.is_active,
    COUNT(tm.tag_id) as tag_count,
    COUNT(ua.id) as user_assignments
FROM historian_meta.plants_areas pa
LEFT JOIN historian_meta.tag_master tm 
    ON tm.server_progid = pa.server_progid 
    AND tm.plant = pa.plant 
    AND tm.area = pa.area
    AND tm.enabled = true
LEFT JOIN historian_meta.user_area_assignments ua
    ON ua.plant_area_id = pa.id
WHERE pa.server_progid IS NOT NULL
GROUP BY pa.id, pa.server_progid, pa.plant, pa.area, pa.is_active
ORDER BY pa.is_active DESC, pa.server_progid;

COMMENT ON FUNCTION historian_meta.sync_plants_areas_from_tags() IS 
'Syncs plants_areas table from tag_master. Auto-activates entries with tags, deactivates entries without tags.';

COMMENT ON FUNCTION historian_meta.trigger_sync_plants_areas() IS 
'Trigger function that calls sync_plants_areas_from_tags() on tag_master changes.';
