/* ====================================================================
   UPDATE TAG_MASTER WITH APPROVED ALARM LIMITS
   
   Purpose: Apply alarm thresholds to tag_master after review
   - Updates alarm limits based on reviewed analysis
   - Enables alarms for approved tags
   - Sets alarm priorities based on criticality
   
   Date: December 22, 2025
   
   IMPORTANT: Review output from 01_analyze_36_days_signal_data.sql first!
   Modify the WHERE clause to select specific tags for alarm configuration.
==================================================================== */

\echo ''
\echo '======================================================================'
\echo '     UPDATING TAG_MASTER WITH ALARM LIMITS'
\echo '======================================================================'
\echo ''

-- Ensure analysis table exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_tables WHERE tablename = 'temp_signal_analysis') THEN
        RAISE EXCEPTION 'Analysis table not found! Run 01_analyze_36_days_signal_data.sql first.';
    END IF;
END $$;

-- Step 1: Update observed min/max values in tag_master
\echo 'Step 1: Updating observed min/max values...'

UPDATE historian_meta.tag_master tm
SET 
    observed_min_value = sa.observed_min,
    observed_max_value = sa.observed_max,
    observation_start_time = sa.first_sample_time,
    observation_sample_count = sa.sample_count,
    last_observation_update = now()
FROM temp_signal_analysis sa
WHERE tm.tag_id = sa.tag_id
  AND sa.data_quality_recommendation IN ('HIGH_CONFIDENCE', 'GOOD_CONFIDENCE', 'MODERATE_CONFIDENCE');

SELECT format('✓ Updated observation data for %s tags', COUNT(*)) AS status
FROM temp_signal_analysis
WHERE data_quality_recommendation IN ('HIGH_CONFIDENCE', 'GOOD_CONFIDENCE', 'MODERATE_CONFIDENCE');

\echo ''

-- Step 2: Apply suggested alarm thresholds (AUTO-APPLY for high confidence tags)
\echo 'Step 2: Applying suggested alarm thresholds...'

UPDATE historian_meta.tag_master tm
SET 
    alarm_ll_limit = sa.suggested_ll_limit,
    alarm_l_limit = sa.suggested_l_limit,
    alarm_h_limit = sa.suggested_h_limit,
    alarm_hh_limit = sa.suggested_hh_limit,
    
    -- Set alarm priority based on sample confidence
    alarm_priority = CASE 
        WHEN sa.data_quality_recommendation = 'HIGH_CONFIDENCE' THEN 4  -- Urgent
        WHEN sa.data_quality_recommendation = 'GOOD_CONFIDENCE' THEN 3  -- Medium
        ELSE 2  -- Low
    END,
    
    -- Enable alarms for high/good confidence tags
    alarm_enabled = CASE 
        WHEN sa.data_quality_recommendation IN ('HIGH_CONFIDENCE', 'GOOD_CONFIDENCE') THEN true
        ELSE false
    END,
    
    alarm_deadband = ROUND((sa.value_range * 0.02)::numeric, 2),  -- 2% of range
    
    config_updated_at = now()
    
FROM temp_signal_analysis sa
WHERE tm.tag_id = sa.tag_id
  AND sa.data_quality_recommendation IN ('HIGH_CONFIDENCE', 'GOOD_CONFIDENCE', 'MODERATE_CONFIDENCE')
  AND sa.sample_count >= 5000;  -- Only apply if sufficient data

SELECT format('✓ Applied alarm thresholds to %s tags', COUNT(*)) AS status
FROM temp_signal_analysis
WHERE data_quality_recommendation IN ('HIGH_CONFIDENCE', 'GOOD_CONFIDENCE')
  AND sample_count >= 5000;

\echo ''

-- Step 3: Display updated configuration
\echo 'Step 3: Verifying updated configuration...'
\echo ''

SELECT 
    tm.tag_id,
    tm.tag_name,
    tm.alarm_ll_limit AS "LL Limit",
    tm.alarm_l_limit AS "L Limit",
    tm.alarm_h_limit AS "H Limit",
    tm.alarm_hh_limit AS "HH Limit",
    tm.alarm_priority AS priority,
    tm.alarm_deadband AS deadband,
    tm.alarm_enabled AS enabled,
    sa.sample_count AS samples,
    sa.data_quality_recommendation AS confidence
FROM historian_meta.tag_master tm
JOIN temp_signal_analysis sa ON tm.tag_id = sa.tag_id
WHERE tm.alarm_enabled = true
ORDER BY tm.alarm_priority DESC, tm.tag_id;

\echo ''
\echo '======================================================================'
\echo '                    CONFIGURATION SUMMARY'
\echo '======================================================================'
\echo ''

-- Summary statistics
SELECT 
    COUNT(*) AS total_tags_configured,
    SUM(CASE WHEN alarm_enabled = true THEN 1 ELSE 0 END) AS alarms_enabled,
    SUM(CASE WHEN alarm_priority = 5 THEN 1 ELSE 0 END) AS priority_5_critical,
    SUM(CASE WHEN alarm_priority = 4 THEN 1 ELSE 0 END) AS priority_4_urgent,
    SUM(CASE WHEN alarm_priority = 3 THEN 1 ELSE 0 END) AS priority_3_medium,
    SUM(CASE WHEN alarm_priority <= 2 THEN 1 ELSE 0 END) AS priority_2_1_low
FROM historian_meta.tag_master
WHERE alarm_hh_limit IS NOT NULL OR alarm_h_limit IS NOT NULL;

\echo ''
\echo '======================================================================'
\echo '                    NEXT STEPS'
\echo '======================================================================'
\echo ''
\echo '1. ✓ Alarm thresholds configured in tag_master'
\echo '2. → Start C# AlarmGenerationService to monitor tag values'
\echo '3. → Deploy Web UI to display active alarms'
\echo '4. → Test alarm generation with simulated data'
\echo ''
\echo 'Configuration complete!'
\echo ''
