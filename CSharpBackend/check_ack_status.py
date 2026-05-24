import psycopg2, json
conn = psycopg2.connect(host='localhost', port=5432, database='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()

# Check Triangle Waves.Real4 LOW events around 02:07:12
cur.execute("""
    SELECT he.event_id, he.tag_id, he."time", he.alarm_state, he.alarm_level,
           he.alarm_priority, he.acknowledged_by, he.acknowledged_at, he.cleared_by, he.cleared_at
    FROM historian_raw.historian_events he
    WHERE he.tag_id = 'Triangle Waves.Real4' AND he.alarm_level = 'LOW'
      AND he."time" BETWEEN '2026-05-13 02:07:00' AND '2026-05-13 02:07:30'
    ORDER BY he."time" DESC LIMIT 5
""")
rows = cur.fetchall()
cols = [d[0] for d in cur.description]
print("=== historian_events ===")
for r in rows:
    d = dict(zip(cols, r))
    print(json.dumps({k: str(v) if v is not None else None for k, v in d.items()}, indent=2))

# Check audit trail for those event_ids
if rows:
    eids = [r[0] for r in rows]
    cur.execute("""
        SELECT event_id, action_type, action_timestamp, performed_by, previous_state, new_state
        FROM historian_raw.alarm_audit_trail
        WHERE event_id = ANY(%s)
        ORDER BY action_timestamp
    """, [eids])
    audit = cur.fetchall()
    acols = [d[0] for d in cur.description]
    print("\n=== alarm_audit_trail ===")
    for r in audit:
        print(dict(zip(acols, r)))
else:
    print("No events found in that time range")

# Also check alarm_active for current live state
cur.execute("""
    SELECT tag_id, level, alarm_state, raised_at, ack_by, ack_at, rtn_at
    FROM historian_raw.alarm_active
    WHERE tag_id = 'Triangle Waves.Real4'
""")
active = cur.fetchall()
acols2 = [d[0] for d in cur.description]
print("\n=== alarm_active (live state) ===")
for r in active:
    print(dict(zip(acols2, r)))

cur.close()
conn.close()
