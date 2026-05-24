-- ============================================================
-- Automation_DB Schema Setup
-- Run this once against Automation_DB to create all required
-- schemas, tables, indexes, and grants.
-- ============================================================

-- Schemas
CREATE SCHEMA IF NOT EXISTS historian_meta;
CREATE SCHEMA IF NOT EXISTS historian_raw;
CREATE SCHEMA IF NOT EXISTS historian_admin;

-- ============================================================
-- historian_meta.tag_master
-- Source of truth for which OPC tags get written to DB.
-- MappingCacheService SELECTs all columns below.
-- ============================================================
CREATE TABLE IF NOT EXISTS historian_meta.tag_master (
    tag_id                  TEXT        PRIMARY KEY,
    tag_name                TEXT        NOT NULL,
    description             TEXT,
    plant                   TEXT,
    area                    TEXT,
    equipment               TEXT,
    data_type               TEXT        NOT NULL DEFAULT 'Double',
    eng_unit                TEXT,
    db_logging_interval_ms  INTEGER     NOT NULL DEFAULT 1000,
    deadband_enabled        BOOLEAN     NOT NULL DEFAULT false,
    deadband_value          DOUBLE PRECISION,
    enabled                 BOOLEAN     NOT NULL DEFAULT true,
    db_table_name           TEXT        NOT NULL DEFAULT 'historian_raw.historian_timeseries',
    mapping_version         BIGINT      NOT NULL DEFAULT 1,
    config_updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by              TEXT,
    server_progid           TEXT,   -- OPC server ProgID filter (NULL = wildcard)
    server_host             TEXT    -- OPC server host (NULL = local)
);

-- Trigger: auto-bump mapping_version + config_updated_at on every UPDATE
CREATE OR REPLACE FUNCTION historian_meta.bump_mapping_version()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.mapping_version  := OLD.mapping_version + 1;
    NEW.config_updated_at := NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_bump_mapping_version ON historian_meta.tag_master;
CREATE TRIGGER trg_bump_mapping_version
    BEFORE UPDATE ON historian_meta.tag_master
    FOR EACH ROW EXECUTE FUNCTION historian_meta.bump_mapping_version();

-- NOTIFY trigger: MappingCacheService listens on 'mapping_updated'
CREATE OR REPLACE FUNCTION historian_meta.notify_mapping_updated()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_notify('mapping_updated', TG_OP || ':' || COALESCE(NEW.tag_id, OLD.tag_id));
    RETURN COALESCE(NEW, OLD);
END;
$$;

DROP TRIGGER IF EXISTS trg_notify_mapping_updated ON historian_meta.tag_master;
CREATE TRIGGER trg_notify_mapping_updated
    AFTER INSERT OR UPDATE OR DELETE ON historian_meta.tag_master
    FOR EACH ROW EXECUTE FUNCTION historian_meta.notify_mapping_updated();

-- ============================================================
-- historian_raw.historian_timeseries
-- Main time-series data table.
-- DbWriterService COPYs: time, tag_id, value_num, value_text,
--   value_bool, quality, sample_source, mapping_version, opc_timestamp
-- ============================================================
CREATE TABLE IF NOT EXISTS historian_raw.historian_timeseries (
    id              BIGSERIAL   PRIMARY KEY,
    time            TIMESTAMPTZ NOT NULL,
    tag_id          TEXT        NOT NULL,
    value_num       DOUBLE PRECISION,
    value_text      TEXT,
    value_bool      BOOLEAN,
    quality         TEXT        NOT NULL DEFAULT 'Unknown',
    sample_source   TEXT        NOT NULL DEFAULT 'OPC_Pool',
    mapping_version INTEGER     NOT NULL DEFAULT 1,
    opc_timestamp   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_hist_ts_tag_time
    ON historian_raw.historian_timeseries(tag_id, time DESC);

CREATE INDEX IF NOT EXISTS idx_hist_ts_time
    ON historian_raw.historian_timeseries(time DESC);

-- ============================================================
-- historian_raw.historian_latest_value
-- DbWriterService UPSERTs latest value per tag here.
-- ============================================================
CREATE TABLE IF NOT EXISTS historian_raw.historian_latest_value (
    tag_id               TEXT        PRIMARY KEY,
    last_time            TIMESTAMPTZ NOT NULL,
    last_value_num       DOUBLE PRECISION,
    last_value_text      TEXT,
    last_value_bool      BOOLEAN,
    last_quality         TEXT,
    last_mapping_version INTEGER,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- historian_admin tables
-- ============================================================
CREATE TABLE IF NOT EXISTS historian_admin.spool_applied (
    id          BIGSERIAL   PRIMARY KEY,
    file_hash   TEXT        NOT NULL UNIQUE,
    file_path   TEXT        NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rows_applied BIGINT     NOT NULL,
    shard_index INTEGER
);

CREATE TABLE IF NOT EXISTS historian_admin.writer_checkpoints (
    writer_name          TEXT        PRIMARY KEY,
    last_processed_at    TIMESTAMPTZ NOT NULL,
    last_mapping_version INTEGER     NOT NULL,
    info                 JSONB,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS historian_admin.events (
    id          BIGSERIAL   PRIMARY KEY,
    event_type  TEXT        NOT NULL,
    severity    TEXT        NOT NULL,
    message     TEXT        NOT NULL,
    details     JSONB,
    writer_name TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Grants
-- ============================================================
GRANT USAGE ON SCHEMA historian_meta  TO cereveate;
GRANT USAGE ON SCHEMA historian_raw   TO cereveate;
GRANT USAGE ON SCHEMA historian_admin TO cereveate;
GRANT ALL ON ALL TABLES IN SCHEMA historian_meta  TO cereveate;
GRANT ALL ON ALL TABLES IN SCHEMA historian_raw   TO cereveate;
GRANT ALL ON ALL TABLES IN SCHEMA historian_admin TO cereveate;
GRANT ALL ON ALL SEQUENCES IN SCHEMA historian_raw   TO cereveate;
GRANT ALL ON ALL SEQUENCES IN SCHEMA historian_admin TO cereveate;

-- ============================================================
-- Done
-- ============================================================
SELECT 'Schema setup complete for Automation_DB' AS result;
