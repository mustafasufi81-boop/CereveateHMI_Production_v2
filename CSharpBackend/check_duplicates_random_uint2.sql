-- Check duplicates for Random.UInt2 tag
-- Show rows that have same value in same second

SELECT 
    DATE_TRUNC('second', time) as second_bucket,
    value_num,
    COUNT(*) as duplicate_count,
    STRING_AGG(to_char(time, 'HH24:MI:SS.MS'), ', ' ORDER BY time) as timestamps
FROM historian_raw.historian_timeseries
WHERE tag_id = 'Random.UInt2'
GROUP BY second_bucket, value_num
HAVING COUNT(*) > 1
ORDER BY second_bucket DESC
LIMIT 10;

-- Summary statistics
SELECT 
    'Total rows' as metric,
    COUNT(*) as value
FROM historian_raw.historian_timeseries
WHERE tag_id = 'Random.UInt2'

UNION ALL

SELECT 
    'Rows with duplicates in same second',
    COUNT(*)
FROM (
    SELECT time, value_num
    FROM historian_raw.historian_timeseries
    WHERE tag_id = 'Random.UInt2'
    GROUP BY DATE_TRUNC('second', time), value_num, time
    HAVING COUNT(*) > 1
) sub;
