/* ====================================================================
   HISTORIAN PLATFORM DDL - FINAL PRODUCTION READY
   TimescaleDB 2.10+, PostgreSQL 14+
   All fixes applied. Ready for deployment.
==================================================================== */

-- ================= EXTENSIONS =================
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ================= SCHEMAS =================
CREATE SCHEMA IF NOT EXISTS historian_raw;
CREATE SCHEMA IF NOT EXISTS historian_meta;
CREATE SCHEMA IF NOT EXISTS historian_mon;

-- ================= METADATA TABLES =================
SET search_path = historian_meta, public;

-- tag_master: single source of truth for tags
CREATE TABLE IF NOT EXISTS tag_master (
    tag_id TEXT PRIMARY KEY,
    tag_name TEXT NOT NULL,
    description TEXT,
    plant TEXT NOT NULL,
    area TEXT NOT NULL,
    equipment TEXT NOT NULL,
    data_type TEXT NOT NULL CHECK (data_type IN ('double','integer','boolean','string')),
    eng_unit TEXT,
    db_logging_interval_ms INTEGER NOT NULL DEFAULT 1000,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    db_table_name TEXT NOT NULL DEFAULT 'historian_raw.historian_timeseries',
    mapping_version BIGINT NOT NULL DEFAULT 1,
    config_updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by TEXT,
    CONSTRAINT chk_interval_positive CHECK (db_logging_interval_ms > 0)
);

COMMENT ON TABLE tag_master IS 'Tag registry and mapping. mapping_version increments on mapping changes.';

-- Indexes for tag_master
CREATE INDEX IF NOT EXISTS idx_tag_master_plant_area_eq ON tag_master (plant, area, equipment);
CREATE INDEX IF NOT EXISTS idx_tag_master_enabled ON tag_master (enabled);
CREATE INDEX IF NOT EXISTS idx_tag_master_tag_id ON tag_master (tag_id);

-- tag_attributes: flexible key/value metadata
CREATE TABLE IF NOT EXISTS tag_attributes (
    tag_id TEXT NOT NULL REFERENCES tag_master(tag_id) ON DELETE CASCADE,
    attr_key TEXT NOT NULL,
    attr_value TEXT,
    PRIMARY KEY (tag_id, attr_key)
);

-- equipment_hierarchy: normalized asset tree
CREATE TABLE IF NOT EXISTS equipment_hierarchy (
    plant TEXT NOT NULL,
    area TEXT NOT NULL,
    equipment TEXT NOT NULL,
    description TEXT,
    PRIMARY KEY (plant, area, equipment)
);

-- writer_checkpoint: durable writer state
CREATE TABLE IF NOT EXISTS writer_checkpoint (
    writer_name TEXT PRIMARY KEY,
    last_processed_at TIMESTAMPTZ,
    last_mapping_version BIGINT,
    last_wal_lsn TEXT,
    info JSONB
);

-- ================= TIMESERIES TABLES =================
SET search_path = historian_raw, public;

-- historian_timeseries: Main hypertable (optimized storage)
CREATE TABLE IF NOT EXISTS historian_timeseries (
    time TIMESTAMPTZ NOT NULL,
    tag_id TEXT NOT NULL,
    value_num DOUBLE PRECISION NULL,
    value_text TEXT NULL,
    value_bool BOOLEAN NULL,
    quality CHAR(1) CHECK (quality IN ('G', 'B', 'U')),
    sample_source CHAR(3) DEFAULT 'OPC',
    mapping_version BIGINT NOT NULL DEFAULT 1
) WITH (fillfactor = 90);

-- Convert to hypertable with 4-hour chunks
SELECT create_hypertable(
    'historian_raw.historian_timeseries',
    'time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '4 hours',
    create_default_indexes => FALSE
);

-- BRIN index on time (WAL-efficient)
CREATE INDEX IF NOT EXISTS hist_ts_time_brin_idx 
ON historian_raw.historian_timeseries 
USING BRIN (time) WITH (pages_per_range = 32);

-- Main query index: (tag_id, time DESC) with covering columns
CREATE INDEX IF NOT EXISTS hist_ts_tag_time_idx 
ON historian_raw.historian_timeseries 
    (tag_id, time DESC)
INCLUDE (value_num, quality, value_bool)
WITH (fillfactor = 95);

CREATE INDEX IF NOT EXISTS idx_ts_tag_only 
ON historian_raw.historian_timeseries(tag_id);

-- Enable TimescaleDB compression
ALTER TABLE historian_raw.historian_timeseries SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'tag_id',
    timescaledb.compress_orderby = 'time DESC'
);

-- Staggered compression policy
SELECT add_compression_policy(
    'historian_raw.historian_timeseries',
    compress_after => INTERVAL '2 days',
    if_not_exists => true
);

-- Retention policy
SELECT add_retention_policy(
    'historian_raw.historian_timeseries',
    drop_after => INTERVAL '730 days',
    if_not_exists => true
);

-- ================= CACHE TABLE =================
CREATE TABLE IF NOT EXISTS historian_latest_value (
    tag_id TEXT PRIMARY KEY,
    last_time TIMESTAMPTZ,
    last_value_num DOUBLE PRECISION,
    last_value_text TEXT,
    last_value_bool BOOLEAN,
    last_quality TEXT,
    last_mapping_version BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
) WITH (fillfactor = 90);

CREATE INDEX IF NOT EXISTS idx_latest_updated_at ON historian_raw.historian_latest_value (updated_at DESC);

-- ================= EVENT TABLES =================
CREATE TABLE IF NOT EXISTS historian_events (
    event_id BIGSERIAL PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL DEFAULT now(),
    tag_id TEXT,
    event_type TEXT,
    severity INTEGER,
    message TEXT,
    metadata JSONB NULL
);

