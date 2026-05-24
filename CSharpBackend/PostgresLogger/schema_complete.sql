-- ============================================================================
-- COMPLETE DATABASE SCHEMA FOR HIGH-PERFORMANCE PARQUET IMPORTER
-- Database: Cereveate
-- Purpose: Enterprise-ready schema for 10K+ tags, idempotent imports
-- ============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- ============================================================================
-- 1. SENSOR DATA TABLE (TimescaleDB Hypertable - Primary Time-Series Store)
-- ============================================================================

DROP TABLE IF EXISTS sensor_data CASCADE;

CREATE TABLE sensor_data (
    -- Time columns
    timestamp TIMESTAMPTZ NOT NULL,              -- Sensor reading time (from parquet)
    ingest_timestamp TIMESTAMPTZ DEFAULT NOW(),  -- System ingestion time
    
    -- Tag identification
    tag_code TEXT NOT NULL,                      -- TagId from parquet (e.g., "Random.Real4")
    tag_name TEXT,                               -- Display name from mapping
    
    -- Asset hierarchy (from tag mappings)
    plant TEXT NOT NULL,
    asset TEXT NOT NULL,
    subsystem TEXT NOT NULL,
    unit TEXT,
    
    -- Value and quality
    value NUMERIC NOT NULL,
    quality_code INTEGER DEFAULT 192,            -- OPC quality code (192 = Good)
    status_flag TEXT DEFAULT 'OK',
    data_source TEXT DEFAULT 'OPC_DA',
    
    -- Optional metadata
    shift TEXT,
    batch_id TEXT,
    
    -- Primary key for TimescaleDB
    PRIMARY KEY (timestamp, tag_code)
);

-- Convert to TimescaleDB hypertable (1-day chunks)
SELECT create_hypertable(
    relation => 'sensor_data'::regclass,
    time_column_name => 'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Performance indexes
CREATE INDEX idx_sensor_tag_time ON sensor_data (tag_code, timestamp DESC);
CREATE INDEX idx_sensor_plant_asset ON sensor_data (plant, asset, timestamp DESC);
CREATE INDEX idx_sensor_subsystem ON sensor_data (subsystem, timestamp DESC);
CREATE INDEX idx_sensor_ingest ON sensor_data (ingest_timestamp DESC);
CREATE INDEX idx_sensor_quality ON sensor_data (quality_code) WHERE quality_code != 192;

-- Enable compression (compress data older than 7 days)
ALTER TABLE sensor_data SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'tag_code, plant, asset, subsystem',
    timescaledb.compress_orderby = 'timestamp DESC'
);

SELECT add_compression_policy('sensor_data', INTERVAL '7 days');

-- ============================================================================
-- 2. TAG CATALOG (Fast Tag Discovery)
-- ============================================================================

DROP TABLE IF EXISTS tag_catalog CASCADE;

CREATE TABLE tag_catalog (
    tag_id TEXT PRIMARY KEY,                     -- Unique tag identifier
    first_seen TIMESTAMPTZ NOT NULL,             -- First data timestamp
    last_seen TIMESTAMPTZ NOT NULL,              -- Most recent data timestamp
    last_file TEXT,                              -- Most recent file containing this tag
    record_count BIGINT DEFAULT 0,               -- Total records across all files
    is_mapped BOOLEAN DEFAULT FALSE,             -- Whether tag has mapping config
    last_updated TIMESTAMPTZ DEFAULT NOW()       -- Last catalog update
);

CREATE INDEX idx_tag_catalog_last_seen ON tag_catalog(last_seen DESC);
CREATE INDEX idx_tag_catalog_mapped ON tag_catalog(is_mapped) WHERE is_mapped = TRUE;
CREATE INDEX idx_tag_catalog_updated ON tag_catalog(last_updated DESC);

-- ============================================================================
-- 3. TAG-FILE CATALOG (Which Tags Exist in Which Files)
-- ============================================================================

DROP TABLE IF EXISTS tag_file_catalog CASCADE;

CREATE TABLE tag_file_catalog (
    tag_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    first_seen TIMESTAMPTZ NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL,
    record_count INTEGER DEFAULT 0,
    file_size_bytes BIGINT DEFAULT 0,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (tag_id, file_path, file_hash)
);

CREATE INDEX idx_tag_file_catalog_tag ON tag_file_catalog(tag_id);
CREATE INDEX idx_tag_file_catalog_file ON tag_file_catalog(file_path);
CREATE INDEX idx_tag_file_catalog_hash ON tag_file_catalog(file_hash);
CREATE INDEX idx_tag_file_catalog_updated ON tag_file_catalog(last_updated DESC);

-- ============================================================================
-- 4. FILE IMPORTS TRACKING (Import Queue + Status)
-- ============================================================================

