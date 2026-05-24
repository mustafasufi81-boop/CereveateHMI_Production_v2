-- Add PLC connection columns to tag_master
ALTER TABLE historian_meta.tag_master 
ADD COLUMN IF NOT EXISTS plc_ip_address VARCHAR(50),
ADD COLUMN IF NOT EXISTS plc_port INTEGER,
ADD COLUMN IF NOT EXISTS plc_protocol VARCHAR(50),
ADD COLUMN IF NOT EXISTS plc_slot INTEGER,
ADD COLUMN IF NOT EXISTS plc_path VARCHAR(50),
ADD COLUMN IF NOT EXISTS plc_timeout_ms INTEGER,
ADD COLUMN IF NOT EXISTS plc_polling_interval_ms INTEGER;

-- Update Rockwell PLC connection details
UPDATE historian_meta.tag_master 
SET 
    plc_ip_address = '192.168.0.20',
    plc_port = 44818,
    plc_protocol = 'Rockwell',
    plc_slot = 0,
    plc_path = '1,0',
    plc_timeout_ms = 3000,
    plc_polling_interval_ms = 1000
WHERE server_progid = 'Rockwel_PLC_001';

-- Verify
SELECT DISTINCT 
    server_progid, 
    plc_protocol, 
    plc_ip_address, 
    plc_port, 
    plc_slot,
    plc_path,
    COUNT(*) as tag_count
FROM historian_meta.tag_master 
WHERE server_progid = 'Rockwel_PLC_001'
GROUP BY server_progid, plc_protocol, plc_ip_address, plc_port, plc_slot, plc_path;
