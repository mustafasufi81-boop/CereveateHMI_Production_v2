-- ============================================================
-- PEWS (Predictive Early Warning System) - Database Schema
-- Run once against Automation_DB to create analytics schema
-- Zero impact on existing tables/schemas
-- ============================================================

CREATE SCHEMA IF NOT EXISTS historian_analytics;

-- -------------------------------------------------------
-- 1. Tag Baselines — computed nightly per tag
--    Stores "what normal looks like" for each tag
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS historian_analytics.tag_baselines (
    tag_id          TEXT PRIMARY KEY,
    mean_value      DOUBLE PRECISION,
    std_value       DOUBLE PRECISION,
    min_value       DOUBLE PRECISION,
    max_value       DOUBLE PRECISION,
    q1_value        DOUBLE PRECISION,
    q3_value        DOUBLE PRECISION,
    normal_roc_max  DOUBLE PRECISION,   -- max normal rate-of-change per second
    last_computed   TIMESTAMPTZ DEFAULT NOW(),
    sample_count    INT
);

-- -------------------------------------------------------
-- 2. Early Warnings — one row per fired warning
--    Only written when anomaly is detected
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS historian_analytics.early_warnings (
    id              BIGSERIAL,
    time            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tag_id          TEXT NOT NULL,
    warning_level   INT NOT NULL,          -- 1=INFO, 2=CAUTION, 3=WARNING, 4=ALERT
    warning_type    TEXT NOT NULL,         -- 'spike','drift','rate_of_change','anomaly'
    current_value   DOUBLE PRECISION,
    avg_value       DOUBLE PRECISION,      -- baseline average at time of warning
    deviation_pct   DOUBLE PRECISION,      -- % deviation from average
    threshold_value DOUBLE PRECISION,      -- threshold that was breached
    message         TEXT,                  -- human-readable reason
    acknowledged    BOOLEAN DEFAULT FALSE,
    ack_by          TEXT,
    ack_time        TIMESTAMPTZ,
    PRIMARY KEY (time, id)
);

SELECT create_hypertable('historian_analytics.early_warnings', 'time',
    if_not_exists => TRUE);

-- Compression: segment by tag_id so each tag compresses independently,
-- order by time DESC for fast recent-data reads (same pattern as historian_timeseries)
ALTER TABLE historian_analytics.early_warnings
    SET (timescaledb.compress = true,
         timescaledb.compress_segmentby = 'tag_id',
         timescaledb.compress_orderby = 'time DESC');

-- Compress chunks older than 7 days (matches historian_timeseries policy)
SELECT add_compression_policy('historian_analytics.early_warnings',
    INTERVAL '7 days', if_not_exists => TRUE);

-- Retention: drop chunks older than 2 years (matches historian_timeseries)
SELECT add_retention_policy('historian_analytics.early_warnings',
    INTERVAL '2 years', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_early_warnings_tag_id
    ON historian_analytics.early_warnings (tag_id, time DESC);

CREATE INDEX IF NOT EXISTS idx_early_warnings_unacked
    ON historian_analytics.early_warnings (acknowledged, time DESC)
    WHERE acknowledged = FALSE;

-- -------------------------------------------------------
-- 3. Tag Predictions — only written when warning triggered
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS historian_analytics.tag_predictions (
    id              BIGSERIAL,
    time            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tag_id          TEXT NOT NULL,
    predicted_value DOUBLE PRECISION,
    prediction_horizon_min INT,
    confidence      DOUBLE PRECISION,
    model_used      TEXT,
    actual_value    DOUBLE PRECISION,
    PRIMARY KEY (time, id)
);

SELECT create_hypertable('historian_analytics.tag_predictions', 'time',
    if_not_exists => TRUE);

-- Compression: segment by tag_id, order by time DESC
ALTER TABLE historian_analytics.tag_predictions
    SET (timescaledb.compress = true,
         timescaledb.compress_segmentby = 'tag_id',
         timescaledb.compress_orderby = 'time DESC');

-- Compress chunks older than 7 days
SELECT add_compression_policy('historian_analytics.tag_predictions',
    INTERVAL '7 days', if_not_exists => TRUE);

-- Retention: drop chunks older than 2 years
SELECT add_retention_policy('historian_analytics.tag_predictions',
    INTERVAL '2 years', if_not_exists => TRUE);

-- -------------------------------------------------------
-- Retention: auto-delete acknowledged warnings > 90 days
-- (run as a scheduled job or pg_cron)
-- -------------------------------------------------------
-- DELETE FROM historian_analytics.early_warnings
-- WHERE acknowledged = TRUE AND time < NOW() - INTERVAL '90 days';
