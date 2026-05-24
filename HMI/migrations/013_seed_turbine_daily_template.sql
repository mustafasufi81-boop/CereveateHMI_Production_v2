-- 013_seed_turbine_daily_template.sql
-- Seed DAILY report template from Turbine1 tags in Plant1, Area1.

BEGIN;

WITH turbine_tags AS (
    SELECT
        tm.tag_id,
        ROW_NUMBER() OVER (
            ORDER BY
                COALESCE(tm.equipment, ''),
                COALESCE(tm.sub_equipment, ''),
                COALESCE(tm.tag_name, ''),
                tm.tag_id
        ) AS s_no
    FROM historian_meta.tag_master tm
    WHERE tm.enabled = TRUE
      AND tm.plant = 'Plant1'
      AND tm.area = 'Area1'
      AND tm.equipment = 'Turbine1'
)
INSERT INTO historian_meta.report_templates (report_type, s_no, tag_id, enabled)
SELECT 'DAILY', t.s_no, t.tag_id, TRUE
FROM turbine_tags t
ON CONFLICT (report_type, tag_id)
DO UPDATE SET
    s_no = EXCLUDED.s_no,
    enabled = EXCLUDED.enabled;

COMMIT;
