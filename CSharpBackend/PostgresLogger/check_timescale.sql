-- ============================================================================
-- TimescaleDB Installation & Configuration Check
-- Database: Cereveate
-- Run these queries step by step
-- ============================================================================

-- Step 1: Check if TimescaleDB extension is installed
SELECT extname, extversion, extowner::regrole 
FROM pg_extension 
WHERE extname = 'timescaledb';
-- Expected: Should show 'timescaledb' with version number

-- Step 2: If not installed, install it (requires superuser)
-- Uncomment and run as postgres user:
-- CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Step 3: Check table structure of sensor_data
SELECT 
    column_name, 
    data_type, 
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'sensor_data'
ORDER BY ordinal_position;

-- Step 4: Check if sensor_data exists and has data
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size
FROM pg_tables
WHERE tablename = 'sensor_data';

-- Step 5: Count records in sensor_data
SELECT COUNT(*) as total_records FROM sensor_data;

-- Step 6: Check if sensor_data is a hypertable
-- This will only work if TimescaleDB extension is properly loaded
SELECT 
    ht.schema_name,
    ht.table_name,
    ht.num_dimensions,
    ds.num_chunks
FROM _timescaledb_catalog.hypertable ht
LEFT JOIN _timescaledb_catalog.dimension_slice ds ON ht.id = ds.hypertable_id
WHERE ht.table_name = 'sensor_data'
LIMIT 1;

-- Alternative check using public API (if above fails)
-- SELECT * FROM timescaledb_information.hypertables WHERE hypertable_name = 'sensor_data';

-- Step 7: Enable TimescaleDB extension first (run as superuser/postgres)
-- CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Step 7a: Reload extension if already installed but not loaded
-- DROP EXTENSION IF EXISTS timescaledb CASCADE;
-- CREATE EXTENSION timescaledb;

-- Step 7b: Convert sensor_data to hypertable
-- WARNING: Table must have 'timestamp' column with TIMESTAMPTZ type
-- Run this AFTER enabling the extension:
-- If table has existing data, use migrate_data => true
/*
SELECT create_hypertable(
    relation => 'sensor_data'::regclass,
    time_column_name => 'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    migrate_data => true,
    if_not_exists => TRUE
);
*/

-- Step 8: After conversion, verify hypertable
SELECT 
    hypertable_schema,
    hypertable_name,
    num_dimensions,
    num_chunks,
    compression_state
FROM timescaledb_information.hypertables
WHERE hypertable_name = 'sensor_data';

-- Step 9: Check existing indexes
SELECT 
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'sensor_data'
ORDER BY indexname;

-- Step 10: Sample data to verify structure
SELECT 
    timestamp,
    tag_name,
    value,
    unit,
    plant,
    asset,
    quality_code,
    status_flag,
    data_source
FROM sensor_data
ORDER BY timestamp DESC
LIMIT 5;

-- ============================================================================
-- RESULTS INTERPRETATION:
-- - Step 1: If empty = extension not installed
-- - Step 6: If empty = sensor_data is NOT a hypertable yet
-- - Step 8: If shows data = sensor_data IS a hypertable (SUCCESS!)
-- ============================================================================
