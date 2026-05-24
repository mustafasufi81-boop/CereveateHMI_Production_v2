-- Run this as PostgreSQL superuser (postgres)
-- Command: psql -U postgres -d Cereveate -f enable_timescaledb_superuser.sql

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Verify extension is installed
SELECT extname, extversion FROM pg_extension WHERE extname = 'timescaledb';

-- Now convert sensor_data to hypertable
-- Note: Table must be EMPTY or this will fail
-- If table has data, you need to migrate it first

SELECT create_hypertable(
    'sensor_data', 
    'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Verify hypertable creation
SELECT * FROM timescaledb_information.hypertables WHERE hypertable_name = 'sensor_data';

-- Grant permissions to cereveate user
GRANT ALL ON ALL TABLES IN SCHEMA public TO cereveate;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO cereveate;

SELECT 'TimescaleDB enabled successfully!' as status;
