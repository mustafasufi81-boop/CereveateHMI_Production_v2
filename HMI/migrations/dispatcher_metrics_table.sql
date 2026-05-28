-- ============================================================
-- Dispatcher Metrics Persistence — Step 4
-- Schema: historian_analytics
-- Run once manually:
--   psql -U <user> -d Automation_DB -f migrations/dispatcher_metrics_table.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS historian_analytics.dispatcher_metrics (
    id                    BIGSERIAL PRIMARY KEY,
    recorded_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type            TEXT        NOT NULL,   -- SNAPSHOT | STATE_CHANGE | REJECTION | TIMEOUT

    -- dispatcher identity
    thread_id             INTEGER,
    apartment             TEXT,

    -- queue health
    queue_depth           INTEGER,
    max_queue_depth       INTEGER,

    -- counters (absolute values at time of snapshot)
    rejected_count        BIGINT,
    ops_processed         BIGINT,
    timeout_count         INTEGER,

    -- state machine
    state                 TEXT,
    state_reason          TEXT,
    last_state_change_utc TIMESTAMPTZ,

    -- timestamps from dispatcher
    last_success          TIMESTAMPTZ,
    last_heartbeat        TIMESTAMPTZ,
    last_error            TEXT
);

-- Index for time-range queries (most common access pattern)
CREATE INDEX IF NOT EXISTS idx_dispatcher_metrics_recorded_at
    ON historian_analytics.dispatcher_metrics (recorded_at DESC);

-- Index for filtering by event type (e.g. only STATE_CHANGE events)
CREATE INDEX IF NOT EXISTS idx_dispatcher_metrics_event_type
    ON historian_analytics.dispatcher_metrics (event_type, recorded_at DESC);

-- Index for filtering by state (e.g. only Degraded rows)
CREATE INDEX IF NOT EXISTS idx_dispatcher_metrics_state
    ON historian_analytics.dispatcher_metrics (state, recorded_at DESC);

-- ── Retention note ──────────────────────────────────────────────────────────
-- Prune rows older than 30 days (run manually or via pg_cron):
--
--   DELETE FROM historian_analytics.dispatcher_metrics
--   WHERE recorded_at < NOW() - INTERVAL '30 days';
--
-- pg_cron job (once pg_cron is configured):
--   SELECT cron.schedule('0 3 * * *',
--     $$DELETE FROM historian_analytics.dispatcher_metrics
--       WHERE recorded_at < NOW() - INTERVAL '30 days'$$);
-- ────────────────────────────────────────────────────────────────────────────
