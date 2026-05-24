-- ═══════════════════════════════════════════════════════════════════════════
-- PLC GATEWAY DATABASE SCHEMA
-- 
-- Creates tables for PLC configuration and tag mappings
-- Each PLC gets its own worker, completely isolated
-- ═══════════════════════════════════════════════════════════════════════════

-- Create schema
CREATE SCHEMA IF NOT EXISTS plc_gateway;

-- ═══════════════════════════════════════════════════════════════════════════
-- PLC CONNECTIONS TABLE
-- One row per PLC
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS plc_gateway.plc_connections (
    id SERIAL PRIMARY KEY,
    
    -- Identity
    plc_id VARCHAR(100) NOT NULL UNIQUE,          -- Unique identifier (e.g., "PLC_PlantA_01")
    plc_name VARCHAR(200) NOT NULL,                -- Display name
    plant_id VARCHAR(100) NOT NULL DEFAULT 'default', -- Plant/Area grouping
    
    -- Protocol (must match PlcProtocol enum)
    protocol VARCHAR(50) NOT NULL,                 -- SiemensS7, ModbusTcp, EtherNetIP, Rockwell, ABB, Mitsubishi, Omron
    
    -- Connection
    ip_address VARCHAR(50) NOT NULL,
    port INTEGER NOT NULL DEFAULT 102,
    
    -- Polling
    polling_interval_ms INTEGER NOT NULL DEFAULT 1000,
    timeout_ms INTEGER NOT NULL DEFAULT 3000,
    retry_count INTEGER NOT NULL DEFAULT 3,
    reconnect_delay_ms INTEGER NOT NULL DEFAULT 5000,
    
    -- Protocol-specific config (JSON)
    s7_config JSONB,                               -- {"CpuType": "S71500", "Rack": 0, "Slot": 1}
    modbus_config JSONB,                           -- {"SlaveId": 1}
    ethernet_ip_config JSONB,                      -- {"Path": "1,0", "PlcType": "ControlLogix"}
    rockwell_config JSONB,                         -- {"PlcType": "ControlLogix", "Path": "1,0", "UseConnectedMessaging": true}
    abb_config JSONB,                              -- {"Protocol": "ModbusTCP", "SlaveId": 1, "PlcModel": "AC500"}
    
    -- Status
    enabled BOOLEAN NOT NULL DEFAULT true,
    
    -- Metadata
    description TEXT,
    location VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by VARCHAR(100) DEFAULT 'system'
);

-- ═══════════════════════════════════════════════════════════════════════════
-- PLC TAGS TABLE
-- Tags per PLC (only mapped tags are polled)
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS plc_gateway.plc_tags (
    id SERIAL PRIMARY KEY,
    
    -- Parent PLC
    plc_id VARCHAR(100) NOT NULL REFERENCES plc_gateway.plc_connections(plc_id) ON DELETE CASCADE,
    
    -- Tag Identity
    address VARCHAR(200) NOT NULL,                 -- PLC address (e.g., "DB100.DBD0", "HR100", "MyTag")
    tag_name VARCHAR(200) NOT NULL,                -- Human-readable name
    
    -- Data Type
    data_type VARCHAR(50) NOT NULL DEFAULT 'float', -- bool, int16, int32, float, double, string
    
    -- Scaling (optional)
    scaling_factor DOUBLE PRECISION DEFAULT 1.0,
    "offset" DOUBLE PRECISION DEFAULT 0.0,
    engineering_unit VARCHAR(50) DEFAULT '',       -- "°C", "bar", "RPM"
    
    -- Rate Control
    deadband DOUBLE PRECISION DEFAULT 0,           -- Change threshold for DB writes
    logging_interval_ms INTEGER DEFAULT 1000,      -- Min interval between DB writes
    
    -- Status
    enabled BOOLEAN NOT NULL DEFAULT true,
    
    -- Metadata
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Unique constraint: one address per PLC
    UNIQUE(plc_id, address)
);

-- ═══════════════════════════════════════════════════════════════════════════
-- INDEXES
-- ═══════════════════════════════════════════════════════════════════════════
CREATE INDEX IF NOT EXISTS idx_plc_connections_enabled ON plc_gateway.plc_connections(enabled);
CREATE INDEX IF NOT EXISTS idx_plc_connections_plant ON plc_gateway.plc_connections(plant_id);
CREATE INDEX IF NOT EXISTS idx_plc_tags_plc_id ON plc_gateway.plc_tags(plc_id);
CREATE INDEX IF NOT EXISTS idx_plc_tags_enabled ON plc_gateway.plc_tags(enabled);

