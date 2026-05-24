-- ============================================================================
-- Clean Setup: Drop and Recreate sensor_data as TimescaleDB Hypertable
-- Database: Cereveate
-- ============================================================================

-- Step 1: Drop existing table
DROP TABLE IF EXISTS sensor_data CASCADE;

-- Step 2: Create table with proper structure for TimescaleDB (matches importer output)
CREATE TABLE sensor_data (
    -- Time fields
    timestamp TIMESTAMPTZ NOT NULL,              -- From parquet file (actual sensor reading time)
    ingest_timestamp TIMESTAMPTZ DEFAULT NOW(),  -- System time when inserted
    
    -- Tag identification (tag_code = TagId from parquet)
    tag_code TEXT NOT NULL,
    
    -- Asset hierarchy (from tag mappings)
    plant TEXT NOT NULL,
    asset TEXT NOT NULL,
    subsystem TEXT NOT NULL,
    unit TEXT,
    
    -- Sensor value and quality
    value NUMERIC NOT NULL,
    quality TEXT DEFAULT 'Good',
    
    -- Auto-populated fields (not mapped)
    shift TEXT,
    batch_id TEXT,
    
    -- Primary key for TimescaleDB
    PRIMARY KEY (timestamp, tag_code)
);

-- Step 3: Enable TimescaleDB extension (if not already enabled)
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Step 4: Convert to hypertable
SELECT create_hypertable(
    relation => 'sensor_data'::regclass,
    time_column_name => 'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Step 5: Create indexes for performance
CREATE INDEX idx_sensor_tag_time ON sensor_data (tag_code, timestamp DESC);
CREATE INDEX idx_sensor_plant_asset ON sensor_data (plant, asset, timestamp DESC);
CREATE INDEX idx_sensor_subsystem ON sensor_data (subsystem, timestamp DESC);
CREATE INDEX idx_sensor_ingest ON sensor_data (ingest_timestamp DESC);
CREATE INDEX idx_sensor_quality ON sensor_data (quality) WHERE quality != 'Good';

-- Step 6: Enable compression (compress data older than 7 days)
ALTER TABLE sensor_data SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'tag_code, plant, asset, subsystem',
    timescaledb.compress_orderby = 'timestamp DESC'
);

SELECT add_compression_policy('sensor_data', INTERVAL '7 days');

-- Step 7: Grant permissions to cereveate user
GRANT ALL PRIVILEGES ON sensor_data TO cereveate;

-- Step 8: Verify setup
SELECT 
    hypertable_schema,
    hypertable_name,
    num_dimensions,
    num_chunks
FROM timescaledb_information.hypertables
WHERE hypertable_name = 'sensor_data';

-- Check compression settings separately
SELECT 
    attname as column_name,
    segmentby_column_index,
    orderby_column_index
FROM timescaledb_information.compression_settings
WHERE hypertable_name = 'sensor_data'
LIMIT 10;

-- Step 9: Show table structure
SELECT 
    column_name, 
    data_type, 
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'sensor_data'
ORDER BY ordinal_position;

-- Step 10: Show all indexes
SELECT 
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'sensor_data'
ORDER BY indexname;

-- ============================================================================
-- ✅ DONE! sensor_data is now a TimescaleDB hypertable
-- - Partitioned by timestamp (1 day chunks)
-- - Compression enabled for data older than 7 days
-- - All indexes created
-- - Ready to accept data from parquet files
-- ============================================================================
