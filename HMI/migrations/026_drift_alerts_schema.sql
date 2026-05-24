-- =============================================================================
-- Migration 026: Drift Detection Schema
-- =============================================================================
-- Adds the drift_alerts table to historian_analytics.
-- Three detection methods are supported per tag:
--   cusum   — cumulative sum, best for slow monotonic shift (bearing wear, fouling)
--   ewma    — exponentially weighted moving average, best for gradual degradation
--   zscore  — rolling Z-score, best for sudden baseline step changes
-- =============================================================================

CREATE TABLE IF NOT EXISTS historian_analytics.drift_alerts (
    id                  BIGSERIAL        PRIMARY KEY,
    tag_id              TEXT             NOT NULL,

    -- Which detector fired
    method              TEXT             NOT NULL
                            CHECK (method IN ('cusum', 'ewma', 'zscore')),

    -- Severity derived from magnitude
    severity            TEXT             NOT NULL DEFAULT 'info'
                            CHECK (severity IN ('info', 'warning', 'critical')),

    -- Quantified shift
    baseline_mean       DOUBLE PRECISION NOT NULL,   -- 30-day rolling mean
    current_mean        DOUBLE PRECISION NOT NULL,   -- mean of the last evaluation window
    drift_magnitude     DOUBLE PRECISION NOT NULL,   -- |current_mean - baseline_mean|
    drift_pct           DOUBLE PRECISION NOT NULL,   -- drift_magnitude / baseline_std * 100
    baseline_std        DOUBLE PRECISION NOT NULL,   -- 30-day rolling std

    -- Direction of drift: UP or DOWN
    direction           TEXT             NOT NULL DEFAULT 'UP'
                            CHECK (direction IN ('UP', 'DOWN')),

    -- CUSUM-specific
    cusum_score         DOUBLE PRECISION,            -- running cumulative sum value

    -- EWMA-specific
    ewma_value          DOUBLE PRECISION,            -- current EWMA level

    -- How long has this drift been active
    started_at          TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    last_updated        TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    consecutive_hours   INTEGER          NOT NULL DEFAULT 1,

    -- Lifecycle
    is_active           BOOLEAN          NOT NULL DEFAULT TRUE,
    acknowledged        BOOLEAN          NOT NULL DEFAULT FALSE,
    acknowledged_at     TIMESTAMPTZ,
    acknowledged_by     TEXT,
    resolved_at         TIMESTAMPTZ,

    -- Metadata
    eval_window_hours   INTEGER          NOT NULL DEFAULT 1,
    baseline_days       INTEGER          NOT NULL DEFAULT 30,
    created_at          TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

-- One active alert per (tag, method) at a time
CREATE UNIQUE INDEX IF NOT EXISTS uq_drift_alerts_active
    ON historian_analytics.drift_alerts (tag_id, method)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS ix_drift_alerts_tag_active
    ON historian_analytics.drift_alerts (tag_id, is_active, last_updated DESC);

CREATE INDEX IF NOT EXISTS ix_drift_alerts_severity
    ON historian_analytics.drift_alerts (severity, is_active, last_updated DESC);

-- updated_at trigger (reuse function from migration 025)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_drift_alerts_updated_at'
    ) THEN
        CREATE TRIGGER trg_drift_alerts_updated_at
            BEFORE UPDATE ON historian_analytics.drift_alerts
            FOR EACH ROW EXECUTE FUNCTION historian_analytics.set_updated_at();
    END IF;
END
$$;

COMMENT ON TABLE historian_analytics.drift_alerts IS
    'Long-term baseline drift detection results. One row per active (tag, method). '
    'Populated hourly by DriftDetectorService. '
    'Methods: cusum (slow monotonic), ewma (gradual degradation), zscore (step change).';
