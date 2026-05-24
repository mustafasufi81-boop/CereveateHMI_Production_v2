-- ============================================
-- FIX DUPLICATE KEY ERROR IN HISTORIAN
-- ============================================
-- Primary Key: (tag_id, time) - must be unique
-- This clears all old data so new data can save
-- ============================================

-- OPTION 1: Delete ALL data (fastest, cleanest)
TRUNCATE TABLE historian_raw.historian_timeseries;

-- OPTION 2: Delete only specific tag data (if you want to keep other tags)
-- DELETE FROM historian_raw.historian_timeseries WHERE tag_id = '@ClientCount';

-- OPTION 3: Delete only recent duplicate data (last 1 hour)
-- DELETE FROM historian_raw.historian_timeseries 
-- WHERE time >= NOW() - INTERVAL '1 hour';

-- Verify table is empty
SELECT COUNT(*) as remaining_rows FROM historian_raw.historian_timeseries;

-- Show message
SELECT 'Database cleared - circuit breaker will auto-close in 30 seconds' as status;
