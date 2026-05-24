-- 022_backfill_server_progid_for_018_realtime_tags.sql
-- Populate source mapping columns so test_mqtt_publisher.py can generate
-- Boiler/Generator/Transformer/CoolingWaterSystem tags without script changes.

BEGIN;

WITH selected_tags AS (
    SELECT *
    FROM (VALUES
        ('BOILER_DRUM_LEVEL_PCT'),
        ('BOILER_MAIN_STEAM_PRESSURE_BAR'),
        ('BOILER_MAIN_STEAM_TEMP_C'),
        ('BOILER_FEEDWATER_FLOW_TPH'),
        ('BOILER_FURNACE_PRESSURE_KPA'),
        ('BOILER_O2_PCT'),
        ('BOILER_ID_FAN_SPEED_RPM'),
        ('BOILER_FD_FAN_SPEED_RPM'),
        ('BOILER_TRIP_STATUS'),
        ('BOILER_RUN_STATUS'),

        ('GENERATOR_ACTIVE_POWER_MW'),
        ('GENERATOR_REACTIVE_POWER_MVAR'),
        ('GENERATOR_TERMINAL_VOLTAGE_KV'),
        ('GENERATOR_CURRENT_A'),
        ('GENERATOR_FREQUENCY_HZ'),
        ('GENERATOR_POWER_FACTOR'),
        ('GENERATOR_STATOR_TEMP_C'),
        ('GENERATOR_ROTOR_TEMP_C'),
        ('GENERATOR_BREAKER_STATUS'),
        ('GENERATOR_RUN_STATUS'),

        ('TRANSFORMER_HV_VOLTAGE_KV'),
        ('TRANSFORMER_LV_VOLTAGE_KV'),
        ('TRANSFORMER_HV_CURRENT_A'),
        ('TRANSFORMER_LV_CURRENT_A'),
        ('TRANSFORMER_OIL_TEMP_C'),
        ('TRANSFORMER_WINDING_TEMP_C'),
        ('TRANSFORMER_LOAD_PCT'),
        ('TRANSFORMER_TAP_POSITION'),
        ('TRANSFORMER_BUCHHOLZ_ALARM'),
        ('TRANSFORMER_TRIP_STATUS'),

        ('CWS_PUMP_1_RUN_STATUS'),
        ('CWS_PUMP_2_RUN_STATUS'),
        ('CWS_HEADER_PRESSURE_BAR'),
        ('CWS_FLOW_TOTAL_M3H'),
        ('CWS_INLET_TEMP_C'),
        ('CWS_OUTLET_TEMP_C'),
        ('COOLING_TOWER_BASIN_LEVEL_PCT'),
        ('COOLING_TOWER_FAN_1_RUN_STATUS'),
        ('COOLING_TOWER_FAN_2_RUN_STATUS'),
        ('CWS_DELTA_TEMP_C')
    ) AS v(tag_id)
),
default_plc AS (
    -- Use first active PLC mapping from mqtt_topic_config.
    -- This is the same value test_mqtt_publisher.py expects in tag_master.server_progid.
    SELECT mtc.plc_name
    FROM historian_raw.mqtt_topic_config mtc
    WHERE mtc.is_active = TRUE
    ORDER BY mtc.topic_id
    LIMIT 1
)
UPDATE historian_meta.tag_master tm
SET
    server_progid = dp.plc_name,
    server_host = COALESCE(NULLIF(tm.server_host, ''), 'localhost'),
    config_updated_at = NOW()
FROM selected_tags st
CROSS JOIN default_plc dp
WHERE tm.tag_id = st.tag_id
  AND tm.plant = 'Plant1'
  AND tm.area = 'Area1'
  AND (tm.server_progid IS NULL OR TRIM(tm.server_progid) = '');

COMMIT;