DROP TABLE IF EXISTS file_imports CASCADE;

CREATE TABLE file_imports (
    id SERIAL PRIMARY KEY,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    file_size BIGINT,
    
    -- Import tracking
    status TEXT DEFAULT 'PENDING',              -- PENDING, PROCESSING, SUCCESS, SKIPPED, FAILED
    import_timestamp TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    processing_time_ms INTEGER,
    
    -- Worker tracking (for concurrent processing)
    worker_id TEXT,
    lock_acquired_at TIMESTAMPTZ,
    
    -- Results
    records_imported INTEGER DEFAULT 0,
    tags_imported INTEGER DEFAULT 0,
    tags_skipped INTEGER DEFAULT 0,
    error_message TEXT,
    
    -- Metadata
    file_format TEXT,                           -- 'LONG' or 'WIDE'
    total_tags_in_file INTEGER,
    total_rows_in_file INTEGER,
    
    UNIQUE(file_path, file_hash)
);

CREATE INDEX idx_file_imports_status ON file_imports(status);
CREATE INDEX idx_file_imports_timestamp ON file_imports(import_timestamp DESC);
CREATE INDEX idx_file_imports_hash ON file_imports(file_hash);
CREATE INDEX idx_file_imports_pending ON file_imports(status, id) WHERE status = 'PENDING';

-- ============================================================================
-- 5. TAG IMPORTS TRACKING (Per-Tag Import Status)
-- ============================================================================

DROP TABLE IF EXISTS tag_imports CASCADE;

CREATE TABLE tag_imports (
    id SERIAL PRIMARY KEY,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    tag_id TEXT NOT NULL,
    records_imported INTEGER DEFAULT 0,
    import_timestamp TIMESTAMPTZ DEFAULT NOW(),
    status TEXT DEFAULT 'SUCCESS',              -- SUCCESS, FAILED, SKIPPED
    error_message TEXT,
    
    UNIQUE(file_path, file_hash, tag_id)
);

CREATE INDEX idx_tag_imports_tag ON tag_imports(tag_id);
CREATE INDEX idx_tag_imports_file ON tag_imports(file_path);
CREATE INDEX idx_tag_imports_timestamp ON tag_imports(import_timestamp DESC);

-- ============================================================================
-- 6. IMPORT METRICS (Performance Monitoring)
-- ============================================================================

DROP TABLE IF EXISTS import_metrics CASCADE;

CREATE TABLE import_metrics (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    
    -- Performance metrics
    files_processed INTEGER DEFAULT 0,
    files_success INTEGER DEFAULT 0,
    files_failed INTEGER DEFAULT 0,
    files_skipped INTEGER DEFAULT 0,
    
    total_records_imported BIGINT DEFAULT 0,
    total_tags_imported INTEGER DEFAULT 0,
    
    avg_processing_time_ms INTEGER,
    max_processing_time_ms INTEGER,
    min_processing_time_ms INTEGER,
    
    -- Resource utilization
    worker_count INTEGER DEFAULT 1,
    queue_depth INTEGER DEFAULT 0,
    
    -- Time window (for aggregated metrics)
    window_start TIMESTAMPTZ,
    window_end TIMESTAMPTZ
);

CREATE INDEX idx_import_metrics_timestamp ON import_metrics(timestamp DESC);

-- ============================================================================
-- 7. SAMPLING STATE (Per-Tag Last Timestamp Tracking)
-- ============================================================================

DROP TABLE IF EXISTS tag_sampling_state CASCADE;

