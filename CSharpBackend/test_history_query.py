import sys; sys.path.insert(0, 'WEB_HMI_MFA/HMI')
from container import container
import psycopg2
cfg = container.historical_service.db_config
conn = psycopg2.connect(**cfg)
cur = conn.cursor()

sql = """
SELECT he.event_id, he.tag_id, he."time" AS raised_at, he.event_type,
       he.alarm_state, he.alarm_priority, he.alarm_level, he.message,
       he.alarm_setpoint, he.alarm_actual_value, he.severity,
       he.acknowledged_by, he.acknowledged_at, he.cleared_by, he.cleared_at,
       he.clear_reason, he.clear_notes,
       ack_at.performed_by, ack_at.action_timestamp, ack_at.action_notes,
       clr_at.performed_by, clr_at.action_timestamp, clr_at.action_reason, clr_at.action_notes,
       CASE WHEN he.cleared_at IS NOT NULL
            THEN ROUND(EXTRACT(EPOCH FROM (he.cleared_at - he."time"))/60.0, 1)
            ELSE ROUND(EXTRACT(EPOCH FROM (NOW() - he."time"))/60.0, 1)
       END AS duration_minutes
FROM historian_raw.historian_events he
LEFT JOIN LATERAL (
    SELECT performed_by, action_timestamp, action_notes
    FROM historian_raw.alarm_audit_trail
    WHERE event_id = he.event_id AND action_type = 'ACKNOWLEDGED'
    ORDER BY action_timestamp DESC LIMIT 1
) ack_at ON TRUE
LEFT JOIN LATERAL (
    SELECT performed_by, action_timestamp, action_reason, action_notes
    FROM historian_raw.alarm_audit_trail
    WHERE event_id = he.event_id AND action_type = 'CLEARED'
    ORDER BY action_timestamp DESC LIMIT 1
) clr_at ON TRUE
ORDER BY he."time" DESC
LIMIT 5 OFFSET 0
"""

try:
    cur.execute(sql)
    rows = cur.fetchall()
    print(f"OK — {len(rows)} rows")
    if rows:
        print("First row event_id:", rows[0][0])
except Exception as e:
    print("SQL ERROR:", repr(e))
cur.close()
conn.close()
