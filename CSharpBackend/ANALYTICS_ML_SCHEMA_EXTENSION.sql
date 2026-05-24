/* ====================================================================
   ANALYTICS & ML EXTENSIONS for Cereveate Historian
   Required for: MTBF, MTTR, OEE, Utilization, Predictive Maintenance
   PostgreSQL 14+ / TimescaleDB 2.10+
==================================================================== */

-- ================= NEW SCHEMAS =================
CREATE SCHEMA IF NOT EXISTS historian_analytics;  -- Analytics & KPI calculations
CREATE SCHEMA IF NOT EXISTS historian_ml;         -- ML features, models, predictions

-- ================= EQUIPMENT STATE TRACKING =================
SET search_path = historian_raw, public;

-- Equipment state changes (Running → Stopped → Maintenance)
CREATE TABLE IF NOT EXISTS equipment_state_history (
    state_id BIGSERIAL PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL,
    plant TEXT NOT NULL,
    area TEXT NOT NULL,
    equipment TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('RUNNING', 'STOPPED', 'IDLE', 'ALARM', 'MAINTENANCE', 'UNKNOWN')),
    previous_state TEXT,
    duration_seconds INTEGER,  -- Duration in previous state
    reason_code TEXT,          -- Why state changed (e.g., 'PLANNED_MAINTENANCE', 'BREAKDOWN', 'NO_ORDER')
    operator_notes TEXT,
    metadata JSONB,
    FOREIGN KEY (plant, area, equipment) 
        REFERENCES historian_meta.equipment_hierarchy(plant, area, equipment)
);

-- Convert to hypertable (1 day chunks)
SELECT create_hypertable(
    'historian_raw.equipment_state_history',
    'time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '1 day'
);

-- Index for state queries
CREATE INDEX idx_eq_state_equipment_time ON equipment_state_history (plant, area, equipment, time DESC);
CREATE INDEX idx_eq_state_state ON equipment_state_history (state, time DESC);

COMMENT ON TABLE equipment_state_history IS 
'Tracks equipment operational states for MTBF/MTTR/OEE calculations. 
Each row represents a state transition event.';

-- ================= DOWNTIME TRACKING =================

-- Downtime events with reason codes
CREATE TABLE IF NOT EXISTS downtime_events (
    event_id BIGSERIAL PRIMARY KEY,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,           -- NULL if still ongoing
    plant TEXT NOT NULL,
    area TEXT NOT NULL,
    equipment TEXT NOT NULL,
    downtime_type TEXT NOT NULL CHECK (downtime_type IN ('PLANNED', 'UNPLANNED')),
    reason_category TEXT NOT NULL,  -- 'MECHANICAL', 'ELECTRICAL', 'PROCESS', 'MATERIAL', 'EXTERNAL'
    reason_code TEXT NOT NULL,      -- Specific reason (e.g., 'BEARING_FAILURE', 'POWER_OUTAGE')
    severity INTEGER CHECK (severity BETWEEN 1 AND 5),  -- 1=minor, 5=critical
    duration_minutes INTEGER GENERATED ALWAYS AS 
        (EXTRACT(EPOCH FROM (COALESCE(end_time, NOW()) - start_time)) / 60) STORED,
    production_loss_units DOUBLE PRECISION,  -- Lost production quantity
    estimated_cost DOUBLE PRECISION,
    root_cause TEXT,
    corrective_action TEXT,
    acknowledged_by TEXT,
    acknowledged_at TIMESTAMPTZ,
    closed_by TEXT,
    closed_at TIMESTAMPTZ,
    metadata JSONB,
    FOREIGN KEY (plant, area, equipment) 
        REFERENCES historian_meta.equipment_hierarchy(plant, area, equipment)
);

-- Hypertable for downtime events
SELECT create_hypertable(
    'historian_raw.downtime_events',
    'start_time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '7 days'
);

-- Indexes
CREATE INDEX idx_downtime_equipment_time ON downtime_events (plant, area, equipment, start_time DESC);
CREATE INDEX idx_downtime_open ON downtime_events (end_time) WHERE end_time IS NULL;  -- Active downtimes
CREATE INDEX idx_downtime_category ON downtime_events (reason_category, start_time DESC);

COMMENT ON TABLE downtime_events IS 
'Downtime event tracking for MTTR calculation and root cause analysis.
Supports both planned (maintenance) and unplanned (breakdown) events.';

-- ================= PRODUCTION TRACKING =================

