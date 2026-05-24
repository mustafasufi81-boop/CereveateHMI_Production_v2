-- =============================================================================
-- PHASE 1 — TIMESCALE REPORTING MIGRATION (Production-Ready)
-- =============================================================================
-- Based on: REPORTING_ARCHITECTURE_RECOMMENDATION.md
-- Phase 1 Scope:
--   1. Drop old normal SQL view
--   2. Create HOURLY ONLY continuous aggregate (no minute/daily)
--   3. Add refresh policy (10 min, 7-day start, 5-min end)
--   4. Compression already enabled in production_schema.sql
-- =============================================================================

\echo '==================== PHASE 1 REPORTING MIGRATION ===================='
\echo 'Based on: REPORTING_ARCHITECTURE_RECOMMENDATION.md'
\echo 'Scope: HOURLY aggregate only - no minute/daily aggregates'
\echo ''

-- =============================================================================
-- PRE-FLIGHT CHECKS
-- =============================================================================
\echo 'Pre-flight checks...'

-- Verify TimescaleDB extension exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        RAISE EXCEPTION 'TimescaleDB extension not found. Cannot proceed.';
    END IF;
    RAISE NOTICE 'TimescaleDB extension: OK';
END $$;

-- Verify hypertable exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.hypertables 
        WHERE hypertable_schema = 'historian_raw' 
        AND hypertable_name = 'historian_timeseries'
    ) THEN
        RAISE EXCEPTION 'historian_timeseries is not a hypertable. Run production_schema.sql first.';
    END IF;
    RAISE NOTICE 'Hypertable status: OK';
END $$;

\echo 'Pre-flight checks passed!'
\echo ''

-- =============================================================================
-- STEP 1: DROP OLD VIEW
-- =============================================================================
\echo 'Step 1: Dropping old normal SQL view...'

-- Drop existing view if it exists
DROP VIEW IF EXISTS historian_raw.v_daily_hourly_agg CASCADE;

\echo 'Old view dropped successfully!'
\echo ''

-- =============================================================================
-- STEP 2: CREATE HOURLY CONTINUOUS AGGREGATE
-- =============================================================================
\echo 'Step 2: Creating HOURLY continuous aggregate...'
\echo 'NOTE: This is the ONLY aggregate in Phase 1 per architecture document.'
\echo ''

-- Create hourly continuous aggregate
-- Uses time_bucket on 'time' column (primary key)
-- Includes timezone conversion to Asia/Kolkata for local_date and local_hour
CREATE MATERIALIZED VIEW historian_raw.ca_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour'::interval, time) AS hour_bucket,
    tag_id,
    -- Compute local_date and local_hour for report compatibility
    DATE(time AT TIME ZONE 'Asia/Kolkata') AS local_date,
    EXTRACT(HOUR FROM time AT TIME ZONE 'Asia/Kolkata')::INT AS local_hour,
    -- Aggregated values
    ROUND(AVG(value_num)::NUMERIC, 2) AS avg_val,
    ROUND(MAX(value_num)::NUMERIC, 2) AS max_val,
    ROUND(MIN(value_num)::NUMERIC, 2) AS min_val,
    COUNT(*) AS sample_count
FROM historian_raw.historian_timeseries
WHERE quality = 'G'
  AND value_num IS NOT NULL
GROUP BY hour_bucket, tag_id, local_date, local_hour;

\echo 'Hourly continuous aggregate created!'
\echo ''

-- =============================================================================
-- STEP 3: CREATE INDEXES ON CONTINUOUS AGGREGATE
-- =============================================================================
\echo 'Step 3: Creating indexes on ca_hourly...'

-- Index for tag-based queries
CREATE INDEX idx_ca_hourly_tag_date 
ON historian_raw.ca_hourly (tag_id, local_date);

-- Index for date-based queries
CREATE INDEX idx_ca_hourly_date 
ON historian_raw.ca_hourly (local_date DESC);

-- Index for time bucket queries
CREATE INDEX idx_ca_hourly_bucket 
ON historian_raw.ca_hourly (hour_bucket DESC);

\echo 'Indexes created successfully!'
\echo ''

-- =============================================================================
-- STEP 4: CREATE COMPATIBILITY VIEW
-- =============================================================================
\echo 'Step 4: Creating compatibility view (v_daily_hourly_agg)...'
\echo 'This view maps ca_hourly to existing report code interface.'
\echo ''

-- Create compatibility view that matches old view structure
-- This allows existing report code to work without changes initially
CREATE OR REPLACE VIEW historian_raw.v_daily_hourly_agg AS
SELECT
    tag_id,
    local_date,
    local_hour AS hour,  -- Map local_hour to 'hour' for backward compatibility
    avg_val,
    max_val,
    min_val
