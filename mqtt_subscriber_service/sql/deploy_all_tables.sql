-- ============================================================================
-- MQTT Subscriber Service - Complete Database Deployment Script
-- PostgreSQL 14+ with TimescaleDB
-- Run this script to create all required tables and indexes
-- ============================================================================

\echo '======================================================================'
\echo 'MQTT Subscriber Service - Database Deployment'
\echo '======================================================================'

-- Set search path
SET search_path = historian_raw, historian_meta, public;

\echo 'Creating schemas if not exist...'

-- Create schemas if they don't exist
CREATE SCHEMA IF NOT EXISTS historian_meta;
CREATE SCHEMA IF NOT EXISTS historian_raw;
CREATE SCHEMA IF NOT EXISTS historian_admin;

\echo 'Schemas created successfully.'

-- ============================================================================
-- PART 1: Core Historian Tables (if not exist)
-- ============================================================================

\echo 'Creating core historian tables...'

-- Tag Master table
CREATE TABLE IF NOT EXISTS historian_meta.tag_master (
    tag_id TEXT PRIMARY KEY,
    tag_name TEXT NOT NULL,
    description TEXT,
    plant TEXT,
    area TEXT,
    equipment TEXT,
    data_type TEXT NOT NULL DEFAULT 'Double',
    eng_unit TEXT,
    db_logging_interval_ms INTEGER NOT NULL DEFAULT 1000,
    enabled BOOLEAN NOT NULL DEFAULT true,
    db_table_name TEXT NOT NULL DEFAULT 'historian_raw.historian_timeseries',
    mapping_version BIGINT NOT NULL DEFAULT 1,
    config_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_tag_master_enabled ON historian_meta.tag_master(enabled);
CREATE INDEX IF NOT EXISTS idx_tag_master_plant ON historian_meta.tag_master(plant, area);

-- Historian Timeseries table
CREATE TABLE IF NOT EXISTS historian_raw.historian_timeseries (
    id BIGSERIAL PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL,
    tag_id TEXT NOT NULL,
    value_num DOUBLE PRECISION,
    value_bool BOOLEAN,
    value_text TEXT,
    quality TEXT NOT NULL,
    sample_source TEXT NOT NULL DEFAULT 'MQTT',
    mapping_version INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_historian_timeseries_tag_time 
    ON historian_raw.historian_timeseries(tag_id, time DESC);

CREATE INDEX IF NOT EXISTS idx_historian_timeseries_time 
    ON historian_raw.historian_timeseries(time DESC);

-- Historian Events table (for alarms)
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
CREATE INDEX IF NOT EXISTS idx_historian_events_active ON historian_raw.historian_events(acknowledged, cleared) 
    WHERE NOT acknowledged OR NOT cleared;

COMMENT ON TABLE historian_raw.historian_events IS 'Alarm and event data from MQTT messages';
COMMENT ON COLUMN historian_raw.historian_events.severity IS 'Event severity: 1=Critical, 2=Warning, 3=Info, 4=Debug, 5=Trace';
COMMENT ON COLUMN historian_raw.historian_events.metadata IS 'Additional event metadata (alarm_value, setpoint, plant, area, equipment, etc.)';

\echo 'Core historian tables created successfully.'

-- ============================================================================
-- PART 2: MQTT Subscriber Tables
-- ============================================================================

\echo 'Creating MQTT subscriber tables...'

-- MQTT Topic Configuration
CREATE TABLE IF NOT EXISTS historian_raw.mqtt_topic_config (
    topic_id SERIAL,
    topic_name TEXT NOT NULL,
    plc_name TEXT NOT NULL,
    qos INTEGER NOT NULL DEFAULT 1 CHECK (qos IN (0, 1, 2)),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    thread_group INTEGER NOT NULL DEFAULT 1,
    processing_rules JSONB,
    created_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT mqtt_topic_config_pkey PRIMARY KEY (topic_id, topic_name, plc_name)
);

CREATE INDEX IF NOT EXISTS idx_mqtt_topic_active ON historian_raw.mqtt_topic_config(is_active);
CREATE INDEX IF NOT EXISTS idx_mqtt_topic_name ON historian_raw.mqtt_topic_config(topic_name);
CREATE INDEX IF NOT EXISTS idx_mqtt_topic_plc_name ON historian_raw.mqtt_topic_config(plc_name);

COMMENT ON TABLE historian_raw.mqtt_topic_config IS 'MQTT topic subscription configuration';
COMMENT ON COLUMN historian_raw.mqtt_topic_config.plc_name IS 'PLC identifier - each PLC is assigned a unique topic name';
COMMENT ON COLUMN historian_raw.mqtt_topic_config.qos IS 'Quality of Service: 0=At most once, 1=At least once, 2=Exactly once';

-- MQTT Audit Main
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
    processing_duration_ms INTEGER
);

CREATE INDEX IF NOT EXISTS idx_audit_main_msg_id ON historian_raw.mqtt_audit_main(message_id);
CREATE INDEX IF NOT EXISTS idx_audit_main_status ON historian_raw.mqtt_audit_main(status);
CREATE INDEX IF NOT EXISTS idx_audit_main_time ON historian_raw.mqtt_audit_main(first_received_time DESC);
CREATE INDEX IF NOT EXISTS idx_audit_main_topic ON historian_raw.mqtt_audit_main(topic_name);

COMMENT ON TABLE historian_raw.mqtt_audit_main IS 'Main audit record for each MQTT message';
COMMENT ON COLUMN historian_raw.mqtt_audit_main.message_id IS 'Unique message identifier';
COMMENT ON COLUMN historian_raw.mqtt_audit_main.status IS 'Processing status: processing, completed, failed';

-- MQTT Audit History
CREATE TABLE IF NOT EXISTS historian_raw.mqtt_audit_history (
    hist_id BIGSERIAL PRIMARY KEY,
    audit_id BIGINT NOT NULL REFERENCES historian_raw.mqtt_audit_main(audit_id),
    step TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('success', 'failed')),
    step_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    details TEXT,
    duration_ms INTEGER
);

