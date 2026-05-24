-- Fix ALL welding tag names to match PLC (with spaces)
-- Based on compare_tag_names.py output:
-- PLC has: "Welding Current A", "Joint ID", etc. (WITH SPACES)
-- DB has: "Welding_Current_A", "Joint_Id", etc. (WITH UNDERSCORES)

BEGIN;

UPDATE historian_meta.tag_master 
SET tag_id = 'Welding Current A', config_updated_at = NOW() 
WHERE tag_id = 'Welding_Current_A';

UPDATE historian_meta.tag_master 
SET tag_id = 'Welding Voltage V', config_updated_at = NOW() 
WHERE tag_id = 'Welding_Voltage_V';

UPDATE historian_meta.tag_master 
SET tag_id = 'Pipe ID', config_updated_at = NOW() 
WHERE tag_id = 'Pipe_Id';

UPDATE historian_meta.tag_master 
SET tag_id = 'Joint ID', config_updated_at = NOW() 
WHERE tag_id = 'Joint_Id';

UPDATE historian_meta.tag_master 
SET tag_id = 'Welder ID', config_updated_at = NOW() 
WHERE tag_id = 'Welder_id';

UPDATE historian_meta.tag_master 
SET tag_id = 'WPS ID', config_updated_at = NOW() 
WHERE tag_id = 'WPS_ID';

UPDATE historian_meta.tag_master 
SET tag_id = 'Simulation Step', config_updated_at = NOW() 
WHERE tag_id = 'sim_step';

-- Verify changes
SELECT tag_id, tag_name, enabled 
FROM historian_meta.tag_master 
WHERE tag_id IN ('Welding Current A', 'Welding Voltage V', 'Pipe ID', 'Joint ID', 'Welder ID', 'WPS ID', 'Simulation Step', 'Arc', 'Power')
ORDER BY tag_id;

COMMIT;