-- Shift definitions
CREATE TABLE IF NOT EXISTS historian_meta.shift_definitions (
    shift_id TEXT PRIMARY KEY,
    shift_name TEXT NOT NULL,
    start_time TIME NOT NULL,      -- e.g., '06:00:00' for morning shift
    end_time TIME NOT NULL,         -- e.g., '14:00:00'
    shift_duration_hours DECIMAL(4,2),
    active BOOLEAN DEFAULT TRUE
);

INSERT INTO historian_meta.shift_definitions (shift_id, shift_name, start_time, end_time, shift_duration_hours)
VALUES 
    ('SHIFT_A', 'Morning Shift', '06:00:00', '14:00:00', 8.0),
    ('SHIFT_B', 'Afternoon Shift', '14:00:00', '22:00:00', 8.0),
    ('SHIFT_C', 'Night Shift', '22:00:00', '06:00:00', 8.0)
ON CONFLICT (shift_id) DO NOTHING;

-- Production batches/orders
CREATE TABLE IF NOT EXISTS historian_raw.production_batches (
    batch_id TEXT PRIMARY KEY,
    plant TEXT NOT NULL,
    area TEXT NOT NULL,
    equipment TEXT NOT NULL,
    product_code TEXT NOT NULL,
    product_name TEXT,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    shift_id TEXT REFERENCES historian_meta.shift_definitions(shift_id),
    planned_quantity DOUBLE PRECISION NOT NULL,
    actual_quantity DOUBLE PRECISION,
    rejected_quantity DOUBLE PRECISION DEFAULT 0,
    unit_of_measure TEXT,  -- 'KG', 'L', 'PIECES', 'MW'
    batch_status TEXT CHECK (batch_status IN ('PLANNED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')),
    quality_grade TEXT,    -- 'A', 'B', 'REJECT'
    operator_id TEXT,
    metadata JSONB,
    FOREIGN KEY (plant, area, equipment) 
        REFERENCES historian_meta.equipment_hierarchy(plant, area, equipment)
);

-- Hypertable
SELECT create_hypertable(
    'historian_raw.production_batches',
    'start_time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '30 days'
);

-- Indexes
CREATE INDEX idx_batch_equipment_time ON production_batches (plant, area, equipment, start_time DESC);
CREATE INDEX idx_batch_status ON production_batches (batch_status, start_time DESC);
CREATE INDEX idx_batch_product ON production_batches (product_code, start_time DESC);

-- ================= ANALYTICS LAYER =================
SET search_path = historian_analytics, public;

-- OEE (Overall Equipment Effectiveness) calculations
CREATE TABLE IF NOT EXISTS oee_metrics (
    metric_id BIGSERIAL PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL,
    plant TEXT NOT NULL,
    area TEXT NOT NULL,
    equipment TEXT NOT NULL,
    shift_id TEXT,
    batch_id TEXT,
    
    -- Time-based
    planned_production_time_minutes INTEGER NOT NULL,
    actual_run_time_minutes INTEGER NOT NULL,
    downtime_minutes INTEGER NOT NULL,
    
    -- Performance
    ideal_cycle_time_seconds DOUBLE PRECISION,
    total_pieces_produced INTEGER,
    target_production_rate DOUBLE PRECISION,
    actual_production_rate DOUBLE PRECISION,
    
    -- Quality
    good_pieces INTEGER NOT NULL,
    rejected_pieces INTEGER NOT NULL,
    
    -- OEE Components (0-100%)
    availability_percent DOUBLE PRECISION GENERATED ALWAYS AS 
        (CASE WHEN planned_production_time_minutes > 0 
         THEN (actual_run_time_minutes::DECIMAL / planned_production_time_minutes) * 100 
         ELSE 0 END) STORED,
    
    performance_percent DOUBLE PRECISION,
    quality_percent DOUBLE PRECISION GENERATED ALWAYS AS 
        (CASE WHEN (good_pieces + rejected_pieces) > 0 
         THEN (good_pieces::DECIMAL / (good_pieces + rejected_pieces)) * 100 
         ELSE 0 END) STORED,
    
    oee_percent DOUBLE PRECISION GENERATED ALWAYS AS 
        ((CASE WHEN planned_production_time_minutes > 0 
          THEN (actual_run_time_minutes::DECIMAL / planned_production_time_minutes) * 100 
          ELSE 0 END) * 
         COALESCE(performance_percent, 0) * 
         (CASE WHEN (good_pieces + rejected_pieces) > 0 
          THEN (good_pieces::DECIMAL / (good_pieces + rejected_pieces)) * 100 
          ELSE 0 END) / 10000) STORED,
    
    metadata JSONB
);

