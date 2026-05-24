-- =============================================================================
-- PHASE 1 ALARM SYSTEM MIGRATION
-- Run once against Automation_DB before starting the updated service.
--
-- VERIFIED EXISTING STATE (checked 2026-05-08):
--   historian_events columns: time, event_id, tag_id, event_type, severity,
--     message, metadata, alarm_state, alarm_priority, acknowledged_by,
--     acknowledged_at, cleared_at, alarm_setpoint, alarm_actual_value,
--     parent_alarm_id, cleared_by, clear_reason, clear_notes
--
--   historian_events constraints KEPT UNCHANGED:
--     chk_event_type              CHECK event_type ~ '^(SYSTEM|WRITER|...)_...$'
--     alarm_priority_check        CHECK alarm_priority BETWEEN 1 AND 5
--     alarm_state_check           CHECK alarm_state IN ('ACTIVE','ACKNOWLEDGED','CLEARED','SUPPRESSED')
--
--   alarm_active: does NOT exist — will be created here
--   tag_master alarm_onset_delay_s: does NOT exist — will be added here
--
-- NEW 4-STATE ISA-18.2 LOGIC (ACTIVE_UNACK, ACTIVE_ACK, RTN_UNACK, CLEARED)
--   lives ONLY in the new alarm_active table.
--   historian_events continues to use existing ACTIVE/ACKNOWLEDGED/CLEARED/SUPPRESSED.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- STEP 1 — Clear the three Python test rows that block Random.Real4
-- ---------------------------------------------------------------------------
UPDATE historian_raw.historian_events
SET    alarm_state = 'CLEARED'
WHERE  event_id IN (32654, 32655, 32656);

-- ---------------------------------------------------------------------------
-- STEP 2 — Add new audit/identity columns to historian_events
--          Existing columns and constraints are NOT touched.
-- ---------------------------------------------------------------------------
ALTER TABLE historian_raw.historian_events
    ADD COLUMN IF NOT EXISTS alarm_level    TEXT,
    ADD COLUMN IF NOT EXISTS occurrence_id  UUID DEFAULT gen_random_uuid(),
    ADD COLUMN IF NOT EXISTS instance_seq   INTEGER;

-- ---------------------------------------------------------------------------
-- STEP 3 — Create alarm_active (fast active-alarm lookup, 4-state only)
--          Row is DELETED when alarm reaches CLEARED.
--          This is the only table that holds Phase 1 ISA-18.2 states.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS historian_raw.alarm_active (
    alarm_key        TEXT        PRIMARY KEY,   -- '{tag_id}:{level}'
    tag_id           TEXT        NOT NULL,
    level            TEXT        NOT NULL,       -- 'High','HighHigh','Low','LowLow'
    alarm_state      TEXT        NOT NULL CHECK (alarm_state IN (
                                     'ACTIVE_UNACK',
                                     'ACTIVE_ACK',
                                     'RTN_UNACK'
                                     -- CLEARED is never stored — row deleted on CLEARED
                                 )),
    current_event_id BIGINT,
    occurrence_id    UUID        NOT NULL,
    instance_seq     INTEGER     NOT NULL DEFAULT 1,
    raised_at        TIMESTAMPTZ NOT NULL,
    raised_value     DOUBLE PRECISION,
    setpoint_value   DOUBLE PRECISION,
    ack_at           TIMESTAMPTZ,
    ack_by           TEXT,
    rtn_at           TIMESTAMPTZ,
    priority         INTEGER,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
    -- Phase 2 adds: shelved_until, shelved_by, alarm_class
    -- Phase 3 adds: first_out, first_out_seq, first_out_group
);

CREATE INDEX IF NOT EXISTS idx_alarm_active_tag ON historian_raw.alarm_active(tag_id);

-- ---------------------------------------------------------------------------
-- STEP 4 — Add onset delay column to tag_master (not present yet)
-- ---------------------------------------------------------------------------
ALTER TABLE historian_meta.tag_master
    ADD COLUMN IF NOT EXISTS alarm_onset_delay_s INTEGER DEFAULT 0;

-- ---------------------------------------------------------------------------
-- STEP 5 — Verify
-- ---------------------------------------------------------------------------
SELECT 'alarm_active exists' AS check,
       EXISTS(SELECT 1 FROM information_schema.tables
              WHERE table_schema = 'historian_raw' AND table_name = 'alarm_active')::TEXT AS result
UNION ALL
SELECT 'alarm_onset_delay_s on tag_master',
       EXISTS(SELECT 1 FROM information_schema.columns
              WHERE table_schema = 'historian_meta' AND table_name = 'tag_master'
                AND column_name = 'alarm_onset_delay_s')::TEXT
UNION ALL
SELECT 'occurrence_id on historian_events',
       EXISTS(SELECT 1 FROM information_schema.columns
              WHERE table_schema = 'historian_raw' AND table_name = 'historian_events'
                AND column_name = 'occurrence_id')::TEXT
UNION ALL
SELECT 'blocking rows cleared',
       (SELECT COUNT(*) FROM historian_raw.historian_events
        WHERE event_id IN (32654,32655,32656) AND alarm_state != 'CLEARED')::TEXT || ' remaining (expect 0)';
