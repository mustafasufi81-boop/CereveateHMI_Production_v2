import psycopg2
c = psycopg2.connect(dbname='Automation_DB', user='cereveate', password='cereveate@222', host='localhost')
cur = c.cursor()

print("=== ALARM_ACTIVE TABLE ===")
cur.execute("SELECT alarm_key, tag_id, level, alarm_state, raised_at, raised_value, setpoint_value, priority FROM historian_raw.alarm_active ORDER BY raised_at DESC LIMIT 20")
rows = cur.fetchall()
print(f"Total active alarms: {len(rows)}")
for r in rows:
    print(r)

print("\n=== HISTORIAN_EVENTS (recent alarm events) ===")
cur.execute("""
    SELECT tag_id, event_type, alarm_level, value_at_event, setpoint_value, event_ts
    FROM historian_raw.historian_events
    WHERE event_type IN ('ALARM_RAISED','ALARM_RTN','ALARM_ACK')
    ORDER BY event_ts DESC LIMIT 20
""")
rows = cur.fetchall()
print(f"Total alarm events: {len(rows)}")
for r in rows:
    print(r)

c.close()
