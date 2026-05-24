-- =============================================================================
-- Migration 0005 — Add ingest_timestamp + tag priority for multi-PLC scale-out
-- Run once against Automation_DB (PostgreSQL / TimescaleDB)
-- Safe to run multiple times (all operations use IF NOT EXISTS / DO NOTHING).
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. historian_raw.historian_timeseries — add ingest_timestamp column
--    Meaning : the wall-clock UTC time when the C# process wrote this row.
--    Use     : ingest_timestamp - opc_timestamp = acquisition + queue latency
--    Nullable: YES for backward compat with rows written before this migration.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE historian_raw.historian_timeseries
    ADD COLUMN IF NOT EXISTS ingest_timestamp TIMESTAMPTZ DEFAULT NULL;

-- Back-fill historical rows so queries don't have to special-case NULL.
-- Uses time as a proxy (actual ingest was ~same second).
UPDATE historian_raw.historian_timeseries
SET    ingest_timestamp = time
WHERE  ingest_timestamp IS NULL;

-- Optional: tighten to NOT NULL once back-fill confirmed
-- ALTER TABLE historian_raw.historian_timeseries
--     ALTER COLUMN ingest_timestamp SET NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. historian_meta.tag_master — add priority column
--    Meaning : write priority for rate-control bypass
--              1=Critical (always write, no deadband), 5=Normal, 10=Low
--    Default : 5 (normal) — existing tags are unaffected
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE historian_meta.tag_master
    ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 5;

-- Optional: add a check constraint so no one sets priority outside 1–10
ALTER TABLE historian_meta.tag_master
    DROP CONSTRAINT IF EXISTS chk_tag_master_priority;
ALTER TABLE historian_meta.tag_master
    ADD  CONSTRAINT chk_tag_master_priority CHECK (priority BETWEEN 1 AND 10);

-- Mark your known critical tags immediately:
-- UPDATE historian_meta.tag_master SET priority = 1
-- WHERE tag_id IN ('TY1101A', 'TY1101B', 'PT_MAIN_HEADER');

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Verify
-- ─────────────────────────────────────────────────────────────────────────────
SELECT column_name, data_type, is_nullable, column_default
FROM   information_schema.columns
WHERE  table_schema = 'historian_raw'
AND    table_name   = 'historian_timeseries'
ORDER  BY ordinal_position;

SELECT column_name, data_type, column_default
FROM   information_schema.columns
WHERE  table_schema = 'historian_meta'
AND    table_name   = 'tag_master'
AND    column_name IN ('priority', 'deadband_value', 'db_logging_interval_ms');
