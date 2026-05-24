-- Check what data is in the historian_timeseries table
SELECT 
    tag_id,
    time,
    value_num,
    quality,
    COUNT(*) as duplicate_count
FROM historian_raw.historian_timeseries
WHERE tag_id = '@ClientCount'
GROUP BY tag_id, time, value_num, quality
HAVING COUNT(*) > 1
ORDER BY time DESC
LIMIT 20;

-- Show total row count
SELECT 
    'Total rows' as info,
    COUNT(*) as count
FROM historian_raw.historian_timeseries;

-- Show rows per tag
SELECT 
    tag_id,
    COUNT(*) as row_count,
    MIN(time) as earliest,
    MAX(time) as latest
FROM historian_raw.historian_timeseries
GROUP BY tag_id
ORDER BY row_count DESC;
