-- 021_backfill_powerplant_realtime_hierarchy_for_018_tags.sql
-- Apply power-plant realtime hierarchy naming for tags seeded in migration 018.

BEGIN;

WITH tag_map AS (
    SELECT *
    FROM (VALUES
        -- BOILER
        ('BOILER_DRUM_LEVEL_PCT', 'Steam Drum', 'LT-101 Drum Level Transmitter'),
        ('BOILER_MAIN_STEAM_PRESSURE_BAR', 'Main Steam Line', 'PT-201 Main Steam Pressure Transmitter'),
        ('BOILER_MAIN_STEAM_TEMP_C', 'Main Steam Line', 'TT-202 Main Steam Temperature Transmitter'),
        ('BOILER_FEEDWATER_FLOW_TPH', 'Feedwater System', 'FT-301 Feedwater Flow Transmitter'),
        ('BOILER_FURNACE_PRESSURE_KPA', 'Furnace Draft', 'PT-401 Furnace Draft Pressure Transmitter'),
        ('BOILER_O2_PCT', 'Flue Gas Path', 'AIT-501 Flue Gas O2 Analyzer'),
        ('BOILER_ID_FAN_SPEED_RPM', 'ID Fan', 'ST-601 ID Fan Speed Transmitter'),
        ('BOILER_FD_FAN_SPEED_RPM', 'FD Fan', 'ST-602 FD Fan Speed Transmitter'),
        ('BOILER_TRIP_STATUS', 'Boiler Protection', 'TRIP-901 Boiler Master Trip Relay Status'),
        ('BOILER_RUN_STATUS', 'Boiler Protection', 'RUN-902 Boiler Run Feedback Contact'),

        -- GENERATOR
        ('GENERATOR_ACTIVE_POWER_MW', 'Generator Electrical', 'PM-101 Active Power Meter'),
        ('GENERATOR_REACTIVE_POWER_MVAR', 'Generator Electrical', 'QM-102 Reactive Power Meter'),
        ('GENERATOR_TERMINAL_VOLTAGE_KV', 'Generator Electrical', 'VT-103 Terminal Voltage Transducer'),
        ('GENERATOR_CURRENT_A', 'Generator Electrical', 'CT-104 Stator Current Transformer'),
        ('GENERATOR_FREQUENCY_HZ', 'Generator Electrical', 'FM-105 Frequency Meter'),
        ('GENERATOR_POWER_FACTOR', 'Generator Electrical', 'PFM-106 Power Factor Meter'),
        ('GENERATOR_STATOR_TEMP_C', 'Stator Winding', 'TT-107 Stator RTD'),
        ('GENERATOR_ROTOR_TEMP_C', 'Rotor Winding', 'TT-108 Rotor RTD'),
        ('GENERATOR_BREAKER_STATUS', 'Generator Protection', '52G Generator Breaker Position Contact'),
        ('GENERATOR_RUN_STATUS', 'Generator Protection', 'RUN-109 Generator Run Feedback Contact'),

        -- TRANSFORMER
        ('TRANSFORMER_HV_VOLTAGE_KV', 'HV Side', 'VT-201 HV Voltage Transducer'),
        ('TRANSFORMER_LV_VOLTAGE_KV', 'LV Side', 'VT-202 LV Voltage Transducer'),
        ('TRANSFORMER_HV_CURRENT_A', 'HV Side', 'CT-203 HV Current Transformer'),
        ('TRANSFORMER_LV_CURRENT_A', 'LV Side', 'CT-204 LV Current Transformer'),
        ('TRANSFORMER_OIL_TEMP_C', 'Oil System', 'TT-205 Top Oil Temperature Sensor'),
        ('TRANSFORMER_WINDING_TEMP_C', 'Winding Monitoring', 'TT-206 Winding Hotspot Sensor'),
        ('TRANSFORMER_LOAD_PCT', 'Loading Monitoring', 'LD-207 Transformer Loading Calculator'),
        ('TRANSFORMER_TAP_POSITION', 'On-Load Tap Changer', 'TP-208 Tap Position Indicator'),
        ('TRANSFORMER_BUCHHOLZ_ALARM', 'Transformer Protection', '63 Buchholz Relay Alarm Contact'),
        ('TRANSFORMER_TRIP_STATUS', 'Transformer Protection', '86T Transformer Lockout Trip Contact'),

        -- COOLING WATER SYSTEM
        ('CWS_PUMP_1_RUN_STATUS', 'CW Pump-1', 'P1-MTR-RUN Cooling Water Pump-1 Run Contact'),
        ('CWS_PUMP_2_RUN_STATUS', 'CW Pump-2', 'P2-MTR-RUN Cooling Water Pump-2 Run Contact'),
        ('CWS_HEADER_PRESSURE_BAR', 'CW Header', 'PT-301 CW Header Pressure Transmitter'),
        ('CWS_FLOW_TOTAL_M3H', 'CW Header', 'FT-302 CW Total Flow Meter'),
        ('CWS_INLET_TEMP_C', 'CW Supply Header', 'TT-303 CW Inlet Temperature Sensor'),
        ('CWS_OUTLET_TEMP_C', 'CW Return Header', 'TT-304 CW Outlet Temperature Sensor'),
        ('COOLING_TOWER_BASIN_LEVEL_PCT', 'Cooling Tower Basin', 'LT-305 Basin Level Transmitter'),
        ('COOLING_TOWER_FAN_1_RUN_STATUS', 'Cooling Tower Fan-1', 'CTF1-RUN Fan-1 Run Contact'),
        ('COOLING_TOWER_FAN_2_RUN_STATUS', 'Cooling Tower Fan-2', 'CTF2-RUN Fan-2 Run Contact'),
        ('CWS_DELTA_TEMP_C', 'Thermal Performance', 'CALC-306 CW Delta-T Calculator')
    ) AS v(tag_id, sub_equipment, components)
)
UPDATE historian_meta.tag_master tm
SET
    sub_equipment = m.sub_equipment,
    components = m.components,
    config_updated_at = NOW()
FROM tag_map m
WHERE tm.tag_id = m.tag_id
  AND tm.plant = 'Plant1'
  AND tm.area = 'Area1';

COMMIT;
