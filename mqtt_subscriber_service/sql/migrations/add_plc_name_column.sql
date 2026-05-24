-- ============================================================================
-- Migration Script: Add plc_name column to mqtt_topic_config
-- Date: 2026-01-15
-- Description: Adds plc_name column to track which PLC each topic belongs to
-- ============================================================================
drop table historian_raw.mqtt_topic_config
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

-- Drop the existing primary key constraint
ALTER TABLE historian_raw.mqtt_topic_config 
DROP CONSTRAINT mqtt_topic_config_pkey;

-- Drop the existing UNIQUE constraint on topic_name
ALTER TABLE historian_raw.mqtt_topic_config 
DROP CONSTRAINT mqtt_topic_config_topic_name_key;

-- Add the new composite primary key
ALTER TABLE historian_raw.mqtt_topic_config 
ADD CONSTRAINT mqtt_topic_config_pkey 
PRIMARY KEY (topic_id, topic_name, plc_name);

INSERT INTO historian_raw.mqtt_topic_config (topic_name, plc_name, qos, is_active, thread_group) VALUES
('test/gateway/data', 'PLC_TEST_GATEWAY', 1, TRUE, 1),
('production/plant_a/gateway_001', 'PLC_PLANT_A_001', 1, TRUE, 1),
('production/plant_b/gateway_002', 'PLC_PLANT_B_002', 1, TRUE, 2),
('development/test/data', 'PLC_DEV_TEST', 0, TRUE, 1);
commit;

