-- 016_seed_turbine_tag_master_plant1_area1.sql
-- Seed realistic Turbine1 tag metadata for Plant1/Area1.

BEGIN;

WITH turbine_seed AS (
    SELECT *
    FROM (VALUES
        ('TURBINE_LOAD_MW', 'Turbine Load', 'Turbine active power output', 'Plant1', 'Area1', 'Turbine1', 'double', 'MW', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('TURBINE_SPEED_RPM', 'Turbine Speed', 'Turbine shaft speed', 'Plant1', 'Area1', 'Turbine1', 'double', 'RPM', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('MAIN_STEAM_PRESSURE_BAR', 'Main Steam Pressure', 'Main steam pressure at turbine inlet', 'Plant1', 'Area1', 'Turbine1', 'double', 'bar', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('MAIN_STEAM_TEMP_C', 'Main Steam Temperature', 'Main steam temperature at turbine inlet', 'Plant1', 'Area1', 'Turbine1', 'double', 'C', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('REHEAT_STEAM_PRESSURE_BAR', 'Reheat Steam Pressure', 'Reheat steam pressure at IP inlet', 'Plant1', 'Area1', 'Turbine1', 'double', 'bar', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('REHEAT_STEAM_TEMP_C', 'Reheat Steam Temperature', 'Reheat steam temperature at IP inlet', 'Plant1', 'Area1', 'Turbine1', 'double', 'C', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('CONDENSER_VACUUM_KPA', 'Condenser Vacuum', 'Condenser vacuum level', 'Plant1', 'Area1', 'Turbine1', 'double', 'kPa', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('GENERATOR_MW', 'Generator MW', 'Generator active power', 'Plant1', 'Area1', 'Turbine1', 'double', 'MW', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('GENERATOR_MVAR', 'Generator MVAR', 'Generator reactive power', 'Plant1', 'Area1', 'Turbine1', 'double', 'MVAR', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('GENERATOR_TERMINAL_KV', 'Generator Terminal Voltage', 'Generator terminal voltage', 'Plant1', 'Area1', 'Turbine1', 'double', 'kV', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('GENERATOR_CURRENT_A', 'Generator Current', 'Generator stator current', 'Plant1', 'Area1', 'Turbine1', 'double', 'A', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('BEARING_TEMP_HP_FRONT_C', 'HP Bearing Front Temperature', 'HP front bearing metal temperature', 'Plant1', 'Area1', 'Turbine1', 'double', 'C', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('BEARING_TEMP_HP_REAR_C', 'HP Bearing Rear Temperature', 'HP rear bearing metal temperature', 'Plant1', 'Area1', 'Turbine1', 'double', 'C', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('BEARING_TEMP_IP_REAR_C', 'IP Bearing Rear Temperature', 'IP rear bearing metal temperature', 'Plant1', 'Area1', 'Turbine1', 'double', 'C', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('BEARING_TEMP_LP_FRONT_C', 'LP Bearing Front Temperature', 'LP front bearing metal temperature', 'Plant1', 'Area1', 'Turbine1', 'double', 'C', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('BEARING_TEMP_LP_REAR_C', 'LP Bearing Rear Temperature', 'LP rear bearing metal temperature', 'Plant1', 'Area1', 'Turbine1', 'double', 'C', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('VIB_HP_FRONT_X_UM', 'HP Front X Vibration', 'HP front bearing X-axis vibration', 'Plant1', 'Area1', 'Turbine1', 'double', 'um', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('VIB_HP_FRONT_Y_UM', 'HP Front Y Vibration', 'HP front bearing Y-axis vibration', 'Plant1', 'Area1', 'Turbine1', 'double', 'um', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('VIB_HP_REAR_X_UM', 'HP Rear X Vibration', 'HP rear bearing X-axis vibration', 'Plant1', 'Area1', 'Turbine1', 'double', 'um', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('VIB_HP_REAR_Y_UM', 'HP Rear Y Vibration', 'HP rear bearing Y-axis vibration', 'Plant1', 'Area1', 'Turbine1', 'double', 'um', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('VIB_IP_REAR_X_UM', 'IP Rear X Vibration', 'IP rear bearing X-axis vibration', 'Plant1', 'Area1', 'Turbine1', 'double', 'um', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('VIB_IP_REAR_Y_UM', 'IP Rear Y Vibration', 'IP rear bearing Y-axis vibration', 'Plant1', 'Area1', 'Turbine1', 'double', 'um', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('VIB_LP_FRONT_X_UM', 'LP Front X Vibration', 'LP front bearing X-axis vibration', 'Plant1', 'Area1', 'Turbine1', 'double', 'um', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('VIB_LP_FRONT_Y_UM', 'LP Front Y Vibration', 'LP front bearing Y-axis vibration', 'Plant1', 'Area1', 'Turbine1', 'double', 'um', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('VIB_LP_REAR_X_UM', 'LP Rear X Vibration', 'LP rear bearing X-axis vibration', 'Plant1', 'Area1', 'Turbine1', 'double', 'um', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('VIB_LP_REAR_Y_UM', 'LP Rear Y Vibration', 'LP rear bearing Y-axis vibration', 'Plant1', 'Area1', 'Turbine1', 'double', 'um', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('AXIAL_SHIFT_UM', 'Axial Shift', 'Turbine rotor axial position', 'Plant1', 'Area1', 'Turbine1', 'double', 'um', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('ECCENTRICITY_UM', 'Rotor Eccentricity', 'Rotor eccentricity measurement', 'Plant1', 'Area1', 'Turbine1', 'double', 'um', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('LUBE_OIL_PRESSURE_BAR', 'Lube Oil Pressure', 'Main lube oil header pressure', 'Plant1', 'Area1', 'Turbine1', 'double', 'bar', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('LUBE_OIL_TEMP_C', 'Lube Oil Temperature', 'Main lube oil supply temperature', 'Plant1', 'Area1', 'Turbine1', 'double', 'C', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('CONTROL_OIL_PRESSURE_BAR', 'Control Oil Pressure', 'EH/control oil pressure', 'Plant1', 'Area1', 'Turbine1', 'double', 'bar', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('GOVERNOR_VALVE_POS_PCT', 'Governor Valve Position', 'Governor valve opening position', 'Plant1', 'Area1', 'Turbine1', 'double', '%', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('STOP_VALVE_POS_PCT', 'Main Stop Valve Position', 'Main stop valve opening position', 'Plant1', 'Area1', 'Turbine1', 'double', '%', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('INTERCEPT_VALVE_POS_PCT', 'Intercept Valve Position', 'Intercept valve opening position', 'Plant1', 'Area1', 'Turbine1', 'double', '%', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('HOTWELL_LEVEL_PCT', 'Hotwell Level', 'Condenser hotwell level', 'Plant1', 'Area1', 'Turbine1', 'double', '%', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('GLAND_STEAM_PRESSURE_KPA', 'Gland Steam Pressure', 'Gland sealing steam pressure', 'Plant1', 'Area1', 'Turbine1', 'double', 'kPa', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('EXHAUST_TEMP_C', 'Exhaust Temperature', 'Turbine exhaust hood temperature', 'Plant1', 'Area1', 'Turbine1', 'double', 'C', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('TURBINE_TRIP_STATUS', 'Turbine Trip Status', 'Turbine trip indication', 'Plant1', 'Area1', 'Turbine1', 'boolean', 'STATE', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('BARRING_GEAR_STATUS', 'Barring Gear Status', 'Turning gear running status', 'Plant1', 'Area1', 'Turbine1', 'boolean', 'STATE', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('TRIP_OIL_PRESSURE_LOW', 'Trip Oil Pressure Low', 'Trip oil low pressure alarm/trip status', 'Plant1', 'Area1', 'Turbine1', 'boolean', 'STATE', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('OVERSPEED_TRIP_ACTIVE', 'Overspeed Trip Active', 'Overspeed protection trip status', 'Plant1', 'Area1', 'Turbine1', 'boolean', 'STATE', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016'),
        ('GEN_BREAKER_STATUS', 'Generator Breaker Status', 'Generator breaker open/close status', 'Plant1', 'Area1', 'Turbine1', 'boolean', 'STATE', 1000, TRUE, 'historian_raw.historian_timeseries', 'seed_migration_016')
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
    ts.tag_id,
    ts.tag_name,
    ts.description,
    ts.plant,
    ts.area,
    ts.equipment,
    LOWER(ts.data_type),
    ts.eng_unit,
    ts.db_logging_interval_ms,
    ts.enabled,
    ts.db_table_name,
    1,
    NOW(),
    NOW(),
    ts.created_by
FROM turbine_seed ts
ON CONFLICT (tag_id)
DO UPDATE SET
    tag_name = EXCLUDED.tag_name,
    description = EXCLUDED.description,
    plant = EXCLUDED.plant,
    area = EXCLUDED.area,
    equipment = EXCLUDED.equipment,
    data_type = EXCLUDED.data_type,
    eng_unit = EXCLUDED.eng_unit,
    db_logging_interval_ms = EXCLUDED.db_logging_interval_ms,
    enabled = EXCLUDED.enabled,
    db_table_name = EXCLUDED.db_table_name,
    config_updated_at = NOW();

COMMIT;