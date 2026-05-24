-- ============================================================================
-- MIGRATION: Update v_alarm_audit_trail view
-- Adds: minutes_since_raised, response_time_seconds columns
-- Run on any DB that already has the alarm_audit_trail table created.
-- Safe to re-run (CREATE OR REPLACE VIEW is idempotent).
-- ============================================================================

CREATE OR REPLACE VIEW historian_raw.v_alarm_audit_trail AS
SELECT
    aat.audit_id,
    aat.event_id,
    aat.tag_id,
    COALESCE(tm.tag_name, aat.tag_id)  AS tag_name,
    tm.description                      AS tag_description,
    tm.plant,
    tm.area,
    tm.equipment,
    aat.event_type,
    aat.action_type,
    aat.action_timestamp,
    aat.performed_by,
    aat.previous_state,
    aat.new_state,
    aat.alarm_priority,
    CASE
        WHEN aat.alarm_priority = 5 THEN 'CRITICAL'
        WHEN aat.alarm_priority = 4 THEN 'HIGH'
        WHEN aat.alarm_priority = 3 THEN 'MEDIUM'
        WHEN aat.alarm_priority = 2 THEN 'LOW'
        WHEN aat.alarm_priority = 1 THEN 'INFO'
        ELSE 'UNKNOWN'
    END AS priority_label,
    aat.alarm_actual_value,
    aat.alarm_setpoint,
    aat.action_reason,
    aat.action_notes,
    aat.session_id,
    aat.client_ip,
    aat.metadata,
    aat.created_at,

    -- Time between this action and the PREVIOUS action on the same alarm
    LAG(aat.action_timestamp) OVER (
        PARTITION BY aat.event_id ORDER BY aat.action_timestamp
    ) AS previous_action_time,

    EXTRACT(EPOCH FROM (
        aat.action_timestamp
        - LAG(aat.action_timestamp) OVER (
              PARTITION BY aat.event_id ORDER BY aat.action_timestamp
          )
    )) / 60 AS minutes_since_previous_action,

    -- Time since RAISED (first action in this alarm's lifecycle)
    -- Used by DAO.get_audit_trail_enhanced() and get_operator_statistics()
    EXTRACT(EPOCH FROM (
        aat.action_timestamp
        - FIRST_VALUE(aat.action_timestamp) OVER (
              PARTITION BY aat.event_id ORDER BY aat.action_timestamp
              ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
          )
    )) / 60 AS minutes_since_raised,

    EXTRACT(EPOCH FROM (
        aat.action_timestamp
        - FIRST_VALUE(aat.action_timestamp) OVER (
              PARTITION BY aat.event_id ORDER BY aat.action_timestamp
              ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
          )
    )) AS response_time_seconds

FROM historian_raw.alarm_audit_trail aat
LEFT JOIN historian_meta.tag_master tm ON aat.tag_id = tm.tag_id;

-- Re-grant access (idempotent)
GRANT SELECT ON historian_raw.v_alarm_audit_trail TO opc_app_user;

\echo 'v_alarm_audit_trail view updated — minutes_since_raised + response_time_seconds added'