FROM historian_raw.ca_hourly;

\echo 'Compatibility view created!'
\echo ''

-- =============================================================================
-- STEP 5: ADD REFRESH POLICY
-- =============================================================================
\echo 'Step 5: Adding refresh policy for hourly aggregate...'
\echo 'Policy: refresh every 10 minutes, cover recent 7 days, lag 5 minutes'
\echo ''

-- Add continuous aggregate refresh policy
-- Per architecture document:
--   - schedule_interval: 10 minutes
--   - start_offset: 7 days (backfill window for late data)
--   - end_offset: 5 minutes (freshness lag)
SELECT add_continuous_aggregate_policy('historian_raw.ca_hourly',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '10 minutes',
    if_not_exists => TRUE
);

\echo 'Refresh policy added successfully!'
\echo ''

-- =============================================================================
-- STEP 6: VERIFY COMPRESSION POLICY EXISTS
-- =============================================================================
\echo 'Step 6: Verifying compression policy on raw historian...'

-- Check if compression policy exists
DO $$
DECLARE
    policy_count INT;
BEGIN
    SELECT COUNT(*) INTO policy_count
    FROM timescaledb_information.jobs
    WHERE application_name LIKE '%Compression%'
    AND hypertable_name = 'historian_timeseries';
    
    IF policy_count = 0 THEN
        RAISE WARNING 'No compression policy found. This should have been created by production_schema.sql';
    ELSE
        RAISE NOTICE 'Compression policy exists: OK (% policies found)', policy_count;
    END IF;
END $$;

\echo ''

-- =============================================================================
-- STEP 7: GRANT PERMISSIONS
-- =============================================================================
\echo 'Step 7: Granting permissions...'

-- Grant SELECT on continuous aggregate
GRANT SELECT ON historian_raw.ca_hourly TO cereveate;
GRANT SELECT ON historian_raw.ca_hourly TO opc_app_user;

-- Grant SELECT on compatibility view
GRANT SELECT ON historian_raw.v_daily_hourly_agg TO cereveate;
GRANT SELECT ON historian_raw.v_daily_hourly_agg TO opc_app_user;

\echo 'Permissions granted!'
\echo ''

-- =============================================================================
-- STEP 8: INITIAL REFRESH (OPTIONAL - COMMENTED OUT FOR SAFETY)
-- =============================================================================
\echo 'Step 8: Initial refresh...'
\echo 'NOTE: Automatic refresh will happen within 10 minutes via policy.'
\echo 'To force immediate refresh, uncomment and run manually:'
\echo ''
\echo '-- CALL refresh_continuous_aggregate(''historian_raw.ca_hourly'', now() - INTERVAL ''7 days'', now());'
\echo ''

-- =============================================================================
-- VERIFICATION QUERIES
-- =============================================================================
\echo '=========================================================='
\echo '               PHASE 1 MIGRATION COMPLETE!               '
\echo '=========================================================='
\echo ''
\echo 'Verification:'
\echo ''

-- Show hypertable info
\echo 'Hypertable Status:'
SELECT 
    hypertable_schema,
    hypertable_name,
    num_dimensions,
    num_chunks,
    compression_enabled,
    replication_factor
FROM timescaledb_information.hypertables
WHERE hypertable_schema = 'historian_raw'
  AND hypertable_name = 'historian_timeseries';

\echo ''
\echo 'Continuous Aggregates:'
SELECT 
    view_schema,
    view_name,
    materialized_only,
    compression_enabled,
    materialization_hypertable_name
FROM timescaledb_information.continuous_aggregates
WHERE view_schema = 'historian_raw';

\echo ''
\echo 'Background Jobs:'
SELECT 
    job_id,
    application_name,
    schedule_interval,
    next_start,
    last_run_status
FROM timescaledb_information.jobs
WHERE hypertable_schema = 'historian_raw'
ORDER BY job_id;

\echo ''
\echo '=========================================================='
\echo '                   IMPORTANT NOTES                        '
\echo '=========================================================='
\echo ''
\echo '1. NO minute or daily aggregates deployed (per Phase 1 scope)'
\echo '2. Hourly aggregate will auto-refresh every 10 minutes'
\echo '3. Compression policy already exists from production_schema.sql'
\echo '4. Report code can continue using v_daily_hourly_agg view'
\echo '5. Monitor job status with: SELECT * FROM timescaledb_information.job_stats;'
\echo ''
\echo 'Next Steps:'
\echo '- Monitor aggregate refresh lag'
\echo '- Validate report performance'
\echo '- Observe compression behavior'
\echo '- After stabilization, consider Phase 2 (snapshots)'
\echo ''
