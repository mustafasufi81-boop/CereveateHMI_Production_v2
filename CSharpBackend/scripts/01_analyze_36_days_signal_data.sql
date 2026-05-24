/* ====================================================================
   SIGNAL DATA ANALYSIS - 36 DAYS HISTORICAL DATA
   
   Purpose: Analyze historian_timeseries data to calculate alarm thresholds
   - Reads last 36 days of data for all enabled tags
   - Calculates min, max, avg, stddev for each tag
   - Suggests alarm limits based on observed ranges
   - Outputs report for review and approval
   
   Date: December 22, 2025
   Usage: Run this script and review output before updating tag_master
==================================================================== */

-- Step 1: Create temporary analysis table
DROP TABLE IF EXISTS temp_signal_analysis;

CREATE TEMP TABLE temp_signal_analysis AS
SELECT 
    tm.tag_id,
    tm.tag_name,
    tm.data_type,
    tm.eng_unit,
    tm.equipment,
    tm.area,
    tm.plant,
    
    -- Statistical analysis from historian_timeseries (36 days)
    COUNT(ts.value_num) AS sample_count,
    MIN(ts.value_num) AS observed_min,
    MAX(ts.value_num) AS observed_max,
    AVG(ts.value_num) AS observed_avg,
    STDDEV(ts.value_num) AS observed_stddev,
    
    -- Value range
    (MAX(ts.value_num) - MIN(ts.value_num)) AS value_range,
    
    -- Data quality metrics
    MIN(ts.time) AS first_sample_time,
    MAX(ts.time) AS last_sample_time,
    EXTRACT(EPOCH FROM (MAX(ts.time) - MIN(ts.time)))/3600 AS observation_hours,
    
    -- Suggested alarm thresholds (based on observed range)
    -- LOW-LOW: min - 10% of range
    ROUND((MIN(ts.value_num) - (MAX(ts.value_num) - MIN(ts.value_num)) * 0.10)::numeric, 2) AS suggested_ll_limit,
    
    -- LOW: min - 5% of range
    ROUND((MIN(ts.value_num) - (MAX(ts.value_num) - MIN(ts.value_num)) * 0.05)::numeric, 2) AS suggested_l_limit,
    
    -- HIGH: max + 5% of range
    ROUND((MAX(ts.value_num) + (MAX(ts.value_num) - MIN(ts.value_num)) * 0.05)::numeric, 2) AS suggested_h_limit,
    
    -- HIGH-HIGH: max + 10% of range
    ROUND((MAX(ts.value_num) + (MAX(ts.value_num) - MIN(ts.value_num)) * 0.10)::numeric, 2) AS suggested_hh_limit,
    
    -- Current configured limits (if any)
    tm.alarm_ll_limit AS current_ll_limit,
    tm.alarm_l_limit AS current_l_limit,
    tm.alarm_h_limit AS current_h_limit,
    tm.alarm_hh_limit AS current_hh_limit,
    tm.alarm_enabled AS alarm_currently_enabled,
    
    -- Recommendation based on data quality
    CASE 
        WHEN COUNT(ts.value_num) < 1000 THEN 'INSUFFICIENT_DATA'
        WHEN (MAX(ts.value_num) - MIN(ts.value_num)) < 0.01 THEN 'CONSTANT_VALUE'
        WHEN COUNT(ts.value_num) >= 10000 THEN 'HIGH_CONFIDENCE'
        WHEN COUNT(ts.value_num) >= 5000 THEN 'GOOD_CONFIDENCE'
        ELSE 'MODERATE_CONFIDENCE'
    END AS data_quality_recommendation

FROM historian_meta.tag_master tm
LEFT JOIN historian_raw.historian_timeseries ts 
    ON tm.tag_id = ts.tag_id
    AND ts.time >= now() - INTERVAL '36 days'
    AND ts.value_num IS NOT NULL  -- Only numeric values
    
WHERE tm.enabled = true
  AND tm.data_type IN ('Double', 'Int32', 'UInt16', 'Int16')  -- Numeric types only

GROUP BY 
    tm.tag_id, tm.tag_name, tm.data_type, tm.eng_unit,
    tm.equipment, tm.area, tm.plant,
    tm.alarm_ll_limit, tm.alarm_l_limit, 
    tm.alarm_h_limit, tm.alarm_hh_limit,
    tm.alarm_enabled

ORDER BY sample_count DESC, tag_id;


-- Step 2: Display comprehensive analysis report
\echo ''
\echo '======================================================================'
\echo '         SIGNAL DATA ANALYSIS REPORT (36 DAYS)'
\echo '======================================================================'
\echo ''

-- Summary statistics
\echo '--- SUMMARY STATISTICS ---'
SELECT 
    COUNT(*) AS total_tags_analyzed,
    SUM(CASE WHEN sample_count >= 10000 THEN 1 ELSE 0 END) AS high_confidence_tags,
    SUM(CASE WHEN sample_count >= 5000 THEN 1 ELSE 0 END) AS good_confidence_tags,
    SUM(CASE WHEN sample_count < 1000 THEN 1 ELSE 0 END) AS insufficient_data_tags,
    ROUND(AVG(sample_count)::numeric, 0) AS avg_samples_per_tag,
    ROUND(AVG(observation_hours)::numeric, 1) AS avg_observation_hours
