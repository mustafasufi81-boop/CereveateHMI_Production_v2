-- ============================================================
-- ALARM SETPOINTS ENABLE SCRIPT
-- Purpose : Enable alarm_enabled = true + populate alarm_hh/h/l/ll_limit
--           for tags that have setpoints defined (new or old columns)
-- Run in  : pgAdmin or psql against Automation_DB
-- Date    : 2026-05-09
-- ============================================================

-- ============================================================
-- SECTION 1 : Matrikon OPC Simulation tags (for alarm system testing)
-- These are live OPC tags connected to Matrikon.OPC.Simulation.1
-- Limits chosen to trigger frequently so the alarm panel can be tested.
-- ============================================================

-- Random.Int4  — Matrikon random signed 32-bit integer (full range)
-- Set H/HH at values that will fire ~50% of the time
UPDATE historian_meta.tag_master SET
    alarm_enabled    = true,
    alarm_hh_limit   = 1500000000,
    alarm_h_limit    = 500000000,
    alarm_l_limit    = -500000000,
    alarm_ll_limit   = -1500000000,
    alarm_priority   = 2,
    alarm_deadband   = 1000000,
    config_updated_at = NOW()
WHERE tag_id = 'Random.Int4';

-- Random.Real8  — Matrikon random double (0.0 – 1.0 range)
UPDATE historian_meta.tag_master SET
    alarm_enabled    = true,
    alarm_hh_limit   = 0.95,
    alarm_h_limit    = 0.80,
    alarm_l_limit    = 0.20,
    alarm_ll_limit   = 0.05,
    alarm_priority   = 2,
    alarm_deadband   = 0.01,
    config_updated_at = NOW()
WHERE tag_id = 'Random.Real8';

-- Random.Real4  — already alarm_enabled=true; setpoints populated by previous config.
-- Keeping as-is (HH=25000, H=20000, L=500, LL=100)

-- Triangle Waves.Int4  — sawtooth/triangle 0–100 range
UPDATE historian_meta.tag_master SET
    alarm_enabled    = true,
    alarm_hh_limit   = 95,
    alarm_h_limit    = 80,
    alarm_l_limit    = 20,
    alarm_ll_limit   = 5,
    alarm_priority   = 3,
    alarm_deadband   = 1,
    config_updated_at = NOW()
WHERE tag_id = 'Triangle Waves.Int4';

-- Triangle Waves.Real4 — already alarm_enabled=true; setpoints OK (HH=500, H=450, L=25, LL=5)

-- Triangle Waves.Real8  — continuous 0–100 wave
UPDATE historian_meta.tag_master SET
    alarm_enabled    = true,
    alarm_hh_limit   = 95,
    alarm_h_limit    = 80,
    alarm_l_limit    = 20,
    alarm_ll_limit   = 5,
    alarm_priority   = 3,
    alarm_deadband   = 1,
    config_updated_at = NOW()
WHERE tag_id = 'Triangle Waves.Real8';

-- Bucket Brigade.Real8  — user-writeable value 0–100
UPDATE historian_meta.tag_master SET
    alarm_enabled    = true,
    alarm_hh_limit   = 90,
    alarm_h_limit    = 75,
    alarm_l_limit    = 25,
    alarm_ll_limit   = 10,
    alarm_priority   = 3,
    alarm_deadband   = 1,
    config_updated_at = NOW()
WHERE tag_id = 'Bucket Brigade.Real8';

-- ============================================================
-- SECTION 2 : PLC/Process tags — copy old threshold columns → new columns
-- These tags have values in alarm_high_threshold / alarm_high_high_threshold
-- but alarm_enabled is still FALSE.  Migrate them in bulk.
-- ============================================================

UPDATE historian_meta.tag_master SET
    alarm_enabled     = true,
    alarm_hh_limit    = COALESCE(alarm_hh_limit,   alarm_high_high_threshold),
    alarm_h_limit     = COALESCE(alarm_h_limit,    alarm_high_threshold),
    alarm_l_limit     = COALESCE(alarm_l_limit,    alarm_low_threshold),
    alarm_ll_limit    = COALESCE(alarm_ll_limit,   alarm_low_low_threshold),
    config_updated_at = NOW()
WHERE alarm_enabled = false
  AND data_type IN ('double', 'integer', 'int')
  AND (
        alarm_high_threshold      IS NOT NULL
     OR alarm_high_high_threshold IS NOT NULL
     OR alarm_low_threshold       IS NOT NULL
     OR alarm_low_low_threshold   IS NOT NULL
  );

-- ============================================================
-- SECTION 3 : Key process tags — explicit setpoints
--             (tags that had no old columns but warrant alarms)
-- ============================================================

