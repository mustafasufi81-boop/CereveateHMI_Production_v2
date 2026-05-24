drop table historian_raw.mqtt_topic_config;
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

INSERT INTO historian_raw.mqtt_topic_config (topic_name, plc_name, qos, is_active, thread_group) VALUES
('plant/gateway/data', 'PLC_GATEWAY_01', 1, TRUE, 1),
('plant/sensors/data', 'PLC_SENSORS_01', 1, TRUE, 1),
('production/plant_a/gateway_001', 'PLC_PLANT_A_001', 1, TRUE, 1),
('production/plant_b/gateway_002', 'PLC_PLANT_B_002', 1, TRUE, 2),
('development/test/data', 'PLC_DEV_TEST', 0, TRUE, 1)
commit;