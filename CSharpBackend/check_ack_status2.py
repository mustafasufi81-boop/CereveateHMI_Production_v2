import psycopg2, json
conn = psycopg2.connect(host='localhost', port=5432, database='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()

# Find recent Triangle Waves.Real4 LOW events that have audit trail entries (Mustafa)
cur.execute("""
    SELECT he.event_id, he.tag_id, he."time" AT TIME ZONE 'UTC' as time_utc, 
           he."time" as time_local,
           he.alarm_state, he.alarm_level, he.alarm_priority,
           he.acknowledged_by, he.acknowledged_at, he.cleared_by, he.cleared_at
    FROM historian_raw.historian_events he
    WHERE he.tag_id = 'Triangle Waves.Real4' AND he.alarm_level IN ('LOW', 'Low')
    ORDER BY he."time" DESC LIMIT 10
""")
rows = cur.fetchall()
cols = [d[0] for d in cur.description]
print("=== Recent Triangle Waves.Real4 LOW events ===")
for r in rows:
    d = dict(zip(cols, r))
    print(f"  event_id={d['event_id']}  state={d['alarm_state']}  ack_by={d['acknowledged_by']}  cleared_by={d['cleared_by']}  time={d['time_local']}")

# Find ALL audit trail entries for Mustafa
cur.execute("""
    SELECT aat.event_id, aat.tag_id, aat.action_type, aat.action_timestamp,
           aat.performed_by, aat.previous_state, aat.new_state,
           he.alarm_state as current_he_state
    FROM historian_raw.alarm_audit_trail aat
    JOIN historian_raw.historian_events he ON he.event_id = aat.event_id
    WHERE aat.performed_by ILIKE '%mustafa%'
    ORDER BY aat.action_timestamp DESC LIMIT 20
""")
audit = cur.fetchall()
acols = [d[0] for d in cur.description]
print("\n=== All Mustafa audit entries (latest 20) ===")
for r in audit:
    d = dict(zip(acols, r))
    print(f"  event_id={d['event_id']} tag={d['tag_id']} action={d['action_type']} he_state={d['current_he_state']} at={d['action_timestamp']}")

cur.close()
conn.close()
