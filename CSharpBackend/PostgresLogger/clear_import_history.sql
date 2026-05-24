-- Clear file import history to allow re-import
DELETE FROM file_imports WHERE file_path LIKE '%ALL_SENSORS_COMPLETE_FORWARDFILL%';

-- Check current data
SELECT COUNT(*) as record_count FROM sensor_data WHERE tag_code = 'SHAFT_VIB._IP_REAR-X';
