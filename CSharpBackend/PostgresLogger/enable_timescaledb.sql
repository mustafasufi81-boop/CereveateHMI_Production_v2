-- Enable TimescaleDB extension and convert sensor_data to hypertable
-- Run this as superuser first

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Convert sensor_data to hypertable
SELECT create_hypertable(
    'sensor_data', 
    'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Verify hypertable creation
SELECT * FROM timescaledb_information.hypertables WHERE hypertable_name = 'sensor_data';
