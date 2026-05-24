-- 011_seed_ftp4_daily_template.sql
-- Seed DAILY report template from existing FTP-4 tags.
-- NOTE:
-- 1) This seed assumes FTP-4 tags exist in historian_meta.tag_master.area = 'FTP-4'.
-- 2) If your area label differs, update the WHERE clause.

BEGIN;

WITH ftp4_tags AS (
    SELECT
        tm.tag_id,
        ROW_NUMBER() OVER (
            ORDER BY
                COALESCE(tm.equipment, ''),
                COALESCE(tm.tag_name, ''),
                tm.tag_id
        ) AS s_no
    FROM historian_meta.tag_master tm
    WHERE tm.enabled = TRUE
      AND tm.area = 'FTP-4'
)
INSERT INTO historian_meta.report_templates (report_type, s_no, tag_id, enabled)
SELECT 'DAILY', f.s_no, f.tag_id, TRUE
FROM ftp4_tags f
ON CONFLICT (report_type, tag_id)
DO UPDATE SET
    s_no = EXCLUDED.s_no,
    enabled = EXCLUDED.enabled;

COMMIT;
