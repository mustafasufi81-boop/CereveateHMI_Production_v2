-- 019_seed_daily_templates_for_boiler_generator_transformer_cws.sql
-- Add DAILY report template rows for Plant1/Area1 tags seeded in migration 018.

BEGIN;

WITH selected_tags AS (
    SELECT tm.tag_id
    FROM historian_meta.tag_master tm
    WHERE tm.enabled = TRUE
      AND tm.plant = 'Plant1'
      AND tm.area = 'Area1'
      AND tm.tag_id IN (
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
      )
),
base AS (
    SELECT COALESCE(MAX(rt.s_no), 0) AS base_s_no
    FROM historian_meta.report_templates rt
    WHERE rt.report_type = 'DAILY'
),
ordered_tags AS (
    SELECT
        st.tag_id,
        ROW_NUMBER() OVER (ORDER BY st.tag_id) AS row_no
    FROM selected_tags st
)
INSERT INTO historian_meta.report_templates (report_type, s_no, tag_id, enabled)
SELECT
    'DAILY',
    b.base_s_no + ot.row_no,
    ot.tag_id,
    TRUE
FROM ordered_tags ot
CROSS JOIN base b
ON CONFLICT (report_type, tag_id)
DO UPDATE SET
    s_no = EXCLUDED.s_no,
    enabled = EXCLUDED.enabled;

COMMIT;
