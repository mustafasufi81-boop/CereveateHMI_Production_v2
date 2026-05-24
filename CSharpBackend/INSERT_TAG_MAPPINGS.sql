-- Insert tag mappings for historian database writes
-- This enables the historian to write OPC data to PostgreSQL

INSERT INTO historian_meta.tag_master (tag_id, tag_name, data_type, enabled, created_by)
VALUES 
    ('Random.Real4', 'Random Value (Real4)', 'Double', true, 'admin'),
    ('Random.Real8', 'Random Value (Real8)', 'Double', true, 'admin'),
    ('@ClientCount', 'Client Count', 'Integer', true, 'admin')
ON CONFLICT (tag_id) DO UPDATE 
SET enabled = true, 
    tag_name = EXCLUDED.tag_name,
    data_type = EXCLUDED.data_type;

-- Verify the mappings
SELECT tag_id, tag_name, data_type, enabled, created_at 
FROM historian_meta.tag_master 
ORDER BY tag_id;
