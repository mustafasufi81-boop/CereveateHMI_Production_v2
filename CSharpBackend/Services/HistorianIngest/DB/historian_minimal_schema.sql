-- MINIMAL HISTORIAN SCHEMA FOR 10K+ TAGS
-- Run this in PostgreSQL database: Cereveate

-- Create schemas
CREATE SCHEMA IF NOT EXISTS historian_meta;
CREATE SCHEMA IF NOT EXISTS historian_raw;
CREATE SCHEMA IF NOT EXISTS historian_admin;

-- ============================================================
-- TAG MASTER TABLE (Configuration)
-- ============================================================
CREATE TABLE IF NOT EXISTS historian_meta.tag_master (
    tag_id TEXT PRIMARY KEY,
    tag_name TEXT NOT NULL,
    description TEXT,
    plant TEXT,
    area TEXT,
    equipment TEXT,
    data_type TEXT NOT NULL DEFAULT 'Double', -- Double, Integer, Boolean, String
    eng_unit TEXT,
    db_logging_interval_ms INTEGER NOT NULL DEFAULT 1000,
    deadband_value DOUBLE PRECISION DEFAULT 0.0,
    enabled BOOLEAN NOT NULL DEFAULT true,
    db_table_name TEXT NOT NULL DEFAULT 'historian_raw.historian_timeseries',
    mapping_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tag_master_enabled ON historian_meta.tag_master(enabled) WHERE enabled = true;
CREATE INDEX IF NOT EXISTS idx_tag_master_version ON historian_meta.tag_master(mapping_version);

-- ============================================================
-- TIMESERIES DATA TABLE (Main historian data)
-- ============================================================
CREATE TABLE IF NOT EXISTS historian_raw.historian_timeseries (
    time TIMESTAMPTZ NOT NULL,
    tag_id TEXT NOT NULL,
    value_num DOUBLE PRECISION,
    value_text TEXT,
    value_bool BOOLEAN,
    quality TEXT NOT NULL DEFAULT 'U', -- G=Good, B=Bad, U=Uncertain
    source TEXT NOT NULL DEFAULT 'OPC',
    mapping_version INTEGER NOT NULL,
    db_table_name TEXT NOT NULL
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_timeseries_time ON historian_raw.historian_timeseries(time DESC);
CREATE INDEX IF NOT EXISTS idx_timeseries_tag_time ON historian_raw.historian_timeseries(tag_id, time DESC);

-- Optional: Convert to TimescaleDB hypertable for better performance
-- SELECT create_hypertable('historian_raw.historian_timeseries', 'time', if_not_exists => TRUE);

-- ============================================================
-- LATEST VALUES TABLE (Current tag values)
-- ============================================================
CREATE TABLE IF NOT EXISTS historian_raw.historian_latest_value (
    tag_id TEXT PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL,
    value_num DOUBLE PRECISION,
    value_text TEXT,
    value_bool BOOLEAN,
    quality TEXT NOT NULL DEFAULT 'U',
    source TEXT NOT NULL DEFAULT 'OPC',
    mapping_version INTEGER NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- WRITER CHECKPOINTS (For service restart)
-- ============================================================
CREATE TABLE IF NOT EXISTS historian_admin.writer_checkpoints (
    writer_name TEXT PRIMARY KEY,
    last_processed_at TIMESTAMPTZ NOT NULL,
    last_mapping_version INTEGER,
    info JSONB,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- EVENTS TABLE (System logging)
-- ============================================================
CREATE TABLE IF NOT EXISTS historian_admin.events (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL, -- INFO, WARNING, ERROR
    message TEXT NOT NULL,
    details JSONB,
    writer_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_created ON historian_admin.events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_type ON historian_admin.events(event_type);

-- ============================================================
-- SAMPLE DATA: Insert a few test tag mappings
-- ============================================================
INSERT INTO historian_meta.tag_master (tag_id, tag_name, data_type, db_logging_interval_ms, enabled) 
VALUES 
    ('Random.Int1', 'Random Integer 1', 'Integer', 1000, true),
    ('Random.Real4', 'Random Real 4', 'Double', 1000, true)
ON CONFLICT (tag_id) DO NOTHING;

-- ============================================================
-- GRANT PERMISSIONS (if using cereveate user)
-- ============================================================
GRANT ALL ON SCHEMA historian_meta TO cereveate;
GRANT ALL ON SCHEMA historian_raw TO cereveate;
GRANT ALL ON SCHEMA historian_admin TO cereveate;

GRANT ALL ON ALL TABLES IN SCHEMA historian_meta TO cereveate;
GRANT ALL ON ALL TABLES IN SCHEMA historian_raw TO cereveate;
GRANT ALL ON ALL TABLES IN SCHEMA historian_admin TO cereveate;

GRANT ALL ON ALL SEQUENCES IN SCHEMA historian_admin TO cereveate;

-- Success message
SELECT 'Historian schema created successfully!' AS status;
