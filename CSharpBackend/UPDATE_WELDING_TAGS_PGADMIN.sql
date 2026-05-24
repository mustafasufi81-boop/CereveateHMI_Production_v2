-- Run this in pgAdmin Query Tool  
-- tag_id is CORRECT with underscores (matches PLC tags)
-- Just ensure tag_name also has underscores for consistency
UPDATE historian_meta.tag_master SET tag_name = tag_id WHERE tag_id IN ('Welding_Current_A', 'Welding_Voltage_V', 'Joint_Id', 'Pipe_Id', 'Welder_id', 'WPS_ID', 'sim_step', 'Arc', 'Power');

-- Verify
SELECT tag_id, tag_name, enabled, plc_ip, server_progid
FROM historian_meta.tag_master 
WHERE tag_id IN ('Welding_Current_A', 'Welding_Voltage_V', 'Joint_Id', 'Pipe_Id', 'Welder_id', 'WPS_ID', 'sim_step', 'Arc', 'Power')
ORDER BY tag_id;
