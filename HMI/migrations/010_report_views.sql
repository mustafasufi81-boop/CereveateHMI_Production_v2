-- 010_report_views.sql
-- Report support views

BEGIN;

CREATE OR REPLACE VIEW historian_meta.v_report_template_tags AS
SELECT
    rt.report_type,
    rt.s_no,
    rt.tag_id,
    rt.enabled AS template_enabled,
    tm.tag_name AS display_label,
    tm.equipment AS group_name,
    COALESCE(tm.eng_unit, tm.data_type, '') AS parameter_unit,
    tm.plant,
    tm.area,
    tm.enabled AS tag_enabled
FROM historian_meta.report_templates rt
JOIN historian_meta.tag_master tm
  ON tm.tag_id = rt.tag_id;

CREATE OR REPLACE VIEW historian_raw.v_daily_hourly_agg AS
SELECT
    ht.tag_id,
    DATE(ht.time AT TIME ZONE 'Asia/Kolkata') AS local_date,
    EXTRACT(HOUR FROM ht.time AT TIME ZONE 'Asia/Kolkata')::INT AS local_hour,
    ROUND(AVG(ht.value_num)::NUMERIC, 2) AS avg_val,
    ROUND(MAX(ht.value_num)::NUMERIC, 2) AS max_val,
    ROUND(MIN(ht.value_num)::NUMERIC, 2) AS min_val
FROM historian_raw.historian_timeseries ht
INNER JOIN historian_meta.tag_master tm ON tm.tag_id = ht.tag_id
WHERE ht.quality = 'G'
  AND ht.value_num IS NOT NULL
  AND tm.enabled = true
GROUP BY
    ht.tag_id,
    DATE(ht.time AT TIME ZONE 'Asia/Kolkata'),
    EXTRACT(HOUR FROM ht.time AT TIME ZONE 'Asia/Kolkata');

COMMIT;