SELECT create_hypertable('historian_raw.historian_events', 'time', 
    if_not_exists => TRUE, chunk_time_interval => INTERVAL '7 days');

-- Optional: KPIs table
CREATE TABLE IF NOT EXISTS historian_calc_values (
    time TIMESTAMPTZ NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value DOUBLE PRECISION,
    tags JSONB NULL,
    PRIMARY KEY (time, metric_name)
);

SELECT create_hypertable('historian_raw.historian_calc_values', 'time', 
    if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 day');

-- ================= MONITORING TABLES =================
SET search_path = historian_mon, public;

CREATE TABLE IF NOT EXISTS system_metrics (
    time TIMESTAMPTZ NOT NULL,
    metric_name TEXT NOT NULL,
    instance_id TEXT NOT NULL,
    value DOUBLE PRECISION,
    labels JSONB,
    PRIMARY KEY (time, metric_name, instance_id)
);

SELECT create_hypertable('historian_mon.system_metrics', 'time', 
    if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 hour');

CREATE TABLE IF NOT EXISTS wal_monitoring (
    time TIMESTAMPTZ PRIMARY KEY DEFAULT now(),
    wal_size_bytes BIGINT,
    wal_files_count INTEGER,
    replication_lag_bytes BIGINT,
    checkpoint_lag_bytes BIGINT,
    archive_status TEXT,
    compression_backlog_days INTEGER
);

-- ================= HELPER FUNCTIONS =================
CREATE OR REPLACE FUNCTION update_latest_values_batch(
    tag_ids TEXT[],
    times TIMESTAMPTZ[],
    value_nums DOUBLE PRECISION[],
    value_texts TEXT[],
    value_bools BOOLEAN[],
    qualities TEXT[],
    mapping_versions BIGINT[]
) RETURNS void AS $$
BEGIN
    UPDATE historian_raw.historian_latest_value AS lv
    SET 
        last_time = upd.last_time,
        last_value_num = upd.last_value_num,
        last_value_text = upd.last_value_text,
        last_value_bool = upd.last_value_bool,
        last_quality = upd.last_quality,
        last_mapping_version = upd.last_mapping_version,
        updated_at = now()
    FROM (
        SELECT 
            unnest(tag_ids) AS tag_id,
            unnest(times) AS last_time,
            unnest(value_nums) AS last_value_num,
            unnest(value_texts) AS last_value_text,
            unnest(value_bools) AS last_value_bool,
            unnest(qualities) AS last_quality,
            unnest(mapping_versions) AS last_mapping_version
    ) AS upd
    WHERE lv.tag_id = upd.tag_id;
    
    INSERT INTO historian_raw.historian_latest_value 
        (tag_id, last_time, last_value_num, last_value_text, 
         last_value_bool, last_quality, last_mapping_version, updated_at)
    SELECT 
        upd.tag_id, upd.last_time, upd.last_value_num, upd.last_value_text,
        upd.last_value_bool, upd.last_quality, upd.last_mapping_version, now()
    FROM (
        SELECT 
            unnest(tag_ids) AS tag_id,
            unnest(times) AS last_time,
            unnest(value_nums) AS last_value_num,
            unnest(value_texts) AS last_value_text,
            unnest(value_bools) AS last_value_bool,
            unnest(qualities) AS last_quality,
            unnest(mapping_versions) AS last_mapping_version
    ) AS upd
    WHERE NOT EXISTS (
        SELECT 1 FROM historian_raw.historian_latest_value 
        WHERE tag_id = upd.tag_id
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE FUNCTION get_tag_history(
    p_tag_id TEXT,
    p_start_time TIMESTAMPTZ,
    p_end_time TIMESTAMPTZ,
    p_limit INTEGER DEFAULT 10000
) RETURNS TABLE(
    time TIMESTAMPTZ,
    value_num DOUBLE PRECISION,
    value_text TEXT,
    value_bool BOOLEAN,
    quality CHAR(1),
    tag_name TEXT,
    plant TEXT,
    area TEXT,
    equipment TEXT
) LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT 
        ht.time,
        ht.value_num,
        ht.value_text,
        ht.value_bool,
        ht.quality,
        tm.tag_name,
        tm.plant,
        tm.area,
        tm.equipment
    FROM historian_raw.historian_timeseries ht
    JOIN historian_meta.tag_master tm ON ht.tag_id = tm.tag_id
    WHERE ht.tag_id = p_tag_id
        AND ht.time >= p_start_time
        AND ht.time <= p_end_time
    ORDER BY ht.time DESC
    LIMIT p_limit;
END;
$$;

-- ================= VALIDATION =================
DO $$
DECLARE
    hypertable_count INTEGER;
    compression_enabled BOOLEAN;
BEGIN
    SELECT COUNT(*) INTO hypertable_count
    FROM timescaledb_information.hypertables 
    WHERE hypertable_schema = 'historian_raw'
      AND hypertable_name IN ('historian_timeseries', 'historian_events');
    
    IF hypertable_count < 2 THEN
        RAISE WARNING 'Not all hypertables created properly';
    END IF;
    
    SELECT compression_enabled INTO compression_enabled
    FROM timescaledb_information.compression_settings 
    WHERE hypertable_name = 'historian_timeseries';
    
    IF NOT compression_enabled THEN
        RAISE WARNING 'Compression not enabled on historian_timeseries';
    END IF;
    
    RAISE NOTICE 'Historian schema validation completed. Hypertables: %, Compression: %',
                 hypertable_count, compression_enabled;
END $$;
