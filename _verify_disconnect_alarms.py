import psycopg2

c = psycopg2.connect(host='localhost', database='Automation_DB',
                     user='cereveate', password='cereveate@222')
cur = c.cursor()

# Any alarm events at all in the last 3 minutes (the disconnect window)?
cur.execute("""
    SELECT time, tag_id, event_type, alarm_state, alarm_level, alarm_actual_value
    FROM historian_raw.historian_events
    WHERE time > now() - interval '3 minutes'
    ORDER BY time DESC
    LIMIT 30
""")
rows = cur.fetchall()
print(f"=== historian_events in last 3 min: {len(rows)} ===")
for r in rows:
    print(f"  {r[0]}  tag={r[1]}  type={r[2]}  state={r[3]}  level={r[4]}  val={r[5]}")

# Currently active alarms (alarm_active) — are any tied to PLC_001 tags?
cur.execute("""
    SELECT alarm_key, tag_id, alarm_state, alarm_level, raised_value, updated_at
    FROM historian_raw.alarm_active
    ORDER BY updated_at DESC
    LIMIT 30
""")
act = cur.fetchall()
print(f"\n=== alarm_active rows: {len(act)} ===")
for r in act:
    print(f"  key={r[0]}  tag={r[1]}  state={r[2]}  level={r[3]}  raised={r[4]}  updated={r[5]}")

c.close()
