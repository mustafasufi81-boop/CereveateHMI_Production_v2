-- ============================================================================
-- TimescaleDB Setup for Cereveate OPC DA Data Logger
-- Database: cereveate
-- User: cereveate
-- Password: cereveate@222
-- ============================================================================

-- Connect to cereveate database first, then run this script

-- ============================================================================
-- 1. CONVERT EXISTING sensor_data TO TIMESCALEDB HYPERTABLE
-- ============================================================================

-- Convert sensor_data to hypertable (partitioned by timestamp)
-- This must be done BEFORE adding any data
SELECT create_hypertable(
    'sensor_data', 
    'timestamp',
    chunk_time_interval => INTERVAL '1 day',  -- One chunk per day
    if_not_exists => TRUE
);

-- ============================================================================
-- 2. ADD INDEXES FOR PERFORMANCE
-- ============================================================================

-- Composite index for tag queries (most common query pattern)
CREATE INDEX IF NOT EXISTS idx_sensor_tag_time 
    ON sensor_data (tag_name, timestamp DESC);

-- Plant/Asset hierarchy queries
CREATE INDEX IF NOT EXISTS idx_sensor_plant_time 
    ON sensor_data (plant, asset, timestamp DESC);

-- Data source filtering
CREATE INDEX IF NOT EXISTS idx_sensor_source 
    ON sensor_data (data_source, timestamp DESC);

-- Quality filtering (find bad data)
CREATE INDEX IF NOT EXISTS idx_sensor_quality 
    ON sensor_data (quality_code, timestamp DESC) 
    WHERE quality_code != 192;  -- Partial index for non-good quality

-- Status alarms
CREATE INDEX IF NOT EXISTS idx_sensor_status 
    ON sensor_data (status_flag, timestamp DESC) 
    WHERE status_flag != 'OK';  -- Partial index for alarms

-- Batch/Shift analytics
CREATE INDEX IF NOT EXISTS idx_sensor_batch 
    ON sensor_data (batch_id, timestamp DESC) 
    WHERE batch_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_sensor_shift 
    ON sensor_data (shift, timestamp DESC) 
    WHERE shift IS NOT NULL;

-- Ingest timestamp for monitoring data pipeline delays
CREATE INDEX IF NOT EXISTS idx_sensor_ingest 
    ON sensor_data (ingest_timestamp DESC);