-- Hypertable
SELECT create_hypertable(
    'historian_analytics.oee_metrics',
    'time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '7 days'
);

-- Indexes
CREATE INDEX idx_oee_equipment_time ON oee_metrics (plant, area, equipment, time DESC);
CREATE INDEX idx_oee_shift ON oee_metrics (shift_id, time DESC);

COMMENT ON TABLE oee_metrics IS 
'OEE (Overall Equipment Effectiveness) = Availability × Performance × Quality.
Calculated per shift or per batch. Target OEE: 85%+';

-- MTBF/MTTR summary metrics
CREATE TABLE IF NOT EXISTS reliability_metrics (
    metric_id BIGSERIAL PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL,
    plant TEXT NOT NULL,
    area TEXT NOT NULL,
    equipment TEXT NOT NULL,
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    
    -- Failure tracking
    total_failures INTEGER NOT NULL,
    planned_downtime_minutes INTEGER NOT NULL,
    unplanned_downtime_minutes INTEGER NOT NULL,
    
    -- MTBF (Mean Time Between Failures) - hours
    mtbf_hours DOUBLE PRECISION GENERATED ALWAYS AS 
        (CASE WHEN total_failures > 0 
         THEN (EXTRACT(EPOCH FROM (period_end - period_start)) / 3600.0) / total_failures 
         ELSE NULL END) STORED,
    
    -- MTTR (Mean Time To Repair) - hours
    mttr_hours DOUBLE PRECISION,
    
    -- Availability
    total_available_time_hours DOUBLE PRECISION,
    actual_uptime_hours DOUBLE PRECISION,
    availability_percent DOUBLE PRECISION GENERATED ALWAYS AS 
        (CASE WHEN total_available_time_hours > 0 
         THEN (actual_uptime_hours / total_available_time_hours) * 100 
         ELSE 0 END) STORED,
    
    metadata JSONB
);

-- Hypertable
SELECT create_hypertable(
    'historian_analytics.reliability_metrics',
    'time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '30 days'
);

-- Indexes
CREATE INDEX idx_reliability_equipment_time ON reliability_metrics (plant, area, equipment, time DESC);

COMMENT ON TABLE reliability_metrics IS 
'MTBF = Total Operating Time / Number of Failures
MTTR = Total Repair Time / Number of Repairs
Calculated daily/weekly/monthly for reliability analysis.';

-- Utilization metrics
CREATE TABLE IF NOT EXISTS utilization_metrics (
    metric_id BIGSERIAL PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL,
    plant TEXT NOT NULL,
    area TEXT NOT NULL,
    equipment TEXT NOT NULL,
    shift_id TEXT,
    
    -- Time breakdown (minutes)
    total_time_minutes INTEGER NOT NULL,
    running_time_minutes INTEGER NOT NULL,
    idle_time_minutes INTEGER NOT NULL,
    maintenance_time_minutes INTEGER NOT NULL,
    alarm_time_minutes INTEGER NOT NULL,
    
    -- Utilization (0-100%)
    utilization_percent DOUBLE PRECISION GENERATED ALWAYS AS 
        (CASE WHEN total_time_minutes > 0 
         THEN (running_time_minutes::DECIMAL / total_time_minutes) * 100 
         ELSE 0 END) STORED,
    
    -- Load factor (actual output / rated capacity)
    rated_capacity DOUBLE PRECISION,
    actual_output DOUBLE PRECISION,
    load_factor_percent DOUBLE PRECISION GENERATED ALWAYS AS 
        (CASE WHEN rated_capacity > 0 
         THEN (actual_output / rated_capacity) * 100 
         ELSE 0 END) STORED,
    
    metadata JSONB
);

-- Hypertable
SELECT create_hypertable(
    'historian_analytics.utilization_metrics',
    'time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '7 days'
);

-- Indexes
CREATE INDEX idx_utilization_equipment_time ON utilization_metrics (plant, area, equipment, time DESC);
CREATE INDEX idx_utilization_shift ON utilization_metrics (shift_id, time DESC);

-- ================= ML FEATURE STORE =================
SET search_path = historian_ml, public;