-- BOILER_DRUM_LEVEL_PCT  (0-100 %)
UPDATE historian_meta.tag_master SET
    alarm_enabled    = true,
    alarm_hh_limit   = 90,
    alarm_h_limit    = 80,
    alarm_l_limit    = 20,
    alarm_ll_limit   = 10,
    alarm_priority   = 2,
    alarm_deadband   = 1,
    config_updated_at = NOW()
WHERE tag_id = 'BOILER_DRUM_LEVEL_PCT' AND alarm_enabled = false;

-- BOILER_MAIN_STEAM_PRESSURE_BAR  (typical 0-200 bar)
UPDATE historian_meta.tag_master SET
    alarm_enabled    = true,
    alarm_hh_limit   = 185,
    alarm_h_limit    = 175,
    alarm_l_limit    = 80,
    alarm_ll_limit   = 60,
    alarm_priority   = 1,
    alarm_deadband   = 1,
    config_updated_at = NOW()
WHERE tag_id = 'BOILER_MAIN_STEAM_PRESSURE_BAR' AND alarm_enabled = false;

-- BOILER_MAIN_STEAM_TEMP_C  (typical 0-600 °C)
UPDATE historian_meta.tag_master SET
    alarm_enabled    = true,
    alarm_hh_limit   = 560,
    alarm_h_limit    = 545,
    alarm_l_limit    = 450,
    alarm_ll_limit   = 430,
    alarm_priority   = 1,
    alarm_deadband   = 2,
    config_updated_at = NOW()
WHERE tag_id = 'BOILER_MAIN_STEAM_TEMP_C' AND alarm_enabled = false;

-- BOILER_FURNACE_PRESSURE_KPA  (draft; negative normal, high positive = puff-back risk)
UPDATE historian_meta.tag_master SET
    alarm_enabled    = true,
    alarm_hh_limit   = 0.5,
    alarm_h_limit    = 0.2,
    alarm_l_limit    = -2.0,
    alarm_ll_limit   = -2.5,
    alarm_priority   = 2,
    alarm_deadband   = 0.05,
    config_updated_at = NOW()
WHERE tag_id = 'BOILER_FURNACE_PRESSURE_KPA' AND alarm_enabled = false;

-- BOILER_O2_PCT  (flue gas O2; low = rich combustion, high = excess air)
UPDATE historian_meta.tag_master SET
    alarm_enabled    = true,
    alarm_hh_limit   = 8.0,
    alarm_h_limit    = 6.0,
    alarm_l_limit    = 2.0,
    alarm_ll_limit   = 1.0,
    alarm_priority   = 3,
    alarm_deadband   = 0.1,
    config_updated_at = NOW()
WHERE tag_id = 'BOILER_O2_PCT' AND alarm_enabled = false;

-- BOILER_FEEDWATER_FLOW_TPH
UPDATE historian_meta.tag_master SET
    alarm_enabled    = true,
    alarm_hh_limit   = 1900,
    alarm_h_limit    = 1800,
    alarm_l_limit    = 200,
    alarm_ll_limit   = 100,
    alarm_priority   = 2,
    alarm_deadband   = 5,
    config_updated_at = NOW()
WHERE tag_id = 'BOILER_FEEDWATER_FLOW_TPH' AND alarm_enabled = false;

-- BOILER_ID_FAN_SPEED_RPM
UPDATE historian_meta.tag_master SET
    alarm_enabled    = true,
    alarm_hh_limit   = 1500,
    alarm_h_limit    = 1450,
    alarm_l_limit    = 500,
    alarm_ll_limit   = 300,
    alarm_priority   = 2,
    alarm_deadband   = 10,
    config_updated_at = NOW()
WHERE tag_id = 'BOILER_ID_FAN_SPEED_RPM' AND alarm_enabled = false;

-- BOILER_FD_FAN_SPEED_RPM
UPDATE historian_meta.tag_master SET
    alarm_enabled    = true,
    alarm_hh_limit   = 1500,
    alarm_h_limit    = 1450,
    alarm_l_limit    = 500,
    alarm_ll_limit   = 300,
    alarm_priority   = 2,
    alarm_deadband   = 10,
    config_updated_at = NOW()
WHERE tag_id = 'BOILER_FD_FAN_SPEED_RPM' AND alarm_enabled = false;

-- GENERATOR_TERMINAL_VOLTAGE_KV
UPDATE historian_meta.tag_master SET
    alarm_enabled    = true,
    alarm_hh_limit   = 21.0,
    alarm_h_limit    = 20.5,
    alarm_l_limit    = 19.5,
    alarm_ll_limit   = 19.0,
    alarm_priority   = 1,
    alarm_deadband   = 0.05,
    config_updated_at = NOW()
WHERE tag_id = 'GENERATOR_TERMINAL_VOLTAGE_KV' AND alarm_enabled = false;

