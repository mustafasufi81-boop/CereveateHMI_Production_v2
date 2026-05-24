-- 020_backfill_sub_equipment_components_for_018_tags.sql
-- Backfill hierarchy fields for tags seeded in migration 018.

BEGIN;

UPDATE historian_meta.tag_master tm
SET
    sub_equipment = CASE
        WHEN tm.tag_id LIKE 'BOILER_%' THEN
            CASE
                WHEN tm.tag_id IN ('BOILER_ID_FAN_SPEED_RPM', 'BOILER_FD_FAN_SPEED_RPM') THEN 'Draft Fans'
                WHEN tm.tag_id IN ('BOILER_TRIP_STATUS', 'BOILER_RUN_STATUS') THEN 'Boiler Protection'
                ELSE 'Boiler Process'
            END
        WHEN tm.tag_id LIKE 'GENERATOR_%' THEN
            CASE
                WHEN tm.tag_id IN ('GENERATOR_STATOR_TEMP_C', 'GENERATOR_ROTOR_TEMP_C') THEN 'Thermal Monitoring'
                WHEN tm.tag_id IN ('GENERATOR_BREAKER_STATUS', 'GENERATOR_RUN_STATUS') THEN 'Generator Protection'
                ELSE 'Electrical Measurements'
            END
        WHEN tm.tag_id LIKE 'TRANSFORMER_%' THEN
            CASE
                WHEN tm.tag_id IN ('TRANSFORMER_OIL_TEMP_C', 'TRANSFORMER_WINDING_TEMP_C') THEN 'Thermal Monitoring'
                WHEN tm.tag_id = 'TRANSFORMER_TAP_POSITION' THEN 'Tap Changer'
                WHEN tm.tag_id IN ('TRANSFORMER_BUCHHOLZ_ALARM', 'TRANSFORMER_TRIP_STATUS') THEN 'Transformer Protection'
                ELSE 'Electrical Measurements'
            END
        WHEN tm.tag_id LIKE 'CWS_%' OR tm.tag_id LIKE 'COOLING_TOWER_%' THEN
            CASE
                WHEN tm.tag_id IN ('CWS_PUMP_1_RUN_STATUS', 'CWS_PUMP_2_RUN_STATUS') THEN 'Pumps'
                WHEN tm.tag_id IN ('COOLING_TOWER_FAN_1_RUN_STATUS', 'COOLING_TOWER_FAN_2_RUN_STATUS', 'COOLING_TOWER_BASIN_LEVEL_PCT') THEN 'Cooling Tower'
                WHEN tm.tag_id IN ('CWS_INLET_TEMP_C', 'CWS_OUTLET_TEMP_C', 'CWS_DELTA_TEMP_C') THEN 'Thermal Monitoring'
                ELSE 'Header Network'
            END
        ELSE tm.sub_equipment
    END,
    components = CASE
        WHEN tm.tag_id = 'BOILER_DRUM_LEVEL_PCT' THEN 'Steam Drum Level Sensor'
        WHEN tm.tag_id = 'BOILER_MAIN_STEAM_PRESSURE_BAR' THEN 'Main Steam Pressure Transmitter'
        WHEN tm.tag_id = 'BOILER_MAIN_STEAM_TEMP_C' THEN 'Main Steam Temperature Sensor'
        WHEN tm.tag_id = 'BOILER_FEEDWATER_FLOW_TPH' THEN 'Feedwater Flow Transmitter'
        WHEN tm.tag_id = 'BOILER_FURNACE_PRESSURE_KPA' THEN 'Furnace Pressure Transmitter'
        WHEN tm.tag_id = 'BOILER_O2_PCT' THEN 'Flue Gas O2 Analyzer'
        WHEN tm.tag_id = 'BOILER_ID_FAN_SPEED_RPM' THEN 'ID Fan Speed Sensor'
        WHEN tm.tag_id = 'BOILER_FD_FAN_SPEED_RPM' THEN 'FD Fan Speed Sensor'
        WHEN tm.tag_id = 'BOILER_TRIP_STATUS' THEN 'Boiler Trip Relay'
        WHEN tm.tag_id = 'BOILER_RUN_STATUS' THEN 'Boiler Run Feedback'

        WHEN tm.tag_id = 'GENERATOR_ACTIVE_POWER_MW' THEN 'Power Meter'
        WHEN tm.tag_id = 'GENERATOR_REACTIVE_POWER_MVAR' THEN 'Reactive Power Meter'
        WHEN tm.tag_id = 'GENERATOR_TERMINAL_VOLTAGE_KV' THEN 'Voltage Transducer'
        WHEN tm.tag_id = 'GENERATOR_CURRENT_A' THEN 'Current Transformer'
        WHEN tm.tag_id = 'GENERATOR_FREQUENCY_HZ' THEN 'Frequency Meter'
        WHEN tm.tag_id = 'GENERATOR_POWER_FACTOR' THEN 'Power Factor Meter'
        WHEN tm.tag_id = 'GENERATOR_STATOR_TEMP_C' THEN 'Stator Temperature Sensor'
        WHEN tm.tag_id = 'GENERATOR_ROTOR_TEMP_C' THEN 'Rotor Temperature Sensor'
        WHEN tm.tag_id = 'GENERATOR_BREAKER_STATUS' THEN 'Generator Breaker Status Contact'
        WHEN tm.tag_id = 'GENERATOR_RUN_STATUS' THEN 'Generator Run Feedback'

        WHEN tm.tag_id = 'TRANSFORMER_HV_VOLTAGE_KV' THEN 'HV Voltage Transducer'
        WHEN tm.tag_id = 'TRANSFORMER_LV_VOLTAGE_KV' THEN 'LV Voltage Transducer'
        WHEN tm.tag_id = 'TRANSFORMER_HV_CURRENT_A' THEN 'HV Current Transformer'
        WHEN tm.tag_id = 'TRANSFORMER_LV_CURRENT_A' THEN 'LV Current Transformer'
        WHEN tm.tag_id = 'TRANSFORMER_OIL_TEMP_C' THEN 'Oil Temperature Sensor'
        WHEN tm.tag_id = 'TRANSFORMER_WINDING_TEMP_C' THEN 'Winding Temperature Sensor'
        WHEN tm.tag_id = 'TRANSFORMER_LOAD_PCT' THEN 'Transformer Load Calculator'
        WHEN tm.tag_id = 'TRANSFORMER_TAP_POSITION' THEN 'Tap Position Indicator'
        WHEN tm.tag_id = 'TRANSFORMER_BUCHHOLZ_ALARM' THEN 'Buchholz Relay Alarm Contact'
        WHEN tm.tag_id = 'TRANSFORMER_TRIP_STATUS' THEN 'Transformer Trip Relay'

        WHEN tm.tag_id = 'CWS_PUMP_1_RUN_STATUS' THEN 'Pump-1 Run Feedback'
        WHEN tm.tag_id = 'CWS_PUMP_2_RUN_STATUS' THEN 'Pump-2 Run Feedback'
        WHEN tm.tag_id = 'CWS_HEADER_PRESSURE_BAR' THEN 'Header Pressure Transmitter'
        WHEN tm.tag_id = 'CWS_FLOW_TOTAL_M3H' THEN 'Total Flow Meter'
        WHEN tm.tag_id = 'CWS_INLET_TEMP_C' THEN 'Inlet Temperature Sensor'
        WHEN tm.tag_id = 'CWS_OUTLET_TEMP_C' THEN 'Outlet Temperature Sensor'
        WHEN tm.tag_id = 'COOLING_TOWER_BASIN_LEVEL_PCT' THEN 'Basin Level Transmitter'
        WHEN tm.tag_id = 'COOLING_TOWER_FAN_1_RUN_STATUS' THEN 'Cooling Tower Fan-1 Feedback'
        WHEN tm.tag_id = 'COOLING_TOWER_FAN_2_RUN_STATUS' THEN 'Cooling Tower Fan-2 Feedback'
        WHEN tm.tag_id = 'CWS_DELTA_TEMP_C' THEN 'Delta Temperature Calculator'
        ELSE tm.components
    END,
    config_updated_at = NOW()
