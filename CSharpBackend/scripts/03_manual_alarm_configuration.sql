/* ====================================================================
   MANUAL ALARM CONFIGURATION (For specific critical tags)
   
   Purpose: Manually configure alarm limits for specific equipment
   - Override auto-suggested thresholds
   - Set specific limits based on equipment specifications
   - Configure trip category and equipment criticality
   
   Date: December 22, 2025
   
   Usage: Modify the UPDATE statements below for your specific tags
==================================================================== */

\echo ''
\echo '======================================================================'
\echo '     MANUAL ALARM CONFIGURATION - CRITICAL EQUIPMENT'
\echo '======================================================================'
\echo ''

-- Example 1: Configure Random.Real4 as critical temperature sensor
UPDATE historian_meta.tag_master 
SET 
    -- Alarm limits (manually specified)
    alarm_hh_limit = 100.0,   -- High-High limit (Critical)
    alarm_h_limit = 90.0,     -- High limit (Warning)
    alarm_l_limit = 10.0,     -- Low limit (Warning)
    alarm_ll_limit = 5.0,     -- Low-Low limit (Critical)
    
    -- Alarm configuration
    alarm_enabled = true,
    alarm_priority = 5,       -- Critical (1=Low, 5=Critical)
    alarm_deadband = 2.0,     -- Prevent oscillation
    
    -- Equipment context
    trip_category = 'SAFETY_TRIP',
    equipment_criticality = 5,  -- Critical equipment
    associated_equipment = 'TURBINE_01',
    is_trip_initiator = true,   -- This alarm can cause trips
    
    -- Metadata
    description = 'Turbine bearing temperature - critical safety parameter',
    config_updated_at = now(),
    created_by = 'engineer_manual_config'
    
WHERE tag_id = 'Random.Real4';

\echo '✓ Configured Random.Real4 as critical safety alarm'

-- Example 2: Configure Random.Int4 as pressure sensor
UPDATE historian_meta.tag_master 
SET 
    alarm_hh_limit = 50.0,
    alarm_h_limit = 40.0,
    alarm_l_limit = -40.0,
    alarm_ll_limit = -50.0,
    
    alarm_enabled = true,
    alarm_priority = 4,       -- Urgent
    alarm_deadband = 1.5,
    
    trip_category = 'PROCESS_TRIP',
    equipment_criticality = 4,
    associated_equipment = 'BOILER_A',
    is_trip_initiator = false,
    
    description = 'Boiler pressure - process control parameter',
    config_updated_at = now(),
    created_by = 'engineer_manual_config'
    
WHERE tag_id = 'Random.Int4';

\echo '✓ Configured Random.Int4 as urgent process alarm'

-- Example 3: Configure Random.UInt2 as vibration sensor
UPDATE historian_meta.tag_master 
SET 
    alarm_hh_limit = 1000.0,
    alarm_h_limit = 900.0,
    alarm_l_limit = NULL,      -- No low alarm for vibration
    alarm_ll_limit = NULL,
    
    alarm_enabled = true,
    alarm_priority = 3,        -- Medium
    alarm_deadband = 10.0,
    
    trip_category = 'SAFETY_TRIP',
    equipment_criticality = 4,
    associated_equipment = 'TURBINE_01',
    is_trip_initiator = true,
    
    description = 'Turbine vibration - high values indicate mechanical issues',
    config_updated_at = now(),
    created_by = 'engineer_manual_config'
    
WHERE tag_id = 'Random.UInt2';

\echo '✓ Configured Random.UInt2 as vibration alarm'

\echo ''
\echo '======================================================================'
\echo '     MANUALLY CONFIGURED ALARMS'
\echo '======================================================================'
\echo ''

-- Display manually configured alarms
SELECT 
    tag_id,
    tag_name,
    description,
    alarm_ll_limit AS "LL",
    alarm_l_limit AS "L",
    alarm_h_limit AS "H",
    alarm_hh_limit AS "HH",
    alarm_priority AS prio,
    alarm_deadband AS deadband,
    alarm_enabled AS enabled,
    trip_category,
    equipment_criticality AS equip_crit,
    associated_equipment AS equipment,
    is_trip_initiator AS trip_init
FROM historian_meta.tag_master
WHERE created_by = 'engineer_manual_config'
   OR config_updated_at > now() - INTERVAL '1 minute'
ORDER BY alarm_priority DESC, tag_id;

\echo ''
\echo 'Manual configuration complete!'
\echo ''

-- Verify acknowledgment source column exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'historian_raw' 
          AND table_name = 'historian_events'
          AND column_name = 'acknowledged_source'
    ) THEN
        RAISE NOTICE 'Adding acknowledged_source column to historian_events...';
        
        ALTER TABLE historian_raw.historian_events
            ADD COLUMN acknowledged_source TEXT 
            CHECK (acknowledged_source IN ('HISTORIAN_UI', 'PLC_SIGNAL', NULL));
        
        COMMENT ON COLUMN historian_raw.historian_events.acknowledged_source IS 
        'Source of acknowledgment: HISTORIAN_UI (operator via web UI), PLC_SIGNAL (acknowledged at DCS/PLC panel)';
        
        RAISE NOTICE '✓ Column added successfully';
    ELSE
        RAISE NOTICE '✓ acknowledged_source column already exists';
    END IF;
END $$;

\echo ''
\echo 'Database schema ready for alarm acknowledgment tracking!'
\echo ''
