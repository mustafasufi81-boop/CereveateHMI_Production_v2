-- Fix tag_id to match exact PLC tag names (with spaces, not underscores)
UPDATE historian_meta.tag_master SET tag_id = 'Welding Current A' WHERE tag_id = 'Welding_Current_A';
UPDATE historian_meta.tag_master SET tag_id = 'Welding Voltage V' WHERE tag_id = 'Welding_Voltage_V';
UPDATE historian_meta.tag_master SET tag_id = 'Joint ID' WHERE tag_id = 'Joint_Id';
UPDATE historian_meta.tag_master SET tag_id = 'Pipe ID' WHERE tag_id = 'Pipe_Id';
UPDATE historian_meta.tag_master SET tag_id = 'Welder ID' WHERE tag_id = 'Welder_id';
UPDATE historian_meta.tag_master SET tag_id = 'WPS ID' WHERE tag_id = 'WPS_ID';

-- Verify
SELECT tag_id, tag_name, enabled, plc_slot, plc_ip 
FROM historian_meta.tag_master 
WHERE tag_id IN ('Welding Current A', 'Welding Voltage V', 'Joint ID', 'Pipe ID', 'Welder ID', 'WPS ID', 'sim_step', 'Arc', 'Power')
ORDER BY tag_id;
