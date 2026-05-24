-- =============================================================================
-- Migration 025: Predictive Alarm Engine Schema
-- =============================================================================
-- Creates the historian_analytics schema with 4 tables:
--   tag_alarm_config  — per-tag monitoring config (limits, model, horizon)
--   predictive_alarms — pre-alarms raised by the engine
--   screener_state    — warm-restart state for Stage 1 screener
--   model_cache       — per-tag per-model performance / drift tracking
-- =============================================================================

-- ── Schema ───────────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS historian_analytics;

-- ── 1. Tag Alarm Configuration ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS historian_analytics.tag_alarm_config (
    tag_id                    TEXT            PRIMARY KEY,
    tag_description           TEXT,
    unit                      TEXT,

    -- Alarm limits (NULL = not monitored in that direction)
    hi_hi_limit               DOUBLE PRECISION,
    hi_limit                  DOUBLE PRECISION,
    lo_limit                  DOUBLE PRECISION,
    lo_lo_limit               DOUBLE PRECISION,

    -- Hysteresis / deadband (prevents chattering on threshold)
    deadband                  DOUBLE PRECISION NOT NULL DEFAULT 0.0,

    -- Forecast settings
    preferred_model           TEXT NOT NULL DEFAULT 'auto'
                                CHECK (preferred_model IN ('auto', 'lr', 'hw', 'fft', 'arima')),
    forecast_horizon_minutes  INTEGER NOT NULL DEFAULT 30
                                CHECK (forecast_horizon_minutes BETWEEN 1 AND 480),

    -- Suppression: after an alarm fires, don't re-fire for this many minutes
    suppression_window_minutes INTEGER NOT NULL DEFAULT 60
                                CHECK (suppression_window_minutes >= 0),

    -- Tag priority (1=CRITICAL, 2=HIGH, 3=MEDIUM, 4=LOW, 5=BACKGROUND)
    priority                  INTEGER NOT NULL DEFAULT 3
                                CHECK (priority BETWEEN 1 AND 5),

    enabled                   BOOLEAN NOT NULL DEFAULT TRUE,

    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by                TEXT
);

COMMENT ON TABLE  historian_analytics.tag_alarm_config IS
    'Per-tag configuration for the predictive pre-alarm engine. Each enabled row is '
    'screened every 60 s (Stage 1) and forecasted if suspicious (Stage 2).';

COMMENT ON COLUMN historian_analytics.tag_alarm_config.preferred_model IS
    'auto = engine picks best from benchmark; lr/hw/fft/arima = fixed model.';

COMMENT ON COLUMN historian_analytics.tag_alarm_config.priority IS
    '1=CRITICAL (always run), 2=HIGH, 3=MEDIUM, 4=LOW, 5=BACKGROUND (best-effort).';

-- ── 2. Predictive Alarms (raised by engine) ───────────────────────────────────
CREATE TABLE IF NOT EXISTS historian_analytics.predictive_alarms (
    id                  BIGSERIAL       PRIMARY KEY,
    tag_id              TEXT            NOT NULL,
    direction           TEXT            NOT NULL
                            CHECK (direction IN ('HIGH', 'LOW', 'HIHI', 'LOLO')),
    confidence          TEXT            NOT NULL
                            CHECK (confidence IN ('HIGH', 'MEDIUM', 'LOW')),

    -- What the model predicted
    predicted_value     DOUBLE PRECISION,  -- projected value at breach point
    limit_value         DOUBLE PRECISION,  -- the limit that will be exceeded
    eta_minutes         INTEGER,           -- estimated minutes to breach
    predicted_breach_at TIMESTAMPTZ,       -- absolute timestamp of projected breach

    -- Model info
    model_used          TEXT,
    forecast_json       TEXT,              -- JSON: [{t: ISO, v: float}, ...]

    -- Lifecycle
    raised_at           TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    active              BOOLEAN         NOT NULL DEFAULT TRUE,
    resolved_at         TIMESTAMPTZ,       -- set when tag moves away from threshold
    resolution_reason   TEXT,              -- 'operator_ack', 'value_recovered', 'suppressed', 'expired'

    -- Acknowledgement
    acknowledged        BOOLEAN         NOT NULL DEFAULT FALSE,
    acknowledged_at     TIMESTAMPTZ,
    acknowledged_by     TEXT,
    notes               TEXT,

    -- Suppression
    suppressed_until    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_pred_alarms_tag_active
    ON historian_analytics.predictive_alarms (tag_id, active);

CREATE INDEX IF NOT EXISTS ix_pred_alarms_raised_at
    ON historian_analytics.predictive_alarms (raised_at DESC);

CREATE INDEX IF NOT EXISTS ix_pred_alarms_active
    ON historian_analytics.predictive_alarms (active)
    WHERE active = TRUE;

COMMENT ON TABLE historian_analytics.predictive_alarms IS
    'Pre-alarms raised by the 2-stage predictive alarm engine. '
    'active=TRUE means operator has not yet acknowledged or value has not recovered.';

-- ── 3. Screener State (warm-restart cache) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS historian_analytics.screener_state (
    tag_id          TEXT            PRIMARY KEY,
    is_suspicious   BOOLEAN         NOT NULL DEFAULT FALSE,
    reason          TEXT,
    slope           DOUBLE PRECISION,
    quality_score   DOUBLE PRECISION,
    n_points        INTEGER,
    last_screened   TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE historian_analytics.screener_state IS
    'Stage 1 screener results. Written every cycle; read on warm restart to '
    'restore state without a full rescan.';

-- ── 4. Model Cache (performance + drift) ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS historian_analytics.model_cache (
    tag_id              TEXT    NOT NULL,
    model               TEXT    NOT NULL,
    rmse                DOUBLE PRECISION,
    mae                 DOUBLE PRECISION,
    r2                  DOUBLE PRECISION,
    drift_score         DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    tuned_params_json   TEXT,
    fitted_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tag_id, model)
);

COMMENT ON TABLE historian_analytics.model_cache IS
    'Per-tag per-model accuracy metrics from last Stage 2 run. '
    'drift_score > 0.3 triggers model re-fit; > 0.7 raises model-drift warning.';

-- ── Trigger: auto-update updated_at on tag_alarm_config ──────────────────────
CREATE OR REPLACE FUNCTION historian_analytics.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_tag_alarm_config_updated_at
    ON historian_analytics.tag_alarm_config;

CREATE TRIGGER trg_tag_alarm_config_updated_at
    BEFORE UPDATE ON historian_analytics.tag_alarm_config
    FOR EACH ROW EXECUTE FUNCTION historian_analytics.set_updated_at();

-- ── Seed: example tag (remove or adapt for your plant) ───────────────────────
-- INSERT INTO historian_analytics.tag_alarm_config
--     (tag_id, tag_description, unit, hi_limit, lo_limit, preferred_model,
--      forecast_horizon_minutes, suppression_window_minutes, priority, created_by)
-- VALUES
--     ('Triangle Waves.Int1', 'Triangle wave test tag', 'counts',
--      90, 10, 'auto', 30, 60, 3, 'admin')
-- ON CONFLICT (tag_id) DO NOTHING;
