-- 023_seed_all_report_types_for_boiler1_generato1_transformer1.sql
-- Seed DAILY, SHIFT, and MONTHLY report templates from Plant1/Area1 tags
-- for Boiler1, Generato1/Generator1, and Transformer1.

BEGIN;

WITH report_types AS (
    SELECT 'DAILY'::VARCHAR(20) AS report_type
    UNION ALL SELECT 'SHIFT'::VARCHAR(20)
    UNION ALL SELECT 'MONTHLY'::VARCHAR(20)
),
selected_tags AS (
    SELECT
        tm.tag_id,
        COALESCE(tm.equipment, '') AS equipment,
        COALESCE(tm.sub_equipment, '') AS sub_equipment,
        COALESCE(tm.tag_name, '') AS tag_name
    FROM historian_meta.tag_master tm
    WHERE tm.enabled = TRUE
      AND tm.plant = 'Plant1'
      AND tm.area = 'Area1'
      AND tm.equipment IN ('Boiler1', 'Generato1', 'Generator1', 'Transformer1')
),
ordered_tags AS (
    SELECT
        rt.report_type,
        st.tag_id,
        ROW_NUMBER() OVER (
            PARTITION BY rt.report_type
            ORDER BY
                st.equipment,
                st.sub_equipment,
                st.tag_name,
                st.tag_id
        ) AS row_no
    FROM selected_tags st
    CROSS JOIN report_types rt
),
base AS (
    SELECT
        rt.report_type,
        COALESCE(MAX(rpt.s_no), 0) AS base_s_no
    FROM report_types rt
    LEFT JOIN historian_meta.report_templates rpt
        ON rpt.report_type = rt.report_type
    GROUP BY rt.report_type
)
INSERT INTO historian_meta.report_templates (report_type, s_no, tag_id, enabled)
SELECT
    ot.report_type,
    b.base_s_no + ot.row_no,
    ot.tag_id,
    TRUE
FROM ordered_tags ot
JOIN base b
  ON b.report_type = ot.report_type
ON CONFLICT (report_type, tag_id)
DO UPDATE SET
    s_no = EXCLUDED.s_no,
    enabled = EXCLUDED.enabled;

COMMIT;
