"""
Update v_alarm_audit_trail view to include new columns
"""
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    database='Automation_DB',
    user='cereveate',
    password='cereveate@222'
)

print("Updating v_alarm_audit_trail view...")

cur = conn.cursor()

# Drop and recreate the view with new columns
cur.execute("""
    DROP VIEW IF EXISTS historian_raw.v_alarm_audit_trail CASCADE;
    
    CREATE VIEW historian_raw.v_alarm_audit_trail AS
    SELECT 
        aat.audit_id,
        aat.event_id,
        aat.tag_id,
        COALESCE(tm.tag_name, aat.tag_id) AS tag_name,
        tm.description AS tag_description,
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
        CASE aat.alarm_priority
            WHEN 5 THEN 'CRITICAL'
            WHEN 4 THEN 'HIGH'
            WHEN 3 THEN 'MEDIUM'
            WHEN 2 THEN 'LOW'
            WHEN 1 THEN 'INFO'
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
        aat.occurrence_id,
        aat.sequence_number,
        aat.performed_by_display_name,
        aat.performed_by_user_id,
        EXTRACT(EPOCH FROM (
            aat.action_timestamp - LAG(aat.action_timestamp) OVER (
                PARTITION BY aat.event_id 
                ORDER BY aat.action_timestamp
            )
        )) / 60.0 AS minutes_since_previous_action,
        EXTRACT(EPOCH FROM (
            aat.action_timestamp - he.time
        )) / 60.0 AS minutes_since_raised,
        CASE 
            WHEN aat.action_type = 'ACKNOWLEDGED' THEN 
                EXTRACT(EPOCH FROM (aat.action_timestamp - he.time))
            ELSE NULL
        END AS response_time_seconds
    FROM historian_raw.alarm_audit_trail aat
    LEFT JOIN historian_raw.historian_events he ON aat.event_id = he.event_id
    LEFT JOIN historian_meta.tag_master tm ON aat.tag_id = tm.tag_id;
""")

conn.commit()
print("✅ View updated successfully with new columns:")
print("   - occurrence_id")
print("   - sequence_number")
print("   - performed_by_display_name")
print("   - performed_by_user_id")

cur.close()
conn.close()
