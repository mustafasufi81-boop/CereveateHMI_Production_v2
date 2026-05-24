import psycopg2
c = psycopg2.connect(dbname='Automation_DB', user='cereveate', password='cereveate@222', host='localhost')
cur = c.cursor()

# Get real column names
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='historian_raw' AND table_name='historian_events' ORDER BY ordinal_position")
print("historian_events columns:", [r[0] for r in cur.fetchall()])

print("\n=== ALARM_ACTIVE ===")
cur.execute("SELECT COUNT(*) FROM historian_raw.alarm_active")
print("alarm_active count:", cur.fetchone())

print("\n=== RECENT historian_events ===")
cur.execute("SELECT * FROM historian_raw.historian_events ORDER BY occurred_at DESC LIMIT 10")
rows = cur.fetchall()
print(f"rows: {len(rows)}")
for r in rows:
    print(r)

c.close()