CREATE INDEX IF NOT EXISTS idx_audit_hist_audit_id ON historian_raw.mqtt_audit_history(audit_id);
CREATE INDEX IF NOT EXISTS idx_audit_hist_step ON historian_raw.mqtt_audit_history(step);
CREATE INDEX IF NOT EXISTS idx_audit_hist_status ON historian_raw.mqtt_audit_history(status);
CREATE INDEX IF NOT EXISTS idx_audit_hist_time ON historian_raw.mqtt_audit_history(step_time DESC);

COMMENT ON TABLE historian_raw.mqtt_audit_history IS 'Detailed audit trail for each processing step';
COMMENT ON COLUMN historian_raw.mqtt_audit_history.step IS 'Processing step identifier (parse, validate, insert)';

\echo 'MQTT subscriber tables created successfully.'

-- ============================================================================
-- PART 3: Insert Sample Data
-- ============================================================================

\echo 'Inserting sample MQTT topic configurations...'

INSERT INTO historian_raw.mqtt_topic_config (topic_name, plc_name, qos, is_active, thread_group) VALUES
('plant/gateway/data', 'PLC_GATEWAY_01', 1, TRUE, 1),
('plant/sensors/#', 'PLC_SENSORS_01', 1, TRUE, 1),
('production/plant_a/gateway_001', 'PLC_PLANT_A_001', 1, TRUE, 1),
('production/plant_b/gateway_002', 'PLC_PLANT_B_002', 1, TRUE, 2),
('development/test/#', 'PLC_DEV_TEST', 0, TRUE, 1)
ON CONFLICT (topic_name) DO NOTHING;

\echo 'Sample data inserted successfully.'

