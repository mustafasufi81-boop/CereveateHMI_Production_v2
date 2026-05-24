-- Fix sensor_data primary key for TimescaleDB compatibility
-- Run these commands in order:

-- Step 1: Drop existing primary key
ALTER TABLE sensor_data DROP CONSTRAINT IF EXISTS sensor_data_pkey;

-- Step 2: Create composite primary key including timestamp
-- This is required for TimescaleDB partitioning
ALTER TABLE sensor_data ADD PRIMARY KEY (id, timestamp);

-- Step 3: Now convert to hypertable with data migration
SELECT create_hypertable(
    relation => 'sensor_data'::regclass,
    time_column_name => 'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    migrate_data => true,
    if_not_exists => TRUE
);

-- Step 4: Verify hypertable was created
SELECT 
    hypertable_schema,
    hypertable_name,
    num_dimensions,
    num_chunks
FROM timescaledb_information.hypertables
WHERE hypertable_name = 'sensor_data';

-- Step 5: Check data is still there
SELECT COUNT(*) as total_records FROM sensor_data;

-- Step 6: View sample data
SELECT * FROM sensor_data ORDER BY timestamp DESC LIMIT 5;