-- GENERATOR_FREQUENCY_HZ
UPDATE historian_meta.tag_master SET
    alarm_enabled    = true,
    alarm_hh_limit   = 50.5,
    alarm_h_limit    = 50.3,
    alarm_l_limit    = 49.7,
    alarm_ll_limit   = 49.5,
    alarm_priority   = 1,
    alarm_deadband   = 0.02,
    config_updated_at = NOW()
WHERE tag_id = 'GENERATOR_FREQUENCY_HZ' AND alarm_enabled = false;

-- GENERATOR_ACTIVE_POWER_MW
UPDATE historian_meta.tag_master SET
    alarm_enabled    = true,
    alarm_hh_limit   = 540,
    alarm_h_limit    = 500,
    alarm_l_limit    = 50,
    alarm_ll_limit   = 20,
    alarm_priority   = 2,
    alarm_deadband   = 2,
    config_updated_at = NOW()
WHERE tag_id = 'GENERATOR_ACTIVE_POWER_MW' AND alarm_enabled = false;

-- GENERATOR_STATOR_TEMP_C
UPDATE historian_meta.tag_master SET
    alarm_enabled    = true,
    alarm_hh_limit   = 135,
    alarm_h_limit    = 120,
    alarm_priority   = 1,
    alarm_deadband   = 1,
    config_updated_at = NOW()
WHERE tag_id = 'GENERATOR_STATOR_TEMP_C' AND alarm_enabled = false;

-- GENERATOR_ROTOR_TEMP_C
UPDATE historian_meta.tag_master SET
    alarm_enabled    = true,
    alarm_hh_limit   = 125,
    alarm_h_limit    = 110,
    alarm_priority   = 1,
    alarm_deadband   = 1,
    config_updated_at = NOW()
WHERE tag_id = 'GENERATOR_ROTOR_TEMP_C' AND alarm_enabled = false;

-- TRANSFORMER_OIL_TEMP_C  (typical trip at 110 °C)
UPDATE historian_meta.tag_master SET
    alarm_enabled    = true,
    alarm_hh_limit   = 105,
    alarm_h_limit    = 95,
    alarm_priority   = 1,
    alarm_deadband   = 1,
    config_updated_at = NOW()
WHERE tag_id = 'TRANSFORMER_OIL_TEMP_C' AND alarm_enabled = false;

-- TRANSFORMER_WINDING_TEMP_C  (hot-spot; IEC 60076 trip ~140 °C)
UPDATE historian_meta.tag_master SET
    alarm_enabled    = true,
    alarm_hh_limit   = 140,
    alarm_h_limit    = 120,
    alarm_priority   = 1,
    alarm_deadband   = 1,
    config_updated_at = NOW()
WHERE tag_id = 'TRANSFORMER_WINDING_TEMP_C' AND alarm_enabled = false;

-- TRANSFORMER_LOAD_PCT
UPDATE historian_meta.tag_master SET
    alarm_enabled    = true,
    alarm_hh_limit   = 110,
    alarm_h_limit    = 100,
    alarm_l_limit    = NULL,
    alarm_ll_limit   = NULL,
    alarm_priority   = 2,
    alarm_deadband   = 1,
    config_updated_at = NOW()
WHERE tag_id = 'TRANSFORMER_LOAD_PCT' AND alarm_enabled = false;

-- CWS_HEADER_PRESSURE_BAR
UPDATE historian_meta.tag_master SET
    alarm_enabled    = true,
    alarm_hh_limit   = 8.0,
    alarm_h_limit    = 7.5,
    alarm_l_limit    = 3.0,
    alarm_ll_limit   = 2.5,
    alarm_priority   = 2,
    alarm_deadband   = 0.1,
    config_updated_at = NOW()
WHERE tag_id = 'CWS_HEADER_PRESSURE_BAR' AND alarm_enabled = false;

-- COOLING_TOWER_BASIN_LEVEL_PCT
UPDATE historian_meta.tag_master SET
    alarm_enabled    = true,
    alarm_hh_limit   = 90,
    alarm_h_limit    = 85,
    alarm_l_limit    = 20,
    alarm_ll_limit   = 10,
    alarm_priority   = 3,
    alarm_deadband   = 1,
    config_updated_at = NOW()
WHERE tag_id = 'COOLING_TOWER_BASIN_LEVEL_PCT' AND alarm_enabled = false;

-- ============================================================
-- SECTION 4 : Verification query
-- Run after all UPDATEs to confirm rows enabled
-- ============================================================
SELECT
    tag_id,
    tag_name,
    alarm_enabled,
    alarm_hh_limit,
    alarm_h_limit,
    alarm_l_limit,
    alarm_ll_limit,
    alarm_priority,
    alarm_deadband
FROM historian_meta.tag_master
WHERE alarm_enabled = true
ORDER BY alarm_priority, tag_id;
