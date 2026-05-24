-- Test the exact query that historical_data.py is running
-- Run this in your PostgreSQL client to debug

-- 1. First check if data exists for the tag
SELECT 
    tag_id, 
    COUNT(*) as total_rows,
    MIN(time) as earliest,
    MAX(time) as latest
FROM historian_raw.historian_timeseries
WHERE tag_id = 'Saw-toothed Waves.Int1'
GROUP BY tag_id;

-- 2. Check data in the last hour (same time range as service)
SELECT 
    tag_id,
    COUNT(*) as count_last_hour,
    MIN(time) as earliest_hour,
    MAX(time) as latest_hour
FROM historian_raw.historian_timeseries
WHERE tag_id = 'Saw-toothed Waves.Int1' 
  AND time >= NOW() - INTERVAL '1 hour'
  AND time <= NOW()
GROUP BY tag_id;

-- 3. The EXACT query from get_multiple_trends() method
SELECT 
    tag_id,
    time_bucket('36 seconds'::interval, time) AS timestamp,
    AVG(value_num) as value,
    MAX(quality) as quality
FROM historian_raw.historian_timeseries
WHERE tag_id = ANY(ARRAY['Saw-toothed Waves.Int1']) 
  AND time >= NOW() - INTERVAL '1 hour'
  AND time <= NOW()
GROUP BY tag_id, time_bucket('36 seconds'::interval, time)
ORDER BY tag_id, timestamp
LIMIT 10;

-- 4. Simplified version without time_bucket to test basic query
SELECT 
    tag_id,
    time AS timestamp,
    value_num as value,
    quality
FROM historian_raw.historian_timeseries
WHERE tag_id = 'Saw-toothed Waves.Int1'
  AND time >= NOW() - INTERVAL '1 hour'
  AND time <= NOW()
ORDER BY time DESC
LIMIT 5;