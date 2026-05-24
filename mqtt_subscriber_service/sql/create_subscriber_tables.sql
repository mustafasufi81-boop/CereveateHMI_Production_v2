-- ============================================================================
-- MQTT Subscriber Service - Database Schema
-- PostgreSQL 14+ with TimescaleDB
-- Schema: historian_raw
-- ============================================================================

-- Set search path
SET search_path = historian_raw, public;

-- ============================================================================
-- Table 1: mqtt_topic_config
-- Purpose: Store MQTT topic subscription configuration
-- ============================================================================

CREATE TABLE IF NOT EXISTS historian_raw.mqtt_topic_config (
    topic_id SERIAL PRIMARY KEY,
    topic_name TEXT NOT NULL UNIQUE,
    plc_name TEXT NOT NULL,
    qos INTEGER NOT NULL DEFAULT 1 CHECK (qos IN (0, 1, 2)),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    thread_group INTEGER NOT NULL DEFAULT 1,
    processing_rules JSONB,
    created_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_time TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mqtt_topic_active ON historian_raw.mqtt_topic_config(is_active);
CREATE INDEX IF NOT EXISTS idx_mqtt_topic_name ON historian_raw.mqtt_topic_config(topic_name);
CREATE INDEX IF NOT EXISTS idx_mqtt_topic_plc_name ON historian_raw.mqtt_topic_config(plc_name);

COMMENT ON TABLE historian_raw.mqtt_topic_config IS 'MQTT topic subscription configuration';
COMMENT ON COLUMN historian_raw.mqtt_topic_config.plc_name IS 'PLC identifier - each PLC is assigned a unique topic name';
COMMENT ON COLUMN historian_raw.mqtt_topic_config.qos IS 'Quality of Service: 0=At most once, 1=At least once, 2=Exactly once';
COMMENT ON COLUMN historian_raw.mqtt_topic_config.processing_rules IS 'Optional JSON rules for message processing';

-- ============================================================================
-- Table 2: mqtt_audit_main
-- Purpose: Main audit record per MQTT message (one record per message)
-- ============================================================================

CREATE TABLE IF NOT EXISTS historian_raw.mqtt_audit_main (
    audit_id BIGSERIAL PRIMARY KEY,
    topic_name TEXT NOT NULL,
    message_id TEXT NOT NULL UNIQUE,
    payload_size INTEGER,
    first_received_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_time TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'processing' CHECK (
        status IN ('processing', 'failed', 'completed')
    ),
    error_message TEXT,
    records_inserted INTEGER DEFAULT 0,
    processing_duration_ms INTEGER,
    retry_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_audit_main_msg_id ON historian_raw.mqtt_audit_main(message_id);
CREATE INDEX IF NOT EXISTS idx_audit_main_status ON historian_raw.mqtt_audit_main(status);
CREATE INDEX IF NOT EXISTS idx_audit_main_time ON historian_raw.mqtt_audit_main(first_received_time DESC);
CREATE INDEX IF NOT EXISTS idx_audit_main_topic ON historian_raw.mqtt_audit_main(topic_name);

COMMENT ON TABLE historian_raw.mqtt_audit_main IS 'Main audit record for each MQTT message';
COMMENT ON COLUMN historian_raw.mqtt_audit_main.message_id IS 'Unique message identifier from payload (file_id)';
COMMENT ON COLUMN historian_raw.mqtt_audit_main.status IS 'Final processing status';
COMMENT ON COLUMN historian_raw.mqtt_audit_main.retry_count IS 'Number of retry attempts for this message';

-- ============================================================================
-- Table 3: mqtt_audit_history
-- Purpose: Historical records per message retry (mirrors mqtt_audit_main)
-- ============================================================================

CREATE TABLE IF NOT EXISTS historian_raw.mqtt_audit_history (
    hist_id BIGSERIAL PRIMARY KEY,
    audit_id BIGINT NOT NULL REFERENCES historian_raw.mqtt_audit_main(audit_id),
    topic_name TEXT NOT NULL,
    message_id TEXT NOT NULL,
    payload_size INTEGER,
    first_received_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_time TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'processing' CHECK (
        status IN ('processing', 'failed', 'completed')
    ),
    error_message TEXT,
    records_inserted INTEGER DEFAULT 0,
    processing_duration_ms INTEGER,
    retry_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_audit_hist_audit_id ON historian_raw.mqtt_audit_history(audit_id);
CREATE INDEX IF NOT EXISTS idx_audit_hist_msg_id ON historian_raw.mqtt_audit_history(message_id);
CREATE INDEX IF NOT EXISTS idx_audit_hist_status ON historian_raw.mqtt_audit_history(status);
CREATE INDEX IF NOT EXISTS idx_audit_hist_time ON historian_raw.mqtt_audit_history(first_received_time DESC);
CREATE INDEX IF NOT EXISTS idx_audit_hist_topic ON historian_raw.mqtt_audit_history(topic_name);
CREATE INDEX IF NOT EXISTS idx_audit_hist_retry ON historian_raw.mqtt_audit_history(retry_count);

COMMENT ON TABLE historian_raw.mqtt_audit_history IS 'Historical audit trail for each message retry attempt';
COMMENT ON COLUMN historian_raw.mqtt_audit_history.message_id IS 'Unique message identifier from payload (file_id)';
COMMENT ON COLUMN historian_raw.mqtt_audit_history.status IS 'Processing status for this attempt';
COMMENT ON COLUMN historian_raw.mqtt_audit_history.retry_count IS 'Retry attempt number for this history record';

-- ============================================================================
-- Insert Sample Topic Configurations
-- ============================================================================

INSERT INTO historian_raw.mqtt_topic_config (topic_name, plc_name, qos, is_active, thread_group) VALUES
('test/gateway/data', 'PLC_TEST_GATEWAY', 1, TRUE, 1),
('production/plant_a/gateway_001', 'PLC_PLANT_A_001', 1, TRUE, 1),
('production/plant_b/gateway_002', 'PLC_PLANT_B_002', 1, TRUE, 2),
('development/test/#', 'PLC_DEV_TEST', 0, TRUE, 1)
ON CONFLICT (topic_name) DO NOTHING;

-- ============================================================================
-- Grant Permissions
-- ============================================================================

-- Create user if needed (uncomment if user doesn't exist)
-- CREATE USER opc_app_user WITH PASSWORD 'your_password_here';

-- Grant schema usage
GRANT USAGE ON SCHEMA historian_raw TO opc_app_user;
GRANT USAGE ON SCHEMA historian_meta TO opc_app_user;

-- Grant SELECT on topic config and tag_master (READ-ONLY)
GRANT SELECT ON historian_raw.mqtt_topic_config TO opc_app_user;
GRANT SELECT ON historian_meta.tag_master TO opc_app_user;

-- Grant INSERT on audit tables
GRANT INSERT, UPDATE ON historian_raw.mqtt_audit_main TO opc_app_user;
GRANT INSERT ON historian_raw.mqtt_audit_history TO opc_app_user;

-- ============================================================================
-- Table 4: historian_events
-- Purpose: Store alarm/event data from MQTT messages
-- ============================================================================

CREATE TABLE IF NOT EXISTS historian_raw.historian_events (
    event_id BIGSERIAL PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL,
    tag_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    severity INTEGER NOT NULL CHECK (severity BETWEEN 1 AND 5),
    message TEXT NOT NULL,
    metadata JSONB,
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_by TEXT,
    acknowledged_at TIMESTAMPTZ,
    cleared BOOLEAN DEFAULT FALSE,
    cleared_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_historian_events_tag_time ON historian_raw.historian_events(tag_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_historian_events_time ON historian_raw.historian_events(time DESC);
CREATE INDEX IF NOT EXISTS idx_historian_events_severity ON historian_raw.historian_events(severity);
CREATE INDEX IF NOT EXISTS idx_historian_events_type ON historian_raw.historian_events(event_type);
CREATE INDEX IF NOT EXISTS idx_historian_events_active ON historian_raw.historian_events(acknowledged, cleared) WHERE NOT acknowledged OR NOT cleared;

COMMENT ON TABLE historian_raw.historian_events IS 'Alarm and event data from MQTT messages';
COMMENT ON COLUMN historian_raw.historian_events.severity IS 'Event severity: 1=Critical, 2=Warning, 3=Info, 4=Debug, 5=Trace';
COMMENT ON COLUMN historian_raw.historian_events.metadata IS 'Additional event metadata (alarm_value, setpoint, plant, area, equipment, etc.)';

-- Enable TimescaleDB hypertable for events (optional)
-- SELECT create_hypertable('historian_raw.historian_events', 'time', if_not_exists => TRUE);

-- Grant INSERT on historian tables
GRANT INSERT ON historian_raw.historian_timeseries TO opc_app_user;
GRANT INSERT ON historian_raw.historian_events TO opc_app_user;
GRANT UPDATE ON historian_raw.historian_events TO opc_app_user;

-- Grant sequence usage for SERIAL columns
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA historian_raw TO opc_app_user;

-- ============================================================================
-- Verification Queries
-- ============================================================================

-- Verify tables created
SELECT 
    table_name, 
    (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='historian_raw' AND table_name=t.table_name) as column_count
FROM information_schema.tables t
WHERE table_schema = 'historian_raw' 
AND table_name LIKE 'mqtt_%'
ORDER BY table_name;

-- Verify topic configurations
SELECT * FROM historian_raw.mqtt_topic_config;

-- ============================================================================
-- END OF SCRIPT
-- ============================================================================
