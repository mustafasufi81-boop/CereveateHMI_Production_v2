-- 012_report_permissions.sql
-- Grants for Daily Report objects to application DB user

BEGIN;

-- Tables
GRANT SELECT ON historian_meta.report_templates TO opc_app_user;
GRANT SELECT, INSERT ON historian_meta.report_gen_log TO opc_app_user;

-- Views
GRANT SELECT ON historian_meta.v_report_template_tags TO opc_app_user;
GRANT SELECT ON historian_raw.v_daily_hourly_agg TO opc_app_user;

-- Sequence permissions required for inserts into BIGSERIAL/SERIAL columns
GRANT USAGE ON SEQUENCE historian_meta.report_gen_log_id_seq TO opc_app_user;

COMMIT;