-- ============================================================================
-- 3. CREATE FILE IMPORT TRACKING TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS file_imports (
    import_id BIGSERIAL PRIMARY KEY,
    
    -- File information
    file_path TEXT NOT NULL UNIQUE,
    file_name TEXT NOT NULL,
    file_size_bytes BIGINT,
    file_modified_time TIMESTAMPTZ,
    file_checksum_sha256 CHAR(64),
    
    -- Import status
    import_status VARCHAR(20) NOT NULL,  -- pending, processing, completed, failed, partial
    import_started_at TIMESTAMPTZ,
    import_completed_at TIMESTAMPTZ,
    import_duration_seconds NUMERIC(10,2),
    
    -- Data validation
    total_rows_in_parquet BIGINT,
    rows_successfully_imported BIGINT DEFAULT 0,
    rows_failed BIGINT DEFAULT 0,
    rows_duplicate_skipped BIGINT DEFAULT 0,
    
    -- Error handling
    error_message TEXT,
    error_stack_trace TEXT,
    retry_count INT DEFAULT 0,
    last_retry_at TIMESTAMPTZ,
    max_retries INT DEFAULT 3,
    
    -- Metadata
    parquet_columns JSONB,  -- Store column structure from parquet
    import_config JSONB,    -- Store import parameters
    
    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_file_imports_status ON file_imports (import_status);
CREATE INDEX IF NOT EXISTS idx_file_imports_filename ON file_imports (file_name);
CREATE INDEX IF NOT EXISTS idx_file_imports_created ON file_imports (created_at DESC);

-- ============================================================================
-- 4. CREATE TAG CATALOG TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS tag_catalog (
    tag_id SERIAL PRIMARY KEY,
    tag_name TEXT UNIQUE NOT NULL,
    tag_code TEXT,
    tag_description TEXT,
    
    -- Hierarchy
    plant TEXT,
    asset TEXT,
    subsystem TEXT,
    
    -- Metadata
    unit TEXT,
    data_type VARCHAR(50),
    sensor_type VARCHAR(100),  -- Temperature, Pressure, Flow, Vibration, etc.
    
    -- Alarm limits (optional)
    high_high_limit NUMERIC,
    high_limit NUMERIC,
    low_limit NUMERIC,
    low_low_limit NUMERIC,
    
    -- Statistics (auto-updated by triggers)
    min_value NUMERIC,
    max_value NUMERIC,
    avg_value NUMERIC,
    
    -- Tracking
    first_seen_timestamp TIMESTAMPTZ,
    last_seen_timestamp TIMESTAMPTZ,
    total_records BIGINT DEFAULT 0,
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tag_catalog_name ON tag_catalog (tag_name);
CREATE INDEX IF NOT EXISTS idx_tag_catalog_plant ON tag_catalog (plant, asset);
CREATE INDEX IF NOT EXISTS idx_tag_catalog_active ON tag_catalog (is_active);

-- ============================================================================
-- 5. CREATE IMPORT ERRORS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS import_errors (
    error_id BIGSERIAL PRIMARY KEY,
    import_id BIGINT REFERENCES file_imports(import_id) ON DELETE CASCADE,
    error_timestamp TIMESTAMPTZ DEFAULT NOW(),
    error_type VARCHAR(100),
    error_message TEXT,
    error_details JSONB,
    row_number BIGINT,
    tag_name TEXT,
    value_attempted TEXT
);

CREATE INDEX IF NOT EXISTS idx_import_errors_import_id ON import_errors (import_id);
CREATE INDEX IF NOT EXISTS idx_import_errors_timestamp ON import_errors (error_timestamp DESC);

-- ============================================================================
-- 6. CREATE AUTO-UPDATE TRIGGER FOR updated_at
-- ============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_file_imports_updated_at
    BEFORE UPDATE ON file_imports
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_tag_catalog_updated_at
    BEFORE UPDATE ON tag_catalog
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 7. CREATE MATERIALIZED VIEWS FOR DASHBOARD
-- ============================================================================

-- Latest values for each tag (for real-time dashboard)
CREATE MATERIALIZED VIEW IF NOT EXISTS latest_sensor_values AS
SELECT DISTINCT ON (tag_name)
    tag_name,
    timestamp,
    value,
    unit,
    quality_code,
    status_flag,
    plant,
    asset,
    subsystem,
    data_source
FROM sensor_data
ORDER BY tag_name, timestamp DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_latest_sensor_values ON latest_sensor_values (tag_name);

-- Import summary dashboard
CREATE MATERIALIZED VIEW IF NOT EXISTS import_summary_dashboard AS
SELECT 
    import_status,
    COUNT(*) as total_imports,
    SUM(total_rows_in_parquet) as total_rows_in_files,
    SUM(rows_successfully_imported) as total_rows_imported,
    SUM(rows_failed) as total_rows_failed,
    SUM(rows_duplicate_skipped) as total_duplicates_skipped,
    AVG(import_duration_seconds) as avg_duration_seconds,
    MAX(import_completed_at) as last_import_time
FROM file_imports
GROUP BY import_status;

-- ============================================================================
-- 8. CREATE HELPER FUNCTIONS
-- ============================================================================

-- Function: Get tag data for time range
CREATE OR REPLACE FUNCTION get_tag_data(
    p_tag_name TEXT,
    p_start_time TIMESTAMPTZ,
    p_end_time TIMESTAMPTZ,
    p_limit INT DEFAULT 10000
)
RETURNS TABLE (
    timestamp TIMESTAMPTZ,
    value NUMERIC,
    unit TEXT,
    quality_code INT,
    status_flag TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        s.timestamp,
        s.value,
        s.unit,
        s.quality_code,
        s.status_flag
    FROM sensor_data s
    WHERE s.tag_name = p_tag_name
      AND s.timestamp BETWEEN p_start_time AND p_end_time
    ORDER BY s.timestamp ASC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- Function: Update tag statistics
CREATE OR REPLACE FUNCTION update_tag_statistics(p_tag_name TEXT)
RETURNS VOID AS $$
BEGIN
    INSERT INTO tag_catalog (
        tag_name,
        min_value,
        max_value,
        avg_value,
        first_seen_timestamp,
        last_seen_timestamp,
        total_records,
        plant,
        asset,
        subsystem,
        unit
    )
    SELECT 
        p_tag_name,
        MIN(value),
        MAX(value),
        AVG(value),
        MIN(timestamp),
        MAX(timestamp),
        COUNT(*),
        MAX(plant),  -- Use most recent values
        MAX(asset),
        MAX(subsystem),
        MAX(unit)
    FROM sensor_data
    WHERE tag_name = p_tag_name
    ON CONFLICT (tag_name) DO UPDATE SET
        min_value = EXCLUDED.min_value,
        max_value = EXCLUDED.max_value,
        avg_value = EXCLUDED.avg_value,
        last_seen_timestamp = EXCLUDED.last_seen_timestamp,
        total_records = EXCLUDED.total_records,
        plant = EXCLUDED.plant,
        asset = EXCLUDED.asset,
        subsystem = EXCLUDED.subsystem,
        unit = EXCLUDED.unit;
END;
$$ LANGUAGE plpgsql;

-- Function: Get multiple tags data (for multi-tag trends)
CREATE OR REPLACE FUNCTION get_multiple_tags_data(
    p_tag_names TEXT[],
    p_start_time TIMESTAMPTZ,
    p_end_time TIMESTAMPTZ,
    p_limit INT DEFAULT 10000
)
RETURNS TABLE (
    timestamp TIMESTAMPTZ,
    tag_name TEXT,
    value NUMERIC,
    unit TEXT,
    quality_code INT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        s.timestamp,
        s.tag_name,
        s.value,
        s.unit,
        s.quality_code
    FROM sensor_data s
    WHERE s.tag_name = ANY(p_tag_names)
      AND s.timestamp BETWEEN p_start_time AND p_end_time
    ORDER BY s.timestamp ASC, s.tag_name
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 9. CONTINUOUS AGGREGATES FOR ANALYTICS (TimescaleDB Feature)
-- ============================================================================

-- 1-minute averages for each tag
CREATE MATERIALIZED VIEW IF NOT EXISTS sensor_data_1min
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 minute', timestamp) AS bucket,
    tag_name,
    plant,
    asset,
    AVG(value) as avg_value,
    MIN(value) as min_value,
    MAX(value) as max_value,
    COUNT(*) as sample_count,
    MAX(unit) as unit
FROM sensor_data
GROUP BY bucket, tag_name, plant, asset;

-- Add refresh policy (auto-update every 1 minute)
SELECT add_continuous_aggregate_policy('sensor_data_1min',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute');

-- 1-hour averages for long-term trends
CREATE MATERIALIZED VIEW IF NOT EXISTS sensor_data_1hour
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', timestamp) AS bucket,
    tag_name,
    plant,
    asset,
    AVG(value) as avg_value,
    MIN(value) as min_value,
    MAX(value) as max_value,
    COUNT(*) as sample_count,
    MAX(unit) as unit
FROM sensor_data
GROUP BY bucket, tag_name, plant, asset;

-- Add refresh policy
SELECT add_continuous_aggregate_policy('sensor_data_1hour',
    start_offset => INTERVAL '1 week',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');

-- ============================================================================
-- 10. COMPRESSION POLICY (Save disk space for old data)
-- ============================================================================

-- Enable compression on sensor_data after 7 days
ALTER TABLE sensor_data SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'tag_name, plant, asset',
    timescaledb.compress_orderby = 'timestamp DESC'
);

-- Auto-compress data older than 7 days
SELECT add_compression_policy('sensor_data', INTERVAL '7 days');

-- ============================================================================
-- 11. RETENTION POLICY (Optional - auto-delete old data)
-- ============================================================================

-- Uncomment to auto-delete data older than 2 years
-- SELECT add_retention_policy('sensor_data', INTERVAL '2 years');

-- ============================================================================
-- 12. GRANT PERMISSIONS TO cereveate USER
-- ============================================================================

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO cereveate;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO cereveate;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO cereveate;

-- Grant future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO cereveate;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO cereveate;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO cereveate;

-- ============================================================================
-- 13. VERIFICATION QUERIES
-- ============================================================================

-- Check if hypertable is created
SELECT * FROM timescaledb_information.hypertables WHERE hypertable_name = 'sensor_data';

-- Check chunks (partitions)
SELECT * FROM timescaledb_information.chunks WHERE hypertable_name = 'sensor_data';

-- Check compression status
SELECT * FROM timescaledb_information.compression_settings WHERE hypertable_name = 'sensor_data';

-- Check all tables
SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;

-- ============================================================================
-- SETUP COMPLETE!
-- ============================================================================

SELECT 'TimescaleDB setup completed successfully!' as status;