CREATE TABLE tag_sampling_state (
    tag_id TEXT PRIMARY KEY,
    last_imported_timestamp TIMESTAMPTZ NOT NULL,
    last_imported_value NUMERIC,
    sampling_frequency_seconds INTEGER DEFAULT 0,
    records_imported_total BIGINT DEFAULT 0,
    records_skipped_sampling BIGINT DEFAULT 0,
    last_updated TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_sampling_state_updated ON tag_sampling_state(last_updated DESC);

-- ============================================================================
-- VIEWS FOR MONITORING
-- ============================================================================

-- View: Import queue status
CREATE OR REPLACE VIEW v_import_queue AS
SELECT 
    status,
    COUNT(*) as file_count,
    SUM(file_size) as total_size_bytes,
    MIN(import_timestamp) as oldest_file,
    MAX(import_timestamp) as newest_file
FROM file_imports
GROUP BY status
ORDER BY 
    CASE status
        WHEN 'PROCESSING' THEN 1
        WHEN 'PENDING' THEN 2
        WHEN 'FAILED' THEN 3
        WHEN 'SKIPPED' THEN 4
        WHEN 'SUCCESS' THEN 5
    END;

-- View: Tag statistics
CREATE OR REPLACE VIEW v_tag_statistics AS
SELECT 
    tc.tag_id,
    tc.is_mapped,
    tc.first_seen,
    tc.last_seen,
    tc.record_count,
    COUNT(DISTINCT tfc.file_path) as file_count,
    SUM(tfc.file_size_bytes) as total_file_size_bytes
FROM tag_catalog tc
LEFT JOIN tag_file_catalog tfc ON tc.tag_id = tfc.tag_id
GROUP BY tc.tag_id, tc.is_mapped, tc.first_seen, tc.last_seen, tc.record_count
ORDER BY tc.last_seen DESC;

-- View: Recent imports
CREATE OR REPLACE VIEW v_recent_imports AS
SELECT 
    fi.file_path,
    fi.status,
    fi.records_imported,
    fi.tags_imported,
    fi.processing_time_ms,
    fi.import_timestamp,
    fi.error_message
FROM file_imports fi
ORDER BY fi.import_timestamp DESC
LIMIT 100;

-- ============================================================================
-- FUNCTIONS FOR IMPORT OPERATIONS
-- ============================================================================

-- Function: Get next pending file (with lock)
CREATE OR REPLACE FUNCTION get_next_pending_file(worker_name TEXT)
RETURNS TABLE (
    file_id INTEGER,
    file_path TEXT,
    file_hash TEXT,
    file_size BIGINT
) AS $$
BEGIN
    RETURN QUERY
    UPDATE file_imports
    SET 
        status = 'PROCESSING',
        worker_id = worker_name,
        lock_acquired_at = NOW(),
        started_at = NOW()
    WHERE id = (
        SELECT id FROM file_imports
        WHERE status = 'PENDING'
        ORDER BY id
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    )
    RETURNING id, file_imports.file_path, file_hash, file_size;
END;
$$ LANGUAGE plpgsql;

-- Function: Mark file as completed
CREATE OR REPLACE FUNCTION complete_file_import(
    file_id INTEGER,
    import_status TEXT,
    records_count INTEGER,
    tags_count INTEGER,
    error_msg TEXT DEFAULT NULL
)
RETURNS VOID AS $$
BEGIN
    UPDATE file_imports
    SET 
        status = import_status,
        completed_at = NOW(),
        processing_time_ms = EXTRACT(EPOCH FROM (NOW() - started_at)) * 1000,
        records_imported = records_count,
        tags_imported = tags_count,
        error_message = error_msg
    WHERE id = file_id;
END;
$$ LANGUAGE plpgsql;

-- Function: Update tag catalog entry
CREATE OR REPLACE FUNCTION upsert_tag_catalog(
    p_tag_id TEXT,
    p_first_seen TIMESTAMPTZ,
    p_last_seen TIMESTAMPTZ,
    p_last_file TEXT,
    p_record_count INTEGER,
    p_is_mapped BOOLEAN
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO tag_catalog (tag_id, first_seen, last_seen, last_file, record_count, is_mapped, last_updated)
    VALUES (p_tag_id, p_first_seen, p_last_seen, p_last_file, p_record_count, p_is_mapped, NOW())
    ON CONFLICT (tag_id) DO UPDATE SET
        first_seen = LEAST(tag_catalog.first_seen, EXCLUDED.first_seen),
        last_seen = GREATEST(tag_catalog.last_seen, EXCLUDED.last_seen),
        last_file = EXCLUDED.last_file,
        record_count = tag_catalog.record_count + EXCLUDED.record_count,
        is_mapped = EXCLUDED.is_mapped,
        last_updated = NOW();
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- GRANTS
-- ============================================================================

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO cereveate;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO cereveate;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO cereveate;

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Verify tables created
SELECT 
    schemaname,
    tablename,
    hasindexes,
    rowsecurity
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN ('sensor_data', 'tag_catalog', 'tag_file_catalog', 'file_imports', 'tag_imports', 'import_metrics', 'tag_sampling_state')
ORDER BY tablename;

-- Verify hypertable
SELECT 
    hypertable_schema,
    hypertable_name,
    num_dimensions,
    num_chunks,
    compression_enabled
FROM timescaledb_information.hypertables
WHERE hypertable_name = 'sensor_data';

-- Verify indexes
SELECT 
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('sensor_data', 'tag_catalog', 'file_imports', 'tag_imports')
ORDER BY tablename, indexname;

-- ============================================================================
-- ✅ SCHEMA COMPLETE
-- Tables: sensor_data (hypertable), tag_catalog, tag_file_catalog, 
--         file_imports, tag_imports, import_metrics, tag_sampling_state
-- Views: v_import_queue, v_tag_statistics, v_recent_imports
-- Functions: get_next_pending_file, complete_file_import, upsert_tag_catalog
-- ============================================================================
