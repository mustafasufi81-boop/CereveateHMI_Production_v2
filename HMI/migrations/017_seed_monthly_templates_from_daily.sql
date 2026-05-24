-- 017_seed_monthly_templates_from_daily.sql
-- Seed MONTHLY report templates from existing DAILY templates where missing.

BEGIN;

INSERT INTO historian_meta.report_templates (report_type, s_no, tag_id, enabled)
SELECT 'MONTHLY', rt.s_no, rt.tag_id, rt.enabled
FROM historian_meta.report_templates rt
WHERE rt.report_type = 'DAILY'
ON CONFLICT (report_type, tag_id)
DO UPDATE SET
    s_no = EXCLUDED.s_no,
    enabled = EXCLUDED.enabled;

COMMIT;
