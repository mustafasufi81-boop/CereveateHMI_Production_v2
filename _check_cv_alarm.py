import psycopg2
c = psycopg2.connect(host='localhost', port=5432, database='Automation_DB',
                     user='cereveate', password='cereveate@222')
cur = c.cursor()
cur.execute("""
    SELECT alarm_key, tag_id, level, alarm_state, raised_value, raised_at
    FROM historian_raw.alarm_active WHERE tag_id='CV1101B_AUTO'
""")
rows = cur.fetchall()
print(f"Active alarms for CV1101B_AUTO: {len(rows)}")
for r in rows:
    print(f"  {r}")

cur.execute("""
    SELECT event_id, event_type, alarm_state, time, alarm_actual_value, alarm_setpoint
    FROM historian_raw.historian_events
    WHERE tag_id='CV1101B_AUTO' AND event_type LIKE 'ALARM%'
    ORDER BY time DESC LIMIT 5
""")
print("\nRecent alarm events for CV1101B_AUTO:")
for r in cur.fetchall():
    print(f"  {r}")
c.close()
