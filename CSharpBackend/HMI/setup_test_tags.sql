-- Check current tag mappings
SELECT tag_id, tag_name, data_type, enabled, created_at
FROM historian_meta.tag_master
ORDER BY tag_id;

-- If empty, insert the 2 visible tags from HMI
INSERT INTO historian_meta.tag_master (tag_id, tag_name, data_type, enabled, created_by)
VALUES 
    ('Random.Int1', 'Random Integer', 'Int32', true, 'HMI'),
    ('Saw-toothed Waves.Int1', 'Saw-tooth Wave', 'Int32', true, 'HMI')
ON CONFLICT (tag_id) DO UPDATE 
SET enabled = true, config_updated_at = NOW();

-- Verify
SELECT tag_id, tag_name, enabled 
FROM historian_meta.tag_master
ORDER BY tag_id;
