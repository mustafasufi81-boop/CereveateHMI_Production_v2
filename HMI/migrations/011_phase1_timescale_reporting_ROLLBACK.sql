-- =============================================================================
-- PHASE 1 ROLLBACK SCRIPT
-- =============================================================================
-- Reverts changes made by 011_phase1_timescale_reporting.sql
-- =============================================================================

\echo '==================== PHASE 1 ROLLBACK ===================='
\echo 'WARNING: This will revert to normal SQL view'
\echo ''

-- =============================================================================
-- STEP 1: DROP CONTINUOUS AGGREGATE POLICY
-- =============================================================================
\echo 'Step 1: Removing continuous aggregate refresh policy...'

-- Remove refresh policy
SELECT remove_continuous_aggregate_policy('historian_raw.ca_hourly', if_exists => TRUE);

\echo 'Policy removed!'
\echo ''

-- =============================================================================
-- STEP 2: DROP COMPATIBILITY VIEW
-- =============================================================================
\echo 'Step 2: Dropping compatibility view...'

DROP VIEW IF EXISTS historian_raw.v_daily_hourly_agg CASCADE;

\echo 'Compatibility view dropped!'
\echo ''

-- =============================================================================
-- STEP 3: DROP CONTINUOUS AGGREGATE
-- =============================================================================
\echo 'Step 3: Dropping continuous aggregate...'

DROP MATERIALIZED VIEW IF EXISTS historian_raw.ca_hourly CASCADE;

\echo 'Continuous aggregate dropped!'
\echo ''

-- =============================================================================
-- STEP 4: RECREATE ORIGINAL VIEW
-- =============================================================================
\echo 'Step 4: Recreating original normal SQL view...'

CREATE OR REPLACE VIEW historian_raw.v_daily_hourly_agg AS
SELECT
    ht.tag_id,
    DATE(ht.time AT TIME ZONE 'Asia/Kolkata') AS local_date,
    EXTRACT(HOUR FROM ht.time AT TIME ZONE 'Asia/Kolkata')::INT AS hour,
    ROUND(AVG(ht.value_num)::NUMERIC, 2) AS avg_val,
    ROUND(MAX(ht.value_num)::NUMERIC, 2) AS max_val,
    ROUND(MIN(ht.value_num)::NUMERIC, 2) AS min_val
FROM historian_raw.historian_timeseries ht
WHERE ht.quality = 'G'
  AND ht.value_num IS NOT NULL
GROUP BY
    ht.tag_id,
    DATE(ht.time AT TIME ZONE 'Asia/Kolkata'),
    EXTRACT(HOUR FROM ht.time AT TIME ZONE 'Asia/Kolkata');

\echo 'Original view recreated!'
\echo ''

-- =============================================================================
-- STEP 5: GRANT PERMISSIONS
-- =============================================================================
\echo 'Step 5: Granting permissions...'

GRANT SELECT ON historian_raw.v_daily_hourly_agg TO cereveate;
GRANT SELECT ON historian_raw.v_daily_hourly_agg TO opc_app_user;

\echo 'Permissions granted!'
\echo ''

-- =============================================================================
-- VERIFICATION
-- =============================================================================
\echo '=========================================================='
\echo '               ROLLBACK COMPLETE                          '
\echo '=========================================================='
\echo ''
\echo 'System reverted to original state:'
\echo '- Continuous aggregate removed'
\echo '- Normal SQL view restored'
\echo '- Hypertable and compression unchanged'
\echo ''
\echo 'NOTE: Hypertable and compression remain enabled.'
\echo 'If full reversion needed, run production_schema.sql restore.'
\echo ''