-- ML features (preprocessed data for models)
CREATE TABLE IF NOT EXISTS feature_store (
    feature_id BIGSERIAL PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL,
    entity_type TEXT NOT NULL,      -- 'equipment', 'tag', 'batch'
    entity_id TEXT NOT NULL,        -- Equipment ID or Tag ID
    feature_set_name TEXT NOT NULL, -- 'vibration_features', 'thermal_features'
    feature_name TEXT NOT NULL,     -- 'rms_value', 'peak_frequency', 'temperature_trend'
    feature_value DOUBLE PRECISION,
    feature_version INTEGER DEFAULT 1,
    metadata JSONB
);

-- Hypertable
SELECT create_hypertable(
    'historian_ml.feature_store',
    'time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '7 days'
);

-- Indexes
CREATE INDEX idx_features_entity_time ON feature_store (entity_type, entity_id, time DESC);
CREATE INDEX idx_features_featureset ON feature_store (feature_set_name, feature_name, time DESC);

COMMENT ON TABLE feature_store IS 
'Preprocessed ML features from raw time-series data.
Supports online serving and batch training.';

-- ML model registry
CREATE TABLE IF NOT EXISTS ml_models (
    model_id TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    model_type TEXT NOT NULL,       -- 'CLASSIFICATION', 'REGRESSION', 'ANOMALY_DETECTION', 'FORECASTING'
    model_framework TEXT,           -- 'scikit-learn', 'tensorflow', 'pytorch'
    feature_set_name TEXT NOT NULL,
    target_variable TEXT,
    training_start_date TIMESTAMPTZ,
    training_end_date TIMESTAMPTZ,
    model_version INTEGER NOT NULL,
    model_file_path TEXT,           -- File path or S3 URI
    model_metrics JSONB,            -- accuracy, precision, recall, F1, RMSE, etc.
    hyperparameters JSONB,
    deployed_at TIMESTAMPTZ,
    deployed_by TEXT,
    status TEXT CHECK (status IN ('TRAINING', 'VALIDATED', 'DEPLOYED', 'RETIRED')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB
);

CREATE INDEX idx_models_status ON ml_models (status, model_version DESC);
CREATE INDEX idx_models_feature_set ON ml_models (feature_set_name);

COMMENT ON TABLE ml_models IS 
'ML model registry tracking trained models, versions, and deployment status.';

-- ML predictions
CREATE TABLE IF NOT EXISTS ml_predictions (
    prediction_id BIGSERIAL PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL,
    model_id TEXT NOT NULL REFERENCES ml_models(model_id),
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    prediction_type TEXT NOT NULL,  -- 'FAILURE_PROBABILITY', 'REMAINING_LIFE', 'ANOMALY_SCORE'
    predicted_value DOUBLE PRECISION,
    confidence_score DOUBLE PRECISION,  -- 0-1
    actual_value DOUBLE PRECISION,      -- For model evaluation
    prediction_horizon_hours INTEGER,   -- How far ahead is this prediction
    metadata JSONB
);

-- Hypertable
SELECT create_hypertable(
    'historian_ml.ml_predictions',
    'time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '7 days'
);

-- Indexes
CREATE INDEX idx_predictions_model_time ON ml_predictions (model_id, time DESC);
CREATE INDEX idx_predictions_entity ON ml_predictions (entity_type, entity_id, time DESC);
CREATE INDEX idx_predictions_type ON ml_predictions (prediction_type, time DESC);

COMMENT ON TABLE ml_predictions IS 
'Model predictions for predictive maintenance, anomaly detection, forecasting.
Stores both predictions and actual outcomes for model evaluation.';

-- ML anomalies detected
CREATE TABLE IF NOT EXISTS ml_anomalies (
    anomaly_id BIGSERIAL PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL,
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    model_id TEXT REFERENCES ml_models(model_id),
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,        -- Equipment or Tag
    anomaly_type TEXT NOT NULL,     -- 'OUTLIER', 'DRIFT', 'PATTERN_BREAK'
    anomaly_score DOUBLE PRECISION NOT NULL,  -- Higher = more anomalous
    severity TEXT CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    features_snapshot JSONB,        -- Feature values at detection time
    root_cause_analysis JSONB,      -- Top contributing features
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_by TEXT,
    acknowledged_at TIMESTAMPTZ,
    resolution_notes TEXT,
    metadata JSONB
);

-- Hypertable
SELECT create_hypertable(
    'historian_ml.ml_anomalies',
    'time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '7 days'
);

-- Indexes
CREATE INDEX idx_anomalies_entity_time ON ml_anomalies (entity_type, entity_id, time DESC);
CREATE INDEX idx_anomalies_severity ON ml_anomalies (severity, acknowledged) WHERE NOT acknowledged;
CREATE INDEX idx_anomalies_model ON ml_anomalies (model_id, time DESC);

COMMENT ON TABLE ml_anomalies IS 
'Anomalies detected by ML models for early warning and root cause analysis.';

-- ================= HELPER FUNCTIONS FOR ANALYTICS =================

-- Calculate MTTR for equipment
CREATE OR REPLACE FUNCTION calculate_mttr(
    p_plant TEXT,
    p_area TEXT,
    p_equipment TEXT,
    p_start_date TIMESTAMPTZ,
    p_end_date TIMESTAMPTZ
) RETURNS TABLE(
    equipment_full_name TEXT,
    total_failures INTEGER,
    total_repair_minutes INTEGER,
    mttr_hours DOUBLE PRECISION
) LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT 
        p_plant || '.' || p_area || '.' || p_equipment AS equipment_full_name,
        COUNT(*)::INTEGER AS total_failures,
        SUM(duration_minutes)::INTEGER AS total_repair_minutes,
        (SUM(duration_minutes) / 60.0 / NULLIF(COUNT(*), 0))::DOUBLE PRECISION AS mttr_hours
    FROM historian_raw.downtime_events
    WHERE plant = p_plant
      AND area = p_area
      AND equipment = p_equipment
      AND start_time >= p_start_date
      AND start_time <= p_end_date
      AND downtime_type = 'UNPLANNED'
      AND end_time IS NOT NULL;
END;
$$;

-- Calculate equipment utilization
CREATE OR REPLACE FUNCTION calculate_utilization(
    p_plant TEXT,
    p_area TEXT,
    p_equipment TEXT,
    p_start_date TIMESTAMPTZ,
    p_end_date TIMESTAMPTZ
) RETURNS TABLE(
    equipment_full_name TEXT,
    total_minutes INTEGER,
    running_minutes INTEGER,
    utilization_percent DOUBLE PRECISION
) LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT 
        p_plant || '.' || p_area || '.' || p_equipment AS equipment_full_name,
        EXTRACT(EPOCH FROM (p_end_date - p_start_date))::INTEGER / 60 AS total_minutes,
        SUM(CASE WHEN state = 'RUNNING' THEN duration_seconds ELSE 0 END)::INTEGER / 60 AS running_minutes,
        (SUM(CASE WHEN state = 'RUNNING' THEN duration_seconds ELSE 0 END) / 
         NULLIF(EXTRACT(EPOCH FROM (p_end_date - p_start_date)), 0) * 100)::DOUBLE PRECISION AS utilization_percent
    FROM historian_raw.equipment_state_history
    WHERE plant = p_plant
      AND area = p_area
      AND equipment = p_equipment
      AND time >= p_start_date
      AND time <= p_end_date;
END;
$$;

-- ================= MATERIALIZED VIEWS FOR DASHBOARDS =================

-- Daily OEE summary (fast dashboard queries)
CREATE MATERIALIZED VIEW IF NOT EXISTS historian_analytics.daily_oee_summary AS
SELECT 
    date_trunc('day', time) AS date,
    plant,
    area,
    equipment,
    AVG(availability_percent) AS avg_availability,
    AVG(performance_percent) AS avg_performance,
    AVG(quality_percent) AS avg_quality,
    AVG(oee_percent) AS avg_oee,
    COUNT(*) AS shifts_count
FROM historian_analytics.oee_metrics
WHERE time >= NOW() - INTERVAL '90 days'
GROUP BY 1, 2, 3, 4;

CREATE INDEX idx_daily_oee_summary_date ON historian_analytics.daily_oee_summary (date DESC, plant, area, equipment);

-- Refresh policy (once per hour)
-- CREATE POLICY: REFRESH MATERIALIZED VIEW historian_analytics.daily_oee_summary;

-- ================= VALIDATION =================
DO $$
BEGIN
    RAISE NOTICE '✅ Analytics & ML schema extension completed successfully';
    RAISE NOTICE '📊 Added tables: equipment_state_history, downtime_events, production_batches';
    RAISE NOTICE '📊 Added tables: oee_metrics, reliability_metrics, utilization_metrics';
    RAISE NOTICE '🤖 Added tables: feature_store, ml_models, ml_predictions, ml_anomalies';
    RAISE NOTICE '📈 Analytics functions: calculate_mttr(), calculate_utilization()';
    RAISE NOTICE '⚠️ Next steps: Implement state detection service, connect ML pipeline';
END $$;

/* ====================================================================
   END OF ANALYTICS & ML EXTENSIONS
==================================================================== */
