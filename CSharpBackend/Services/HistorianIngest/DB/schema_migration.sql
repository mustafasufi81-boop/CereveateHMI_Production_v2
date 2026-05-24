-- ============================================================================
-- HISTORIAN INGEST SYSTEM - DATABASE SCHEMA MIGRATION
-- TimescaleDB Required
-- ============================================================================

-- Create schemas
CREATE SCHEMA IF NOT EXISTS historian_meta;
CREATE SCHEMA IF NOT EXISTS historian_raw;
CREATE SCHEMA IF NOT EXISTS historian_admin;
CREATE SCHEMA IF NOT EXISTS historian_mon;

-- ============================================================================
-- SCHEMA: historian_meta (Tag Configuration & Mapping)
-- ============================================================================

CREATE TABLE IF NOT EXISTS historian_meta.tag_master (
    tag_id VARCHAR(255) PRIMARY KEY,
    tag_name VARCHAR(255) NOT NULL,
    description TEXT,
    plant VARCHAR(100),
    area VARCHAR(100),
    equipment VARCHAR(100),
    data_type VARCHAR(20) NOT NULL CHECK (data_type IN ('double', 'int', 'bool', 'string')),
    eng_unit VARCHAR(50),
    db_logging_interval_ms INTEGER NOT NULL CHECK (db_logging_interval_ms BETWEEN 1000 AND 60000),
    deadband_value DOUBLE PRECISION DEFAULT 0.0,
    enabled BOOLEAN DEFAULT true,
    db_table_name VARCHAR(255) DEFAULT 'historian_raw.historian_timeseries',
    mapping_version INTEGER NOT NULL DEFAULT 1,
    config_updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_tag_master_enabled ON historian_meta.tag_master(enabled);
CREATE INDEX IF NOT EXISTS idx_tag_master_mapping_version ON historian_meta.tag_master(mapping_version);

-- Tag attributes (flexible metadata)
CREATE TABLE IF NOT EXISTS historian_meta.tag_attributes (
    tag_id VARCHAR(255) REFERENCES historian_meta.tag_master(tag_id) ON DELETE CASCADE,
    attribute_key VARCHAR(100),
    attribute_value TEXT,
    PRIMARY KEY (tag_id, attribute_key)
);

-- Trigger to auto-increment mapping_version on update
CREATE OR REPLACE FUNCTION historian_meta.increment_mapping_version()
RETURNS TRIGGER AS $$
BEGIN
    NEW.mapping_version = OLD.mapping_version + 1;
    NEW.config_updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_increment_mapping_version ON historian_meta.tag_master;
CREATE TRIGGER trg_increment_mapping_version
BEFORE UPDATE ON historian_meta.tag_master
FOR EACH ROW
WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE FUNCTION historian_meta.increment_mapping_version();

-- Notification trigger for cache refresh
CREATE OR REPLACE FUNCTION historian_meta.notify_mapping_change()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('mapping_updated', json_build_object(
        'tag_id', COALESCE(NEW.tag_id, OLD.tag_id),
        'operation', TG_OP,
        'mapping_version', COALESCE(NEW.mapping_version, OLD.mapping_version)
    )::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_notify_mapping_change ON historian_meta.tag_master;
CREATE TRIGGER trg_notify_mapping_change
AFTER INSERT OR UPDATE OR DELETE ON historian_meta.tag_master
FOR EACH ROW
EXECUTE FUNCTION historian_meta.notify_mapping_change();

-- ============================================================================
-- SCHEMA: historian_raw (Timeseries Data Storage)
-- ============================================================================

CREATE TABLE IF NOT EXISTS historian_raw.historian_timeseries (
    time TIMESTAMPTZ NOT NULL,
    tag_id VARCHAR(255) NOT NULL,
    value_num DOUBLE PRECISION,
    value_int BIGINT,
    value_bool BOOLEAN,
    value_text TEXT,
    quality CHAR(1) DEFAULT 'G' CHECK (quality IN ('G', 'B', 'U')),
    sample_source VARCHAR(20) DEFAULT 'OPC',
    mapping_version INTEGER NOT NULL,
    raw_opc_timestamp TIMESTAMPTZ,
    raw_opc_quality VARCHAR(50)
);

-- Convert to hypertable (TimescaleDB required)
SELECT create_hypertable('historian_raw.historian_timeseries', 'time', 
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_timeseries_tag_time 
    ON historian_raw.historian_timeseries (tag_id, time DESC);

CREATE INDEX IF NOT EXISTS idx_timeseries_time_brin 
    ON historian_raw.historian_timeseries USING BRIN (time);

-- Compression policy (after 7 days)
SELECT add_compression_policy('historian_raw.historian_timeseries', 
    INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Retention policy (optional, 2 years)
SELECT add_retention_policy('historian_raw.historian_timeseries', 
    INTERVAL '730 days',
    if_not_exists => TRUE
);

-- Latest values table (fast lookup)
CREATE TABLE IF NOT EXISTS historian_raw.historian_latest_value (
    tag_id VARCHAR(255) PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL,
    value_num DOUBLE PRECISION,
    value_int BIGINT,
    value_bool BOOLEAN,
    value_text TEXT,
    quality CHAR(1),
    sample_source VARCHAR(20),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_latest_value_time ON historian_raw.historian_latest_value(time DESC);

-- Stored procedure to update latest values in batch
CREATE OR REPLACE FUNCTION historian_raw.update_latest_values_batch(
    p_tag_ids VARCHAR(255)[],
    p_times TIMESTAMPTZ[],
    p_values_num DOUBLE PRECISION[],
    p_values_int BIGINT[],
    p_values_bool BOOLEAN[],
    p_values_text TEXT[],
    p_qualities CHAR(1)[],
    p_sources VARCHAR(20)[]
)
RETURNS INTEGER AS $$
DECLARE
    v_count INTEGER := 0;
    v_idx INTEGER;
BEGIN
    FOR v_idx IN 1..array_length(p_tag_ids, 1) LOOP
        INSERT INTO historian_raw.historian_latest_value 
            (tag_id, time, value_num, value_int, value_bool, value_text, quality, sample_source, updated_at)
        VALUES 
            (p_tag_ids[v_idx], p_times[v_idx], p_values_num[v_idx], p_values_int[v_idx], 
             p_values_bool[v_idx], p_values_text[v_idx], p_qualities[v_idx], p_sources[v_idx], NOW())
        ON CONFLICT (tag_id) DO UPDATE SET
            time = EXCLUDED.time,
            value_num = EXCLUDED.value_num,
            value_int = EXCLUDED.value_int,
            value_bool = EXCLUDED.value_bool,
            value_text = EXCLUDED.value_text,
            quality = EXCLUDED.quality,
            sample_source = EXCLUDED.sample_source,
            updated_at = NOW()
        WHERE historian_raw.historian_latest_value.time < EXCLUDED.time;
        
        v_count := v_count + 1;
    END LOOP;
    
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- SCHEMA: historian_admin (Checkpoints, Spool, Events)
-- ============================================================================

-- Writer checkpoints
CREATE TABLE IF NOT EXISTS historian_admin.writer_checkpoint (
    writer_name VARCHAR(100) PRIMARY KEY,
    last_processed_at TIMESTAMPTZ NOT NULL,
    last_mapping_version INTEGER,
    last_wal_lsn PG_LSN,
    info JSONB,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Spool tracking (idempotent replay)
CREATE TABLE IF NOT EXISTS historian_admin.spool_applied (
    file_hash VARCHAR(64) PRIMARY KEY,
    file_path TEXT NOT NULL,
    applied_at TIMESTAMPTZ DEFAULT NOW(),
    record_count INTEGER,
    writer_name VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_spool_applied_time ON historian_admin.spool_applied(applied_at);

-- Event log
CREATE TABLE IF NOT EXISTS historian_admin.historian_events (
    id BIGSERIAL PRIMARY KEY,
    event_time TIMESTAMPTZ DEFAULT NOW(),
    event_type VARCHAR(50) NOT NULL,
    tag_id VARCHAR(255),
    severity VARCHAR(20) DEFAULT 'INFO' CHECK (severity IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    message TEXT,
    details JSONB,
    writer_name VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_events_time ON historian_admin.historian_events(event_time DESC);
CREATE INDEX IF NOT EXISTS idx_events_type ON historian_admin.historian_events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_tag ON historian_admin.historian_events(tag_id);

-- ============================================================================
-- SCHEMA: historian_mon (Monitoring & Metrics)
-- ============================================================================

CREATE TABLE IF NOT EXISTS historian_mon.system_metrics (
    time TIMESTAMPTZ NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    metric_value DOUBLE PRECISION,
    labels JSONB,
    writer_name VARCHAR(100)
);

SELECT create_hypertable('historian_mon.system_metrics', 'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_metrics_name_time 
    ON historian_mon.system_metrics (metric_name, time DESC);

-- Compression policy
SELECT add_compression_policy('historian_mon.system_metrics', 
    INTERVAL '3 days',
    if_not_exists => TRUE
);

-- ============================================================================
-- INITIAL SAMPLE DATA (Optional - for testing)
-- ============================================================================

-- Sample tags
INSERT INTO historian_meta.tag_master 
    (tag_id, tag_name, description, plant, area, equipment, data_type, eng_unit, db_logging_interval_ms, enabled)
VALUES
    ('TAG001', 'Turbine Speed', 'Main turbine RPM', 'PLANT1', 'TURBINE', 'TURB01', 'double', 'RPM', 1000, true),
    ('TAG002', 'Generator Load', 'Active power output', 'PLANT1', 'GENERATOR', 'GEN01', 'double', 'MW', 1000, true),
    ('TAG003', 'Bearing Temp', 'Bearing temperature sensor', 'PLANT1', 'TURBINE', 'TURB01', 'double', '°C', 5000, true),
    ('TAG004', 'Emergency Stop', 'E-Stop button status', 'PLANT1', 'SAFETY', 'PANEL01', 'bool', '', 1000, true),
    ('TAG005', 'Alarm Message', 'Current alarm text', 'PLANT1', 'HMI', 'SCADA01', 'string', '', 2000, true)
ON CONFLICT (tag_id) DO NOTHING;

-- ============================================================================
-- GRANTS (Adjust based on your security model)
-- ============================================================================

-- Example: Grant access to historian_user role
-- CREATE ROLE historian_user WITH LOGIN PASSWORD 'your_password';
-- GRANT USAGE ON SCHEMA historian_meta, historian_raw, historian_admin, historian_mon TO historian_user;
-- GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA historian_raw TO historian_user;
-- GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA historian_meta TO historian_user;
-- GRANT ALL ON ALL TABLES IN SCHEMA historian_admin TO historian_user;
-- GRANT INSERT ON ALL TABLES IN SCHEMA historian_mon TO historian_user;

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Check hypertables
-- SELECT * FROM timescaledb_information.hypertables;

-- Check compression policies
-- SELECT * FROM timescaledb_information.jobs WHERE proc_name LIKE '%compression%';

-- Check sample tags
-- SELECT tag_id, tag_name, data_type, db_logging_interval_ms, enabled, mapping_version 
-- FROM historian_meta.tag_master;
