-- =============================================================================
-- PHASE 1 MONITORING QUERIES
-- =============================================================================
-- Based on: REPORTING_ARCHITECTURE_RECOMMENDATION.md
-- Section: "Timescale operational monitoring"
-- =============================================================================

\echo '==================== TIMESCALE MONITORING ===================='
\echo ''

-- =============================================================================
-- 1. BACKGROUND JOBS STATUS
-- =============================================================================
\echo '1. Background Jobs Status:'
\echo ''

SELECT 
    job_id,
    application_name,
    schedule_interval,
    config,
    next_start,
    scheduled
FROM timescaledb_information.jobs
WHERE hypertable_schema = 'historian_raw'
ORDER BY job_id;

\echo ''

-- =============================================================================
-- 2. JOB EXECUTION HISTORY
-- =============================================================================
\echo '2. Job Execution History:'
\echo ''

SELECT 
    job_id,
    last_run_status,
    last_successful_finish,
    total_runs,
    total_successes,
    total_failures,
    CASE 
        WHEN total_runs > 0 
        THEN ROUND((total_failures::NUMERIC / total_runs * 100), 2) 
        ELSE 0 
    END AS failure_rate_pct
FROM timescaledb_information.job_stats
WHERE job_id IN (
    SELECT job_id 
    FROM timescaledb_information.jobs 
    WHERE hypertable_schema = 'historian_raw'
)
ORDER BY job_id;

\echo ''

-- =============================================================================
-- 3. CONTINUOUS AGGREGATE REFRESH LAG
-- =============================================================================
\echo '3. Continuous Aggregate Refresh Lag:'
\echo ''

SELECT 
    view_name,
    materialized_only,
    completed_threshold,
    now() - completed_threshold AS lag,
    CASE 
        WHEN (now() - completed_threshold) > INTERVAL '30 minutes' 
        THEN 'WARNING: Lag exceeds 30 minutes' 
        ELSE 'OK' 
    END AS status
FROM timescaledb_information.continuous_aggregates
WHERE view_schema = 'historian_raw';

\echo ''

-- =============================================================================
-- 4. COMPRESSION STATUS
-- =============================================================================
\echo '4. Compression Status:'
\echo ''

SELECT 
    hypertable_name,
    total_chunks,
    number_compressed_chunks,
    pg_size_pretty(before_compression_total_bytes) AS uncompressed_size,
    pg_size_pretty(after_compression_total_bytes) AS compressed_size,
    ROUND(
        (before_compression_total_bytes::NUMERIC - after_compression_total_bytes::NUMERIC) 
        / NULLIF(before_compression_total_bytes::NUMERIC, 0) * 100, 
        2
    ) AS compression_ratio_pct
FROM timescaledb_information.hypertables h
LEFT JOIN timescaledb_information.compression_settings cs USING (hypertable_name)
WHERE hypertable_schema = 'historian_raw'
  AND hypertable_name = 'historian_timeseries';

\echo ''

-- =============================================================================
-- 5. CHUNK HEALTH CHECK
-- =============================================================================
\echo '5. Chunk Health (Recent 20 chunks):'
\echo ''

SELECT 
    chunk_schema,
    chunk_name,
    range_start,
    range_end,
    is_compressed,
    pg_size_pretty(total_bytes) AS chunk_size,
    CASE 
        WHEN total_bytes < 100 * 1024 * 1024 THEN 'WARNING: Chunk too small' 
        WHEN total_bytes > 10 * 1024 * 1024 * 1024 THEN 'WARNING: Chunk too large' 
        ELSE 'OK' 
    END AS size_status
FROM timescaledb_information.chunks
WHERE hypertable_schema = 'historian_raw'
  AND hypertable_name = 'historian_timeseries'
ORDER BY range_start DESC
LIMIT 20;

\echo ''

-- =============================================================================
-- 6. AGGREGATE DATA AVAILABILITY
-- =============================================================================
\echo '6. Aggregate Data Availability:'
\echo ''

SELECT 
    'ca_hourly' AS aggregate_name,
    MIN(hour_bucket) AS earliest_data,
    MAX(hour_bucket) AS latest_data,
    COUNT(DISTINCT tag_id) AS tag_count,
    COUNT(*) AS total_rows
FROM historian_raw.ca_hourly;

\echo ''

-- =============================================================================
-- 7. RECENT AGGREGATE SAMPLE
-- =============================================================================
\echo '7. Recent Aggregate Sample (last hour):'
\echo ''