-- ═══════════════════════════════════════════════════════════════════════════
-- TRIGGER: Auto-update updated_at
-- ═══════════════════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION plc_gateway.update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_plc_connections_updated ON plc_gateway.plc_connections;
CREATE TRIGGER trg_plc_connections_updated
    BEFORE UPDATE ON plc_gateway.plc_connections
    FOR EACH ROW EXECUTE FUNCTION plc_gateway.update_timestamp();

DROP TRIGGER IF EXISTS trg_plc_tags_updated ON plc_gateway.plc_tags;
CREATE TRIGGER trg_plc_tags_updated
    BEFORE UPDATE ON plc_gateway.plc_tags
    FOR EACH ROW EXECUTE FUNCTION plc_gateway.update_timestamp();

-- ═══════════════════════════════════════════════════════════════════════════
-- EXAMPLE DATA - Multiple PLCs, Same and Different Manufacturers
-- ═══════════════════════════════════════════════════════════════════════════

-- EXAMPLE 1: Siemens S7-1500 (PLC #1)
INSERT INTO plc_gateway.plc_connections (plc_id, plc_name, plant_id, protocol, ip_address, port, s7_config)
VALUES (
    'SIEMENS_PLC_01',
    'Siemens S7-1500 - Production Line 1',
    'PlantA',
    'SiemensS7',
    '192.168.1.10',
    102,
    '{"CpuType": "S71500", "Rack": 0, "Slot": 1}'
) ON CONFLICT (plc_id) DO NOTHING;

-- EXAMPLE 2: Siemens S7-1200 (PLC #2 - SAME MANUFACTURER, DIFFERENT IP)
INSERT INTO plc_gateway.plc_connections (plc_id, plc_name, plant_id, protocol, ip_address, port, s7_config)
VALUES (
    'SIEMENS_PLC_02',
    'Siemens S7-1200 - Packaging Line',
    'PlantA',
    'SiemensS7',
    '192.168.1.11',
    102,
    '{"CpuType": "S71200", "Rack": 0, "Slot": 1}'
) ON CONFLICT (plc_id) DO NOTHING;

-- EXAMPLE 3: Allen Bradley ControlLogix
INSERT INTO plc_gateway.plc_connections (plc_id, plc_name, plant_id, protocol, ip_address, port, rockwell_config)
VALUES (
    'AB_PLC_01',
    'Allen Bradley ControlLogix - Assembly',
    'PlantA',
    'Rockwell',
    '192.168.1.20',
    44818,
    '{"PlcType": "ControlLogix", "Path": "1,0", "UseConnectedMessaging": true}'
) ON CONFLICT (plc_id) DO NOTHING;

-- EXAMPLE 4: Modbus TCP Device
INSERT INTO plc_gateway.plc_connections (plc_id, plc_name, plant_id, protocol, ip_address, port, modbus_config)
VALUES (
    'MODBUS_RTU_01',
    'Modbus RTU Gateway - Sensors',
    'PlantA',
    'ModbusTcp',
    '192.168.1.30',
    502,
    '{"SlaveId": 1}'
) ON CONFLICT (plc_id) DO NOTHING;

-- EXAMPLE 5: ABB AC500
INSERT INTO plc_gateway.plc_connections (plc_id, plc_name, plant_id, protocol, ip_address, port, abb_config, modbus_config)
VALUES (
    'ABB_PLC_01',
    'ABB AC500 - Utility Control',
    'PlantB',
    'ABB',
    '192.168.2.10',
    502,
    '{"Protocol": "ModbusTCP", "PlcModel": "AC500", "SlaveId": 1}',
    '{"SlaveId": 1}'
) ON CONFLICT (plc_id) DO NOTHING;

-- EXAMPLE 6: Mitsubishi MELSEC
INSERT INTO plc_gateway.plc_connections (plc_id, plc_name, plant_id, protocol, ip_address, port, modbus_config)
VALUES (
    'MITS_PLC_01',
    'Mitsubishi iQ-R - Robot Cell',
    'PlantB',
    'Mitsubishi',
    '192.168.2.20',
    502,
    '{"SlaveId": 1}'
) ON CONFLICT (plc_id) DO NOTHING;

-- ═══════════════════════════════════════════════════════════════════════════
-- EXAMPLE TAGS - Various PLC Types
-- ═══════════════════════════════════════════════════════════════════════════

-- Siemens PLC #1 Tags
INSERT INTO plc_gateway.plc_tags (plc_id, address, tag_name, data_type, engineering_unit) VALUES
('SIEMENS_PLC_01', 'DB100.DBD0', 'Temperature_Tank1', 'float', '°C'),
('SIEMENS_PLC_01', 'DB100.DBD4', 'Pressure_Tank1', 'float', 'bar'),
('SIEMENS_PLC_01', 'DB100.DBD8', 'Level_Tank1', 'float', '%'),
('SIEMENS_PLC_01', 'DB100.DBX12.0', 'Pump1_Running', 'bool', ''),
('SIEMENS_PLC_01', 'DB100.DBW14', 'Motor1_Speed', 'int16', 'RPM')
ON CONFLICT (plc_id, address) DO NOTHING;

-- Siemens PLC #2 Tags (SEPARATE from PLC #1!)
INSERT INTO plc_gateway.plc_tags (plc_id, address, tag_name, data_type, engineering_unit) VALUES
('SIEMENS_PLC_02', 'DB200.DBD0', 'Conveyor_Speed', 'float', 'm/min'),
('SIEMENS_PLC_02', 'DB200.DBD4', 'Box_Count', 'int32', 'pcs'),
('SIEMENS_PLC_02', 'DB200.DBX8.0', 'Conveyor_Running', 'bool', '')
ON CONFLICT (plc_id, address) DO NOTHING;

-- Allen Bradley Tags
INSERT INTO plc_gateway.plc_tags (plc_id, address, tag_name, data_type, engineering_unit) VALUES
('AB_PLC_01', 'Assembly_Temp', 'Assembly Temperature', 'real', '°F'),
('AB_PLC_01', 'Assembly_Pressure', 'Assembly Pressure', 'real', 'PSI'),
('AB_PLC_01', 'Robot_Position[0]', 'Robot X Position', 'dint', 'mm'),
('AB_PLC_01', 'Robot_Position[1]', 'Robot Y Position', 'dint', 'mm'),
('AB_PLC_01', 'Cycle_Active', 'Cycle Active', 'bool', '')
ON CONFLICT (plc_id, address) DO NOTHING;

-- Modbus Tags
INSERT INTO plc_gateway.plc_tags (plc_id, address, tag_name, data_type, engineering_unit) VALUES
('MODBUS_RTU_01', 'HR0', 'Sensor1_Value', 'float', ''),
('MODBUS_RTU_01', 'HR2', 'Sensor2_Value', 'float', ''),
('MODBUS_RTU_01', 'HR4', 'Sensor3_Value', 'float', ''),
('MODBUS_RTU_01', 'C0', 'Relay1_Status', 'bool', ''),
('MODBUS_RTU_01', 'C1', 'Relay2_Status', 'bool', '')
ON CONFLICT (plc_id, address) DO NOTHING;

-- ABB Tags
INSERT INTO plc_gateway.plc_tags (plc_id, address, tag_name, data_type, engineering_unit) VALUES
('ABB_PLC_01', '%MW100', 'Utility_Power', 'float', 'kW'),
('ABB_PLC_01', '%MW102', 'Utility_Voltage', 'float', 'V'),
('ABB_PLC_01', '%M0.0', 'Breaker1_Status', 'bool', '')
ON CONFLICT (plc_id, address) DO NOTHING;

-- Mitsubishi Tags
INSERT INTO plc_gateway.plc_tags (plc_id, address, tag_name, data_type, engineering_unit) VALUES
('MITS_PLC_01', 'D100', 'Robot_Torque', 'float', 'Nm'),
('MITS_PLC_01', 'D102', 'Robot_Speed', 'int16', '%'),
('MITS_PLC_01', 'M100', 'Robot_Ready', 'bool', ''),
('MITS_PLC_01', 'M101', 'Robot_Fault', 'bool', '')
ON CONFLICT (plc_id, address) DO NOTHING;

-- ═══════════════════════════════════════════════════════════════════════════
-- VERIFICATION QUERIES
-- ═══════════════════════════════════════════════════════════════════════════

-- View all PLCs
-- SELECT * FROM plc_gateway.plc_connections;

-- View tags per PLC
-- SELECT c.plc_id, c.plc_name, c.protocol, COUNT(t.id) as tag_count
-- FROM plc_gateway.plc_connections c
-- LEFT JOIN plc_gateway.plc_tags t ON c.plc_id = t.plc_id
-- WHERE c.enabled = true
-- GROUP BY c.plc_id, c.plc_name, c.protocol;

-- View all enabled tags
-- SELECT c.plc_id, c.protocol, t.address, t.tag_name, t.data_type
-- FROM plc_gateway.plc_tags t
-- JOIN plc_gateway.plc_connections c ON t.plc_id = c.plc_id
-- WHERE t.enabled = true AND c.enabled = true
-- ORDER BY c.plc_id, t.address;