WHERE tm.tag_id IN (
    'BOILER_DRUM_LEVEL_PCT',
    'BOILER_MAIN_STEAM_PRESSURE_BAR',
    'BOILER_MAIN_STEAM_TEMP_C',
    'BOILER_FEEDWATER_FLOW_TPH',
    'BOILER_FURNACE_PRESSURE_KPA',
    'BOILER_O2_PCT',
    'BOILER_ID_FAN_SPEED_RPM',
    'BOILER_FD_FAN_SPEED_RPM',
    'BOILER_TRIP_STATUS',
    'BOILER_RUN_STATUS',
    'GENERATOR_ACTIVE_POWER_MW',
    'GENERATOR_REACTIVE_POWER_MVAR',
    'GENERATOR_TERMINAL_VOLTAGE_KV',
    'GENERATOR_CURRENT_A',
    'GENERATOR_FREQUENCY_HZ',
    'GENERATOR_POWER_FACTOR',
    'GENERATOR_STATOR_TEMP_C',
    'GENERATOR_ROTOR_TEMP_C',
    'GENERATOR_BREAKER_STATUS',
    'GENERATOR_RUN_STATUS',
    'TRANSFORMER_HV_VOLTAGE_KV',
    'TRANSFORMER_LV_VOLTAGE_KV',
    'TRANSFORMER_HV_CURRENT_A',
    'TRANSFORMER_LV_CURRENT_A',
    'TRANSFORMER_OIL_TEMP_C',
    'TRANSFORMER_WINDING_TEMP_C',
    'TRANSFORMER_LOAD_PCT',
    'TRANSFORMER_TAP_POSITION',
    'TRANSFORMER_BUCHHOLZ_ALARM',
    'TRANSFORMER_TRIP_STATUS',
    'CWS_PUMP_1_RUN_STATUS',
    'CWS_PUMP_2_RUN_STATUS',
    'CWS_HEADER_PRESSURE_BAR',
    'CWS_FLOW_TOTAL_M3H',
    'CWS_INLET_TEMP_C',
    'CWS_OUTLET_TEMP_C',
    'COOLING_TOWER_BASIN_LEVEL_PCT',
    'COOLING_TOWER_FAN_1_RUN_STATUS',
    'COOLING_TOWER_FAN_2_RUN_STATUS',
    'CWS_DELTA_TEMP_C'
);

COMMIT;