SELECT 
    hour_bucket,
    tag_id,
    local_date,
    local_hour,
    avg_val,
    sample_count
FROM historian_raw.ca_hourly
WHERE hour_bucket >= now() - INTERVAL '1 hour'
ORDER BY hour_bucket DESC
LIMIT 10;

\echo ''

-- =============================================================================
-- 8. RAW HISTORIAN INSERT RATE
-- =============================================================================
\echo '8. Raw Historian Insert Rate (last 10 minutes):'
\echo ''

SELECT 
    time_bucket('1 minute', time) AS minute_bucket,
    COUNT(*) AS inserts_per_minute
FROM historian_raw.historian_timeseries
WHERE time >= now() - INTERVAL '10 minutes'
GROUP BY minute_bucket
ORDER BY minute_bucket DESC;

\echo ''

-- =============================================================================
-- 9. DATABASE SIZE
-- =============================================================================
\echo '9. Database Size:'
\echo ''

SELECT 
    pg_size_pretty(pg_database_size('Automation_DB')) AS database_size;

\echo ''

-- =============================================================================
-- 10. HYPERTABLE SIZE
-- =============================================================================
\echo '10. Hypertable Size:'
\echo ''

SELECT 
    hypertable_name,
    pg_size_pretty(total_bytes) AS total_size,
    pg_size_pretty(index_bytes) AS index_size,
    pg_size_pretty(toast_bytes) AS toast_size,
    pg_size_pretty(compressed_total_size) AS compressed_size
FROM timescaledb_information.hypertables h
LEFT JOIN (
    SELECT 
        format('%I.%I', hypertable_schema, hypertable_name)::regclass AS hypertable_id,
        SUM(compressed_total_size) AS compressed_total_size
    FROM timescaledb_information.chunks
    WHERE is_compressed = TRUE
    GROUP BY hypertable_schema, hypertable_name
) c ON h.hypertable_name = c.hypertable_id::text
WHERE hypertable_schema = 'historian_raw'
  AND hypertable_name = 'historian_timeseries';

\echo ''

-- =============================================================================
-- ALERTS
-- =============================================================================
\echo '=========================================================='
\echo '                      ALERTS                              '
\echo '=========================================================='
\echo ''

-- Check for job failures
DO $$
DECLARE
    failure_rate NUMERIC;
    job_name TEXT;
BEGIN
    FOR job_name, failure_rate IN 
        SELECT 
            j.application_name,
            CASE 
                WHEN js.total_runs > 0 
                THEN (js.total_failures::NUMERIC / js.total_runs * 100) 
                ELSE 0 
            END
        FROM timescaledb_information.job_stats js
        JOIN timescaledb_information.jobs j USING (job_id)
        WHERE j.hypertable_schema = 'historian_raw'
    LOOP
        IF failure_rate > 5 THEN
            RAISE WARNING 'HIGH ALERT: Job "%" has failure rate of %%', job_name, failure_rate;
        END IF;
    END LOOP;
END $$;

-- Check for refresh lag
DO $$
DECLARE
    lag_interval INTERVAL;
    view_name TEXT;
BEGIN
    FOR view_name, lag_interval IN 
        SELECT 
            ca.view_name,
            now() - ca.completed_threshold
        FROM timescaledb_information.continuous_aggregates ca
        WHERE ca.view_schema = 'historian_raw'
    LOOP
        IF lag_interval > INTERVAL '30 minutes' THEN
            RAISE WARNING 'MEDIUM ALERT: Aggregate "%" has refresh lag of %', view_name, lag_interval;
        END IF;
    END LOOP;
END $$;

-- Check for uncompressed chunks older than 3 days
DO $$
DECLARE
    old_chunk_count INT;
BEGIN
    SELECT COUNT(*) INTO old_chunk_count
    FROM timescaledb_information.chunks
    WHERE hypertable_schema = 'historian_raw'
      AND hypertable_name = 'historian_timeseries'
      AND is_compressed = FALSE
      AND range_end < now() - INTERVAL '3 days';
    
    IF old_chunk_count > 0 THEN
        RAISE WARNING 'LOW ALERT: % uncompressed chunks older than 3 days', old_chunk_count;
    END IF;
END $$;

\echo ''
\echo '=========================================================='
\echo '              MONITORING CHECK COMPLETE                   '
\echo '=========================================================='
\echo ''
