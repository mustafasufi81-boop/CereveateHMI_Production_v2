-- Insert PLC tags for ROCKWELL_001
-- Run this SQL in your PostgreSQL database

INSERT INTO plc_tags (plc_id, address, tag_name, data_type, enabled, created_at, updated_at, plant_id) 
VALUES 
    ('ROCKWELL_001', 'Cooling_FAN_SPEED', 'Cooling_FAN_SPEED', 'REAL', true, NOW(), NOW(), 'PLANT_001'),
    ('ROCKWELL_001', 'High_Temp_Limit', 'High_Temp_Limit', 'REAL', true, NOW(), NOW(), 'PLANT_001'),
    ('ROCKWELL_001', 'Tank_Level', 'Tank_Level', 'REAL', true, NOW(), NOW(), 'PLANT_001'),
    ('ROCKWELL_001', 'Pump_Status', 'Pump_Status', 'BOOL', true, NOW(), NOW(), 'PLANT_001'),
    ('ROCKWELL_001', 'Motor_RPM', 'Motor_RPM', 'REAL', true, NOW(), NOW(), 'PLANT_001'),
    ('ROCKWELL_001', 'Pressure_PSI', 'Pressure_PSI', 'REAL', true, NOW(), NOW(), 'PLANT_001'),
    ('ROCKWELL_001', 'Flow_Rate', 'Flow_Rate', 'REAL', true, NOW(), NOW(), 'PLANT_001'),
    ('ROCKWELL_001', 'Valve_Position', 'Valve_Position', 'REAL', true, NOW(), NOW(), 'PLANT_001'),
    ('ROCKWELL_001', 'Alarm_Status', 'Alarm_Status', 'BOOL', true, NOW(), NOW(), 'PLANT_001'),
    ('ROCKWELL_001', 'Production_Count', 'Production_Count', 'DINT', true, NOW(), NOW(), 'PLANT_001')
ON CONFLICT (plc_id, address) DO UPDATE SET 
    enabled = EXCLUDED.enabled,
    updated_at = NOW();

-- Verify the tags were inserted
SELECT plc_id, address, tag_name, data_type, enabled 
FROM plc_tags 
WHERE plc_id = 'ROCKWELL_001' 
ORDER BY tag_name;