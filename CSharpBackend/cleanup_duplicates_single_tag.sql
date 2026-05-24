-- ============================================================
-- CLEANUP DUPLICATE VALUES FOR SINGLE TAG (TEST)
-- ============================================================
-- This script removes duplicate values within the same second
-- Keeps only the FIRST occurrence of each unique value per second
-- ============================================================

-- Step 1: Find duplicates for Random.UInt2 (TEST TAG)
SELECT 
    tag_id,
    DATE_TRUNC('second', time) as second_bucket,
    value_num,
    COUNT(*) as duplicate_count,
    MIN(time) as first_time,
    MAX(time) as last_time
FROM historian_raw.historian_timeseries
WHERE tag_id = 'Random.UInt2'
GROUP BY tag_id, second_bucket, value_num
HAVING COUNT(*) > 1
ORDER BY second_bucket DESC
LIMIT 20;

-- Step 2: Show total rows before cleanup
SELECT 
    tag_id,
    COUNT(*) as total_rows,
    COUNT(DISTINCT DATE_TRUNC('second', time)) as unique_seconds
FROM historian_raw.historian_timeseries
WHERE tag_id = 'Random.UInt2'
GROUP BY tag_id;

-- Step 3: DELETE duplicates (keeps first occurrence per second per value)
-- UNCOMMENT TO EXECUTE:
/*
WITH duplicates AS (
    SELECT 
        id,
        ROW_NUMBER() OVER (
            PARTITION BY tag_id, DATE_TRUNC('second', time), value_num 
            ORDER BY time ASC
        ) as row_num
    FROM historian_raw.historian_timeseries
    WHERE tag_id = 'Random.UInt2'
)
DELETE FROM historian_raw.historian_timeseries
WHERE id IN (
    SELECT id FROM duplicates WHERE row_num > 1
);
*/

-- Step 4: Verify cleanup (run after uncommenting Step 3)
-- SELECT 
--     tag_id,
--     COUNT(*) as total_rows_after,
--     COUNT(DISTINCT DATE_TRUNC('second', time)) as unique_seconds_after
-- FROM historian_raw.historian_timeseries
-- WHERE tag_id = 'Random.UInt2'
-- GROUP BY tag_id;
