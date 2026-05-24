import psycopg2
conn = psycopg2.connect(dbname='Automation_DB', user='cereveate', password='cereveate@222', host='localhost', port=5432)
cur = conn.cursor()

# Check alarm_active - is raised_value truly frozen or updating?
cur.execute("""
SELECT alarm_key, tag_id, alarm_state, raised_value, setpoint_value, raised_at, updated_at
FROM historian_raw.alarm_active
ORDER BY updated_at DESC LIMIT 10
""")
cols = [d[0] for d in cur.description]
rows = cur.fetchall()
print("=== alarm_active current rows ===")
for r in rows:
    print(dict(zip(cols, r)))

# Check historian_events - does the same alarm_key have multiple rows with different values?
cur.execute("""
SELECT tag_id, alarm_level, alarm_state, alarm_actual_value, alarm_setpoint, time
FROM historian_raw.historian_events
WHERE tag_id IN (SELECT tag_id FROM historian_raw.alarm_active)
ORDER BY time DESC LIMIT 20
""")
cols2 = [d[0] for d in cur.description]
rows2 = cur.fetchall()
print("\n=== historian_events for active tags ===")
for r in rows2:
    print(dict(zip(cols2, r)))

conn.close()
