-- =============================================================================
-- Migration: alarm_sequence_migration.sql
-- Purpose : Add global transition_seq to alarm_active and historian_events for
--           deterministic ordering — fixes Issue 1 (missing sequence numbers).
--
-- Issue addressed:
--   Without a global sequence, WebSocket reconnects may see out-of-order or
--   duplicate events. React HMI can now track the highest transition_seq it has
--   received and request only missing transitions on reconnect.
--
-- Run once against Automation_DB (or the DB hosting historian_raw schema).
-- Idempotent: uses IF NOT EXISTS / DO NOTHING guards throughout.
-- =============================================================================

BEGIN;

-- ─── 1. Global monotonic sequence ─────────────────────────────────────────────
-- Shared across all alarm transitions so ordering is absolute, not per-table.
CREATE SEQUENCE IF NOT EXISTS historian_raw.alarm_transition_seq
    START     1
    INCREMENT 1
    CACHE     100          -- batch-allocate for performance
    NO CYCLE;

-- ─── 2. historian_events — tag each journal row with its global sequence ───────
ALTER TABLE historian_raw.historian_events
    ADD COLUMN IF NOT EXISTS transition_seq BIGINT
        DEFAULT nextval('historian_raw.alarm_transition_seq');

-- Back-fill existing rows in event_id order (best-effort historical ordering)
DO $$
DECLARE
    r RECORD;
    seq BIGINT;
BEGIN
    FOR r IN
        SELECT event_id
        FROM   historian_raw.historian_events
        WHERE  transition_seq IS NULL
        ORDER  BY event_id
    LOOP
        seq := nextval('historian_raw.alarm_transition_seq');
        UPDATE historian_raw.historian_events
        SET    transition_seq = seq
        WHERE  event_id = r.event_id;
    END LOOP;
END;
$$;

-- Make NOT NULL once back-fill is complete
ALTER TABLE historian_raw.historian_events
    ALTER COLUMN transition_seq SET NOT NULL;

-- ─── 3. alarm_active — track sequence of most-recent state change ─────────────
ALTER TABLE historian_raw.alarm_active
    ADD COLUMN IF NOT EXISTS transition_seq BIGINT;

-- Set existing rows to 0 (pre-migration sentinel — any real value will be > 0)
UPDATE historian_raw.alarm_active
SET    transition_seq = 0
WHERE  transition_seq IS NULL;

ALTER TABLE historian_raw.alarm_active
    ALTER COLUMN transition_seq SET NOT NULL,
    ALTER COLUMN transition_seq SET DEFAULT 0;

-- ─── 4. Index for snapshot + reconnect queries ────────────────────────────────
-- HMI reconnect pattern: SELECT * FROM historian_events WHERE transition_seq > :last_seq
CREATE INDEX IF NOT EXISTS idx_historian_events_transition_seq
    ON historian_raw.historian_events (transition_seq);

-- ─── 5. Verification ─────────────────────────────────────────────────────────
DO $$
BEGIN
    RAISE NOTICE 'alarm_transition_seq sequence created (or already exists)';
    RAISE NOTICE 'historian_events.transition_seq column: %',
        (SELECT data_type FROM information_schema.columns
         WHERE  table_schema = 'historian_raw'
           AND  table_name   = 'historian_events'
           AND  column_name  = 'transition_seq');
    RAISE NOTICE 'alarm_active.transition_seq column: %',
        (SELECT data_type FROM information_schema.columns
         WHERE  table_schema = 'historian_raw'
           AND  table_name   = 'alarm_active'
           AND  column_name  = 'transition_seq');
END;
$$;

COMMIT;
