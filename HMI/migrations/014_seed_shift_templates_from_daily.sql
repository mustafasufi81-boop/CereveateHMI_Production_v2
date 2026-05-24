-- 014_seed_shift_templates_from_daily.sql
-- Seed SHIFT report templates from existing DAILY templates.
-- This keeps tag ordering and enabled state aligned between Daily and Shift reports.

BEGIN;

INSERT INTO historian_meta.report_templates (report_type, s_no, tag_id, enabled)
SELECT 'SHIFT', rt.s_no, rt.tag_id, rt.enabled
FROM historian_meta.report_templates rt
WHERE rt.report_type = 'DAILY'
ON CONFLICT (report_type, tag_id)
DO UPDATE SET
    s_no = EXCLUDED.s_no,
    enabled = EXCLUDED.enabled;

COMMIT;
