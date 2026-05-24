-- Simple query to see all values written by the test
-- Shows all records where sample_source = 'OPC_DA'

SELECT 
    time,
    tag_id,
    value_num,
    quality,
    sample_source,
    mapping_version
FROM historian_raw.historian_timeseries
WHERE sample_source = 'OPC_DA'
ORDER BY time DESC;