-- ============================================================================
-- PART 4: Enable TimescaleDB (Optional)
-- ============================================================================

\echo 'Checking for TimescaleDB extension...'

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        RAISE NOTICE 'TimescaleDB detected. Converting tables to hypertables...';
        
        -- Convert historian_timeseries to hypertable
        PERFORM create_hypertable(
            'historian_raw.historian_timeseries', 
            'time',
            if_not_exists => TRUE,
            chunk_time_interval => INTERVAL '1 day'
        );
        
        -- Convert historian_events to hypertable
        PERFORM create_hypertable(
            'historian_raw.historian_events', 
            'time',
            if_not_exists => TRUE,
            chunk_time_interval => INTERVAL '7 days'
        );
        
        RAISE NOTICE 'Hypertables created successfully.';
    ELSE
        RAISE NOTICE 'TimescaleDB not installed. Skipping hypertable creation.';
        RAISE NOTICE 'To enable TimescaleDB, run: CREATE EXTENSION timescaledb;';
    END IF;
END$$;

-- ============================================================================
-- PART 5: Grant Permissions
-- ============================================================================

\echo 'Granting permissions...'

-- Create user if needed (uncomment and set password)
-- CREATE USER mqtt_subscriber_user WITH PASSWORD 'your_secure_password_here';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mqtt_subscriber_user') THEN
        -- Grant schema usage
        GRANT USAGE ON SCHEMA historian_raw TO mqtt_subscriber_user;
        GRANT USAGE ON SCHEMA historian_meta TO mqtt_subscriber_user;
        
        -- Grant SELECT on topic config and tag_master (READ-ONLY)
        GRANT SELECT ON historian_raw.mqtt_topic_config TO mqtt_subscriber_user;
        GRANT SELECT ON historian_meta.tag_master TO mqtt_subscriber_user;
        
        -- Grant INSERT/UPDATE on audit tables
        GRANT INSERT, UPDATE ON historian_raw.mqtt_audit_main TO mqtt_subscriber_user;
        GRANT INSERT ON historian_raw.mqtt_audit_history TO mqtt_subscriber_user;
        
        -- Grant INSERT on historian tables
        GRANT INSERT ON historian_raw.historian_timeseries TO mqtt_subscriber_user;
        GRANT INSERT, UPDATE ON historian_raw.historian_events TO mqtt_subscriber_user;
        
        -- Grant sequence usage
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA historian_raw TO mqtt_subscriber_user;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA historian_meta TO mqtt_subscriber_user;
        
        RAISE NOTICE 'Permissions granted to mqtt_subscriber_user successfully.';
    ELSE
        RAISE NOTICE 'User mqtt_subscriber_user does not exist. Please create user and run grant statements manually.';
    END IF;
END$$;

-- ============================================================================
-- PART 6: Verification
-- ============================================================================

\echo '======================================================================'
\echo 'Verification Results'
\echo '======================================================================'

\echo 'Tables in historian_raw schema:'
SELECT 
    table_name, 
    (SELECT COUNT(*) FROM information_schema.columns 
     WHERE table_schema='historian_raw' AND table_name=t.table_name) as column_count
FROM information_schema.tables t
WHERE table_schema = 'historian_raw' 
ORDER BY table_name;

\echo ''
\echo 'MQTT topic configurations:'
SELECT topic_id, topic_name, plc_name, qos, is_active, thread_group 
FROM historian_raw.mqtt_topic_config
ORDER BY topic_id;

\echo ''
\echo '======================================================================'
\echo 'Deployment Complete!'
\echo '======================================================================'
\echo ''
\echo 'Next Steps:'
\echo '1. Review the sample MQTT topic configurations'
\echo '2. Update database connection in config/config.yaml'
\echo '3. Create mqtt_subscriber_user if not exists'
\echo '4. Test connectivity with tests/test_basic.py'
\echo '======================================================================'
