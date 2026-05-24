-- 015_seed_equipment1_both_report_templates.sql
-- Seed BOTH DAILY and SHIFT report templates from Equipment1 tags in Plant1/Area1.

BEGIN;

WITH equipment1_tags AS (
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
      AND tm.equipment = 'Equipment1'
)
INSERT INTO historian_meta.report_templates (report_type, s_no, tag_id, enabled)
SELECT 'DAILY', e.s_no, e.tag_id, TRUE
FROM equipment1_tags e
ON CONFLICT (report_type, tag_id)
DO UPDATE SET
    s_no = EXCLUDED.s_no,
    enabled = EXCLUDED.enabled;

WITH equipment1_tags AS (
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
      AND tm.equipment = 'Equipment1'
)
INSERT INTO historian_meta.report_templates (report_type, s_no, tag_id, enabled)
SELECT 'SHIFT', e.s_no, e.tag_id, TRUE
FROM equipment1_tags e
ON CONFLICT (report_type, tag_id)
DO UPDATE SET
    s_no = EXCLUDED.s_no,
    enabled = EXCLUDED.enabled;

COMMIT;
