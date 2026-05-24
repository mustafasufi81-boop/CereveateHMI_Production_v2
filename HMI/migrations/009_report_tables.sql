-- 009_report_tables.sql
-- Daily/Shift/Monthly report core tables

BEGIN;

CREATE TABLE IF NOT EXISTS historian_meta.report_templates (
    id              SERIAL PRIMARY KEY,
    report_type     VARCHAR(20) NOT NULL CHECK (report_type IN ('DAILY', 'SHIFT', 'MONTHLY')),
    s_no            INTEGER NOT NULL,
    tag_id          VARCHAR(200) NOT NULL
                        REFERENCES historian_meta.tag_master(tag_id)
                        ON DELETE CASCADE,
    enabled         BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (report_type, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_report_templates_type_enabled
    ON historian_meta.report_templates(report_type, enabled, s_no);

CREATE TABLE IF NOT EXISTS historian_meta.report_gen_log (
    id              BIGSERIAL PRIMARY KEY,
    report_type     VARCHAR(20) NOT NULL,
    plant           VARCHAR(100),
    area            VARCHAR(100),
    report_date     DATE NOT NULL,
    generated_by    INTEGER REFERENCES historian_meta.users(id),
    generated_at    TIMESTAMPTZ DEFAULT NOW(),
    export_format   VARCHAR(10),
    row_count       INTEGER,
    duration_ms     INTEGER,
    ip_address      VARCHAR(45),
    status          VARCHAR(10) DEFAULT 'SUCCESS'
);

CREATE INDEX IF NOT EXISTS idx_report_gen_log_lookup
    ON historian_meta.report_gen_log(report_type, report_date, generated_at DESC);

COMMIT;
