-- Test: Insert one tag into historian_meta.tag_master
-- This will test the complete pipeline: OPC → Rate Control → Batch → DB

INSERT INTO historian_meta.tag_master 
    (tag_id, tag_name, description, plant, area, equipment, 
     data_type, eng_unit, db_logging_interval_ms, enabled, 
     db_table_name, mapping_version, created_by)
VALUES 
    ('TAG001', 
     'Test Turbine Speed', 
     'Test tag for historian pipeline validation',
     'PLANT1', 
     'TURBINE', 
     'TURB01',
     'double',
     'RPM',
     5000,  -- Log every 5 seconds
     TRUE,
     'historian_raw.historian_timeseries',
     1,
     'TEST_SETUP')
ON CONFLICT (tag_id) DO UPDATE SET
    db_logging_interval_ms = 5000,
    enabled = TRUE,
    config_updated_at = now(),
    mapping_version = historian_meta.tag_master.mapping_version + 1;

-- Verify the tag was inserted
SELECT tag_id, tag_name, db_logging_interval_ms, enabled, mapping_version
FROM historian_meta.tag_master
WHERE tag_id = 'TAG001';
