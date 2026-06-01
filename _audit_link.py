import psycopg2, json
conn = psycopg2.connect(host='localhost', port=5432, dbname='postgres', user='postgres', password='postgres')
cur = conn.cursor()
cur.execute("""
    SELECT he.event_id, he.event_type, he.alarm_state, he."time"::time
    FROM historian_raw.historian_events he
    WHERE he.tag_id = 'AY1101'
    ORDER BY he."time" DESC
    LIMIT 6
""")
rows = cur.fetchall()
event_ids = [r[0] for r in rows]
print("=== historian_events ===")
for r in rows:
    print(f"  event_id={r[0]}, type={r[1]}, state={r[2]}, time={r[3]}")

print("\n=== alarm_audit_trail for these event_ids ===")
cur.execute("""
    SELECT event_id, action_type, action_timestamp::time, performed_by
    FROM historian_raw.alarm_audit_trail
    WHERE event_id = ANY(%s)
    ORDER BY action_timestamp
""", (event_ids,))
for r in cur.fetchall():
    print(f"  event_id={r[0]}, action={r[1]}, time={r[2]}, by={r[3]}")

cur.close(); conn.close()
