-- Check shift configuration in database
SELECT id, shift_code, shift_name, start_time, end_time, is_active
FROM historian_meta.shifts
ORDER BY start_time;

-- Check if there's data for the specific date and shift hours
SELECT 
    tag_id,
    local_date,
    local_hour,
    COUNT(*) as record_count
FROM historian_raw.v_daily_hourly_agg
WHERE local_date = '2026-05-17'
  AND local_hour BETWEEN 6 AND 13
GROUP BY tag_id, local_date, local_hour
ORDER BY tag_id, local_hour
LIMIT 50;

-- Check available tags for FTP-1 and POTLINE
SELECT 
    tm.tag_id,
    tm.tag_name,
    tm.equipment,
    tm.sub_equipment,
    tm.plant,
    tm.area,
    tm.server_progid,
    tm.enabled,
    tm.include_in_report
FROM historian_meta.tag_master tm
WHERE tm.plant = 'FTP-1'
  AND tm.area = 'POTLINE'
  AND tm.enabled = TRUE
LIMIT 20;