FROM temp_signal_analysis;

\echo ''
\echo '--- DETAILED TAG ANALYSIS ---'
\echo ''

-- Main analysis table
SELECT 
    tag_id,
    tag_name,
    equipment,
    sample_count,
    ROUND(observed_min::numeric, 2) AS min_value,
    ROUND(observed_max::numeric, 2) AS max_value,
    ROUND(observed_avg::numeric, 2) AS avg_value,
    ROUND(observed_stddev::numeric, 2) AS stddev,
    ROUND(value_range::numeric, 2) AS range,
    eng_unit,
    ROUND(observation_hours::numeric, 1) AS hours_analyzed,
    data_quality_recommendation AS data_quality
FROM temp_signal_analysis
ORDER BY 
    CASE data_quality_recommendation
        WHEN 'HIGH_CONFIDENCE' THEN 1
        WHEN 'GOOD_CONFIDENCE' THEN 2
        WHEN 'MODERATE_CONFIDENCE' THEN 3
        WHEN 'CONSTANT_VALUE' THEN 4
        WHEN 'INSUFFICIENT_DATA' THEN 5
    END,
    sample_count DESC;

\echo ''
\echo '--- SUGGESTED ALARM THRESHOLDS ---'
\echo ''

-- Suggested alarm thresholds
SELECT 
    tag_id,
    tag_name,
    ROUND(observed_min::numeric, 2) AS obs_min,
    ROUND(observed_max::numeric, 2) AS obs_max,
    '→' AS arrow1,
    suggested_ll_limit AS "LL (Low-Low)",
    suggested_l_limit AS "L (Low)",
    suggested_h_limit AS "H (High)",
    suggested_hh_limit AS "HH (High-High)",
    data_quality_recommendation AS confidence
FROM temp_signal_analysis
WHERE data_quality_recommendation IN ('HIGH_CONFIDENCE', 'GOOD_CONFIDENCE', 'MODERATE_CONFIDENCE')
ORDER BY sample_count DESC;

\echo ''
\echo '--- CURRENT VS SUGGESTED LIMITS (For tags with existing config) ---'
\echo ''

-- Compare current vs suggested
SELECT 
    tag_id,
    tag_name,
    'CURRENT' AS config_type,
    current_ll_limit AS ll_limit,
    current_l_limit AS l_limit,
    current_h_limit AS h_limit,
    current_hh_limit AS hh_limit,
    alarm_currently_enabled AS enabled
FROM temp_signal_analysis
WHERE current_hh_limit IS NOT NULL OR current_h_limit IS NOT NULL

UNION ALL

SELECT 
    tag_id,
    tag_name,
    'SUGGESTED' AS config_type,
    suggested_ll_limit AS ll_limit,
    suggested_l_limit AS l_limit,
    suggested_h_limit AS h_limit,
    suggested_hh_limit AS hh_limit,
    NULL AS enabled
FROM temp_signal_analysis
WHERE current_hh_limit IS NOT NULL OR current_h_limit IS NOT NULL

ORDER BY tag_id, config_type DESC;

\echo ''
\echo '--- TAGS REQUIRING ATTENTION ---'
\echo ''

-- Insufficient data warning
SELECT 
    tag_id,
    tag_name,
    sample_count,
    observation_hours,
    'INSUFFICIENT DATA - Need more samples' AS issue
FROM temp_signal_analysis
WHERE data_quality_recommendation = 'INSUFFICIENT_DATA'
ORDER BY sample_count;

-- Constant value warning
SELECT 
    tag_id,
    tag_name,
    observed_min,
    observed_max,
    'CONSTANT VALUE - May be digital signal or stuck sensor' AS issue
FROM temp_signal_analysis
WHERE data_quality_recommendation = 'CONSTANT_VALUE'
ORDER BY tag_id;

\echo ''
\echo '======================================================================'
\echo '                    REVIEW INSTRUCTIONS'
\echo '======================================================================'
\echo ''
\echo 'Please review the suggested alarm thresholds above and:'
\echo ''
\echo '1. Verify suggested limits are reasonable for each tag'
\echo '2. Adjust limits based on equipment specifications'
\echo '3. Consider process safety requirements'
\echo '4. Mark which tags should have alarms enabled'
\echo ''
\echo 'After approval, run: 02_update_tag_master_with_limits.sql'
\echo ''
\echo '======================================================================'
\echo ''

-- Step 3: Export detailed CSV for offline review (optional)
\echo 'Exporting detailed analysis to CSV...'

\copy (SELECT tag_id, tag_name, equipment, area, plant, sample_count, observed_min, observed_max, observed_avg, observed_stddev, value_range, eng_unit, observation_hours, suggested_ll_limit, suggested_l_limit, suggested_h_limit, suggested_hh_limit, current_ll_limit, current_l_limit, current_h_limit, current_hh_limit, alarm_currently_enabled, data_quality_recommendation FROM temp_signal_analysis ORDER BY sample_count DESC) TO 'signal_analysis_36days.csv' WITH CSV HEADER;

\echo ''
\echo 'CSV exported to: signal_analysis_36days.csv'
\echo ''

-- Step 4: Keep analysis table for next script
\echo 'Analysis complete! Temporary table temp_signal_analysis available for next steps.'
\echo ''
