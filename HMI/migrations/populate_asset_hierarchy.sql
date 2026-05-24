-- Asset Hierarchy Population Script
-- Works with your EXISTING tag_master data

-- ============================================
-- STEP 1: View your current tags
-- ============================================
SELECT 
    tag_id,
    tag_name,
    plant,
    area,
    equipment,
    enabled,
    data_type,
    eng_unit
FROM historian_meta.tag_master
WHERE enabled = true
ORDER BY tag_id;

-- ============================================
-- STEP 2: Check current hierarchy status
-- ============================================
SELECT 
    COUNT(*) as total_enabled_tags,
    COUNT(plant) as has_plant,
    COUNT(area) as has_area,
    COUNT(equipment) as has_equipment,
    COUNT(sub_equipment) as has_sub_equipment,
    COUNT(components) as has_components
FROM historian_meta.tag_master
WHERE enabled = true;

-- ============================================
-- STEP 3: Update hierarchy based on EXISTING plant/area/equipment
-- (This preserves your existing hierarchy and just adds the new columns)
-- ============================================

-- Option A: If you already have plant/area/equipment filled, just add sub-equipment and components
UPDATE historian_meta.tag_master
SET 
    sub_equipment = CASE 
        WHEN equipment IS NOT NULL THEN equipment || ' System'
        ELSE 'Monitoring System'
    END,
    components = CASE 
        WHEN data_type IN ('Float', 'Double', 'Int32', 'Int64') THEN 'Sensor'
        WHEN data_type IN ('Boolean', 'Bool') THEN 'Switch'
        WHEN data_type IN ('String', 'Text') THEN 'Controller'
        ELSE 'Device'
    END
WHERE enabled = true
  AND sub_equipment IS NULL;

-- ============================================
-- STEP 4: Fill in missing hierarchy levels
-- (Only updates tags that don't have plant/area/equipment)
-- ============================================

-- If plant is NULL, set default
UPDATE historian_meta.tag_master
SET plant = 'Northstar Mfg Plant'
WHERE enabled = true AND plant IS NULL;

-- If area is NULL, try to infer from tag_id or set default
UPDATE historian_meta.tag_master
SET area = CASE 
    WHEN tag_id LIKE '%MIX%' OR tag_id LIKE '%MIXER%' THEN 'Mixing'
    WHEN tag_id LIKE '%PACK%' OR tag_id LIKE '%PKG%' THEN 'Packaging'
    WHEN tag_id LIKE '%RAW%' OR tag_id LIKE '%RM%' THEN 'Raw Material'
    WHEN tag_id LIKE '%PROD%' THEN 'Production'
    ELSE 'General Area'
END
WHERE enabled = true AND area IS NULL;

-- If equipment is NULL, try to infer from tag_id or set default
UPDATE historian_meta.tag_master
SET equipment = CASE 
    WHEN tag_id LIKE '%M-101%' OR tag_id LIKE '%MIXER%' THEN 'Mixer M-101'
    WHEN tag_id LIKE '%P-%' OR tag_id LIKE '%PUMP%' THEN 'Pump'
    WHEN tag_id LIKE '%T-%' OR tag_id LIKE '%TANK%' THEN 'Tank'
    WHEN tag_id LIKE '%R-%' OR tag_id LIKE '%REACTOR%' THEN 'Reactor'
    ELSE 'General Equipment'
END
WHERE enabled = true AND equipment IS NULL;

-- ============================================
-- STEP 5: Set equipment criticality based on patterns
-- ============================================
UPDATE historian_meta.tag_master
SET equipment_criticality = CASE 
    WHEN tag_id LIKE '%TRIP%' OR tag_id LIKE '%SAFETY%' THEN 5  -- Critical
    WHEN tag_id LIKE '%ALARM%' OR tag_id LIKE '%HIGH%' THEN 4   -- Urgent
    WHEN tag_id LIKE '%TEMP%' OR tag_id LIKE '%PRESS%' THEN 3   -- High
    ELSE 2  -- Medium
END
WHERE enabled = true AND equipment_criticality IS NULL;

-- ============================================
-- STEP 6: Verify the updates
-- ============================================
SELECT 
    tag_id,
    tag_name,
    plant,
    area,
    equipment,
    sub_equipment,
    components,
    equipment_criticality,
    trip_category
FROM historian_meta.tag_master
WHERE enabled = true
ORDER BY plant, area, equipment, sub_equipment, components;

-- ============================================
-- STEP 7: Show hierarchy summary
-- ============================================
SELECT 
    plant,
    area,
    equipment,
    COUNT(*) as tag_count
FROM historian_meta.tag_master
WHERE enabled = true
GROUP BY plant, area, equipment
ORDER BY plant, area, equipment;

-- ============================================
-- OPTIONAL: Customize specific tags manually
-- ============================================
-- Use these templates to customize specific tags:

-- Example: Update a specific tag with full hierarchy
/*
UPDATE historian_meta.tag_master
SET 
    plant = 'Your Plant Name',
    area = 'Your Area Name',
    equipment = 'Your Equipment Name',
    sub_equipment = 'Your Sub-Equipment Name',
    components = 'Your Component Name',
    equipment_criticality = 4,  -- 1-5 scale
    trip_category = 'SAFETY_TRIP'  -- Options: PROCESS_TRIP, SAFETY_TRIP, EMERGENCY_TRIP, INTERLOCK
WHERE tag_id = 'YOUR_TAG_ID';
*/

-- Example: Update multiple tags with same pattern
/*
UPDATE historian_meta.tag_master
SET 
    area = 'Mixing',
    equipment = 'Mixer M-101',
    sub_equipment = 'Temperature Control',
    components = 'Temperature Sensor'
WHERE tag_id LIKE 'TT-%' OR tag_id LIKE '%TEMP%';
*/
