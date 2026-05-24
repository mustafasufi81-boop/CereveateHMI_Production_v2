import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, database='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()

# Test the exact CASE expression from the API for ACK-only events
cur.execute("""
    SELECT
        he.event_id, he.tag_id, he.alarm_state AS raw_state,
        CASE
            WHEN clr_at.action_timestamp IS NOT NULL THEN 'CLEARED'
            WHEN ack_at.action_timestamp IS NOT NULL AND he.alarm_state NOT IN ('RTN_UNACK','CLEARED')
                 THEN 'ACTIVE_ACK'
            ELSE he.alarm_state
        END AS effective_state,
        ack_at.performed_by AS ack_by,
        clr_at.performed_by AS clr_by
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
    WHERE he.event_id IN (66108, 66112, 66018, 65984)
    ORDER BY he.event_id
""")
rows = cur.fetchall()
cols = [d[0] for d in cur.description]
print("=== Effective state for ACK-only events ===")
for r in rows:
    d = dict(zip(cols, r))
    print(f"  event_id={d['event_id']}  raw={d['raw_state']}  effective={d['effective_state']}  ack_by={d['ack_by']}  clr_by={d['clr_by']}")

cur.close(); conn.close()
