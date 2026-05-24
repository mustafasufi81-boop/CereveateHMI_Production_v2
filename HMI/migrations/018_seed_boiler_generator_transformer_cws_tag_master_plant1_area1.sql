-- 018_seed_boiler_generator_transformer_cws_tag_master_plant1_area1.sql
-- Seed realistic realtime tag metadata for Boiler, Generator, Transformer,
-- and CoolingWaterSystem under Plant1/Area1.

BEGIN;

WITH equipment_seed AS (
    SELECT *
    FROM (VALUES
        -- =========================
        -- BOILER
        -- =========================
        ('BOILER_DRUM_LEVEL_PCT', 'Boiler Drum Level', 'Boiler steam drum level', 'Plant1', 'Area1', 'Boiler1', 'double', '%', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('BOILER_MAIN_STEAM_PRESSURE_BAR', 'Boiler Main Steam Pressure', 'Boiler outlet main steam pressure', 'Plant1', 'Area1', 'Boiler1', 'double', 'bar', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('BOILER_MAIN_STEAM_TEMP_C', 'Boiler Main Steam Temperature', 'Boiler outlet main steam temperature', 'Plant1', 'Area1', 'Boiler1', 'double', 'C', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('BOILER_FEEDWATER_FLOW_TPH', 'Boiler Feedwater Flow', 'Feedwater flow to boiler', 'Plant1', 'Area1', 'Boiler1', 'double', 'TPH', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('BOILER_FURNACE_PRESSURE_KPA', 'Boiler Furnace Pressure', 'Boiler furnace draft pressure', 'Plant1', 'Area1', 'Boiler1', 'double', 'kPa', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('BOILER_O2_PCT', 'Boiler Flue Gas O2', 'Flue gas oxygen at boiler outlet', 'Plant1', 'Area1', 'Boiler1', 'double', '%', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('BOILER_ID_FAN_SPEED_RPM', 'Boiler ID Fan Speed', 'Induced draft fan speed', 'Plant1', 'Area1', 'Boiler1', 'double', 'RPM', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('BOILER_FD_FAN_SPEED_RPM', 'Boiler FD Fan Speed', 'Forced draft fan speed', 'Plant1', 'Area1', 'Boiler1', 'double', 'RPM', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('BOILER_TRIP_STATUS', 'Boiler Trip Status', 'Boiler protection trip status', 'Plant1', 'Area1', 'Boiler1', 'boolean', 'STATE', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('BOILER_RUN_STATUS', 'Boiler Run Status', 'Boiler running status', 'Plant1', 'Area1', 'Boiler1', 'boolean', 'STATE', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),

        -- =========================
        -- GENERATOR
        -- =========================
        ('GENERATOR_ACTIVE_POWER_MW', 'Generator Active Power', 'Generator active power output', 'Plant1', 'Area1', 'Generator1', 'double', 'MW', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('GENERATOR_REACTIVE_POWER_MVAR', 'Generator Reactive Power', 'Generator reactive power output', 'Plant1', 'Area1', 'Generator1', 'double', 'MVAR', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('GENERATOR_TERMINAL_VOLTAGE_KV', 'Generator Terminal Voltage', 'Generator terminal voltage', 'Plant1', 'Area1', 'Generator1', 'double', 'kV', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('GENERATOR_CURRENT_A', 'Generator Current', 'Generator stator current', 'Plant1', 'Area1', 'Generator1', 'double', 'A', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('GENERATOR_FREQUENCY_HZ', 'Generator Frequency', 'Generator output frequency', 'Plant1', 'Area1', 'Generator1', 'double', 'Hz', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('GENERATOR_POWER_FACTOR', 'Generator Power Factor', 'Generator power factor', 'Plant1', 'Area1', 'Generator1', 'double', 'PF', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('GENERATOR_STATOR_TEMP_C', 'Generator Stator Temperature', 'Generator stator winding temperature', 'Plant1', 'Area1', 'Generator1', 'double', 'C', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('GENERATOR_ROTOR_TEMP_C', 'Generator Rotor Temperature', 'Generator rotor temperature', 'Plant1', 'Area1', 'Generator1', 'double', 'C', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('GENERATOR_BREAKER_STATUS', 'Generator Breaker Status', 'Generator breaker close/open status', 'Plant1', 'Area1', 'Generator1', 'boolean', 'STATE', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('GENERATOR_RUN_STATUS', 'Generator Run Status', 'Generator running status', 'Plant1', 'Area1', 'Generator1', 'boolean', 'STATE', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),

        -- =========================
        -- TRANSFORMER
        -- =========================
        ('TRANSFORMER_HV_VOLTAGE_KV', 'Transformer HV Voltage', 'Transformer high-voltage side voltage', 'Plant1', 'Area1', 'Transformer1', 'double', 'kV', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('TRANSFORMER_LV_VOLTAGE_KV', 'Transformer LV Voltage', 'Transformer low-voltage side voltage', 'Plant1', 'Area1', 'Transformer1', 'double', 'kV', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('TRANSFORMER_HV_CURRENT_A', 'Transformer HV Current', 'Transformer high-voltage side current', 'Plant1', 'Area1', 'Transformer1', 'double', 'A', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('TRANSFORMER_LV_CURRENT_A', 'Transformer LV Current', 'Transformer low-voltage side current', 'Plant1', 'Area1', 'Transformer1', 'double', 'A', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('TRANSFORMER_OIL_TEMP_C', 'Transformer Oil Temperature', 'Transformer top oil temperature', 'Plant1', 'Area1', 'Transformer1', 'double', 'C', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('TRANSFORMER_WINDING_TEMP_C', 'Transformer Winding Temperature', 'Transformer winding hot spot temperature', 'Plant1', 'Area1', 'Transformer1', 'double', 'C', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('TRANSFORMER_LOAD_PCT', 'Transformer Load', 'Transformer loading in percent', 'Plant1', 'Area1', 'Transformer1', 'double', '%', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('TRANSFORMER_TAP_POSITION', 'Transformer Tap Position', 'On-load tap changer position', 'Plant1', 'Area1', 'Transformer1', 'double', 'STEP', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('TRANSFORMER_BUCHHOLZ_ALARM', 'Transformer Buchholz Alarm', 'Buchholz relay alarm status', 'Plant1', 'Area1', 'Transformer1', 'boolean', 'STATE', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('TRANSFORMER_TRIP_STATUS', 'Transformer Trip Status', 'Transformer trip status', 'Plant1', 'Area1', 'Transformer1', 'boolean', 'STATE', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),

        -- =========================
        -- COOLING WATER SYSTEM
        -- =========================
        ('CWS_PUMP_1_RUN_STATUS', 'Cooling Water Pump 1 Run Status', 'Cooling water pump 1 running status', 'Plant1', 'Area1', 'CoolingWaterSystem1', 'boolean', 'STATE', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('CWS_PUMP_2_RUN_STATUS', 'Cooling Water Pump 2 Run Status', 'Cooling water pump 2 running status', 'Plant1', 'Area1', 'CoolingWaterSystem1', 'boolean', 'STATE', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('CWS_HEADER_PRESSURE_BAR', 'Cooling Water Header Pressure', 'Cooling water header pressure', 'Plant1', 'Area1', 'CoolingWaterSystem1', 'double', 'bar', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('CWS_FLOW_TOTAL_M3H', 'Cooling Water Total Flow', 'Total cooling water flow', 'Plant1', 'Area1', 'CoolingWaterSystem1', 'double', 'm3/h', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('CWS_INLET_TEMP_C', 'Cooling Water Inlet Temperature', 'Cooling water inlet temperature', 'Plant1', 'Area1', 'CoolingWaterSystem1', 'double', 'C', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('CWS_OUTLET_TEMP_C', 'Cooling Water Outlet Temperature', 'Cooling water outlet temperature', 'Plant1', 'Area1', 'CoolingWaterSystem1', 'double', 'C', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('COOLING_TOWER_BASIN_LEVEL_PCT', 'Cooling Tower Basin Level', 'Cooling tower basin water level', 'Plant1', 'Area1', 'CoolingWaterSystem1', 'double', '%', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('COOLING_TOWER_FAN_1_RUN_STATUS', 'Cooling Tower Fan 1 Run Status', 'Cooling tower fan 1 running status', 'Plant1', 'Area1', 'CoolingWaterSystem1', 'boolean', 'STATE', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('COOLING_TOWER_FAN_2_RUN_STATUS', 'Cooling Tower Fan 2 Run Status', 'Cooling tower fan 2 running status', 'Plant1', 'Area1', 'CoolingWaterSystem1', 'boolean', 'STATE', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018'),
        ('CWS_DELTA_TEMP_C', 'Cooling Water Delta Temperature', 'Cooling water return-supply temperature difference', 'Plant1', 'Area1', 'CoolingWaterSystem1', 'double', 'C', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_018')
    ) AS v(
        tag_id,
        tag_name,
        description,
        plant,
        area,
        equipment,
        data_type,
        eng_unit,
        db_logging_interval_ms,
        enabled,
        db_table_name,
        created_by
    )
)
INSERT INTO historian_meta.tag_master (
    tag_id,
    tag_name,
    description,
    plant,
    area,
    equipment,
    sub_equipment,
    components,
    data_type,
    eng_unit,
    db_logging_interval_ms,
    enabled,
    db_table_name,
    mapping_version,
    config_updated_at,
    created_at,
    created_by
)
SELECT
    es.tag_id,
    es.tag_name,
    es.description,
    es.plant,
    es.area,
    es.equipment,
    CASE
        WHEN es.tag_id LIKE 'BOILER_%' THEN
            CASE
                WHEN es.tag_id IN ('BOILER_ID_FAN_SPEED_RPM', 'BOILER_FD_FAN_SPEED_RPM') THEN 'Draft Fans'
                WHEN es.tag_id IN ('BOILER_TRIP_STATUS', 'BOILER_RUN_STATUS') THEN 'Boiler Protection'
                ELSE 'Boiler Process'
            END
        WHEN es.tag_id LIKE 'GENERATOR_%' THEN
            CASE
                WHEN es.tag_id IN ('GENERATOR_STATOR_TEMP_C', 'GENERATOR_ROTOR_TEMP_C') THEN 'Thermal Monitoring'
                WHEN es.tag_id IN ('GENERATOR_BREAKER_STATUS', 'GENERATOR_RUN_STATUS') THEN 'Generator Protection'
                ELSE 'Electrical Measurements'
            END
        WHEN es.tag_id LIKE 'TRANSFORMER_%' THEN
            CASE
                WHEN es.tag_id IN ('TRANSFORMER_OIL_TEMP_C', 'TRANSFORMER_WINDING_TEMP_C') THEN 'Thermal Monitoring'
                WHEN es.tag_id = 'TRANSFORMER_TAP_POSITION' THEN 'Tap Changer'
                WHEN es.tag_id IN ('TRANSFORMER_BUCHHOLZ_ALARM', 'TRANSFORMER_TRIP_STATUS') THEN 'Transformer Protection'
                ELSE 'Electrical Measurements'
            END
        WHEN es.tag_id LIKE 'CWS_%' OR es.tag_id LIKE 'COOLING_TOWER_%' THEN
            CASE
                WHEN es.tag_id IN ('CWS_PUMP_1_RUN_STATUS', 'CWS_PUMP_2_RUN_STATUS') THEN 'Pumps'
                WHEN es.tag_id IN ('COOLING_TOWER_FAN_1_RUN_STATUS', 'COOLING_TOWER_FAN_2_RUN_STATUS', 'COOLING_TOWER_BASIN_LEVEL_PCT') THEN 'Cooling Tower'
                WHEN es.tag_id IN ('CWS_INLET_TEMP_C', 'CWS_OUTLET_TEMP_C', 'CWS_DELTA_TEMP_C') THEN 'Thermal Monitoring'
                ELSE 'Header Network'
            END
        ELSE 'General'
    END,
    CASE
        WHEN es.tag_id = 'BOILER_DRUM_LEVEL_PCT' THEN 'Steam Drum Level Sensor'
        WHEN es.tag_id = 'BOILER_MAIN_STEAM_PRESSURE_BAR' THEN 'Main Steam Pressure Transmitter'
        WHEN es.tag_id = 'BOILER_MAIN_STEAM_TEMP_C' THEN 'Main Steam Temperature Sensor'
        WHEN es.tag_id = 'BOILER_FEEDWATER_FLOW_TPH' THEN 'Feedwater Flow Transmitter'
        WHEN es.tag_id = 'BOILER_FURNACE_PRESSURE_KPA' THEN 'Furnace Pressure Transmitter'
        WHEN es.tag_id = 'BOILER_O2_PCT' THEN 'Flue Gas O2 Analyzer'
        WHEN es.tag_id = 'BOILER_ID_FAN_SPEED_RPM' THEN 'ID Fan Speed Sensor'
        WHEN es.tag_id = 'BOILER_FD_FAN_SPEED_RPM' THEN 'FD Fan Speed Sensor'
        WHEN es.tag_id = 'BOILER_TRIP_STATUS' THEN 'Boiler Trip Relay'
        WHEN es.tag_id = 'BOILER_RUN_STATUS' THEN 'Boiler Run Feedback'

        WHEN es.tag_id = 'GENERATOR_ACTIVE_POWER_MW' THEN 'Power Meter'
        WHEN es.tag_id = 'GENERATOR_REACTIVE_POWER_MVAR' THEN 'Reactive Power Meter'
        WHEN es.tag_id = 'GENERATOR_TERMINAL_VOLTAGE_KV' THEN 'Voltage Transducer'
        WHEN es.tag_id = 'GENERATOR_CURRENT_A' THEN 'Current Transformer'
        WHEN es.tag_id = 'GENERATOR_FREQUENCY_HZ' THEN 'Frequency Meter'
        WHEN es.tag_id = 'GENERATOR_POWER_FACTOR' THEN 'Power Factor Meter'
        WHEN es.tag_id = 'GENERATOR_STATOR_TEMP_C' THEN 'Stator Temperature Sensor'
        WHEN es.tag_id = 'GENERATOR_ROTOR_TEMP_C' THEN 'Rotor Temperature Sensor'
        WHEN es.tag_id = 'GENERATOR_BREAKER_STATUS' THEN 'Generator Breaker Status Contact'
        WHEN es.tag_id = 'GENERATOR_RUN_STATUS' THEN 'Generator Run Feedback'

        WHEN es.tag_id = 'TRANSFORMER_HV_VOLTAGE_KV' THEN 'HV Voltage Transducer'
        WHEN es.tag_id = 'TRANSFORMER_LV_VOLTAGE_KV' THEN 'LV Voltage Transducer'
        WHEN es.tag_id = 'TRANSFORMER_HV_CURRENT_A' THEN 'HV Current Transformer'
        WHEN es.tag_id = 'TRANSFORMER_LV_CURRENT_A' THEN 'LV Current Transformer'
        WHEN es.tag_id = 'TRANSFORMER_OIL_TEMP_C' THEN 'Oil Temperature Sensor'
        WHEN es.tag_id = 'TRANSFORMER_WINDING_TEMP_C' THEN 'Winding Temperature Sensor'
        WHEN es.tag_id = 'TRANSFORMER_LOAD_PCT' THEN 'Transformer Load Calculator'
        WHEN es.tag_id = 'TRANSFORMER_TAP_POSITION' THEN 'Tap Position Indicator'
        WHEN es.tag_id = 'TRANSFORMER_BUCHHOLZ_ALARM' THEN 'Buchholz Relay Alarm Contact'
        WHEN es.tag_id = 'TRANSFORMER_TRIP_STATUS' THEN 'Transformer Trip Relay'

        WHEN es.tag_id = 'CWS_PUMP_1_RUN_STATUS' THEN 'Pump-1 Run Feedback'
        WHEN es.tag_id = 'CWS_PUMP_2_RUN_STATUS' THEN 'Pump-2 Run Feedback'
        WHEN es.tag_id = 'CWS_HEADER_PRESSURE_BAR' THEN 'Header Pressure Transmitter'
        WHEN es.tag_id = 'CWS_FLOW_TOTAL_M3H' THEN 'Total Flow Meter'
        WHEN es.tag_id = 'CWS_INLET_TEMP_C' THEN 'Inlet Temperature Sensor'
        WHEN es.tag_id = 'CWS_OUTLET_TEMP_C' THEN 'Outlet Temperature Sensor'
        WHEN es.tag_id = 'COOLING_TOWER_BASIN_LEVEL_PCT' THEN 'Basin Level Transmitter'
        WHEN es.tag_id = 'COOLING_TOWER_FAN_1_RUN_STATUS' THEN 'Cooling Tower Fan-1 Feedback'
        WHEN es.tag_id = 'COOLING_TOWER_FAN_2_RUN_STATUS' THEN 'Cooling Tower Fan-2 Feedback'
        WHEN es.tag_id = 'CWS_DELTA_TEMP_C' THEN 'Delta Temperature Calculator'
        ELSE es.tag_name
    END,
    LOWER(es.data_type),
    es.eng_unit,
    es.db_logging_interval_ms,
    es.enabled,
    es.db_table_name,
    1,
    NOW(),
    NOW(),
    es.created_by
FROM equipment_seed es
ON CONFLICT (tag_id)
DO UPDATE SET
    tag_name = EXCLUDED.tag_name,
    description = EXCLUDED.description,
    plant = EXCLUDED.plant,
    area = EXCLUDED.area,
    equipment = EXCLUDED.equipment,
    sub_equipment = EXCLUDED.sub_equipment,
    components = EXCLUDED.components,
    data_type = EXCLUDED.data_type,
    eng_unit = EXCLUDED.eng_unit,
    db_logging_interval_ms = EXCLUDED.db_logging_interval_ms,
    enabled = EXCLUDED.enabled,
    db_table_name = EXCLUDED.db_table_name,
    config_updated_at = NOW();

COMMIT;
