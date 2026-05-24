import psycopg2
c = psycopg2.connect(dbname='Automation_DB', user='cereveate', password='cereveate@222', host='localhost')
cur = c.cursor()

print("=== RECENT historian_events ===")
cur.execute("SELECT tag_id, event_type, alarm_level, alarm_actual_value, alarm_setpoint, time FROM historian_raw.historian_events ORDER BY time DESC LIMIT 10")
rows = cur.fetchall()
print(f"rows: {len(rows)}")
for r in rows:
    print(r)

c.close()
