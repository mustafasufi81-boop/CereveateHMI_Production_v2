import psycopg2
conn = psycopg2.connect(dbname='Automation_DB', user='cereveate', password='cereveate@222', host='localhost')
cur = conn.cursor()
cur.execute("SELECT COUNT(*), MAX(time)::text FROM historian_raw.historian_events WHERE time > NOW() - INTERVAL '2 minutes'")
r = cur.fetchone()
print(f'New events in last 2 min: count={r[0]}, latest={r[1]}')
cur.execute("SELECT COUNT(*) FROM historian_raw.alarm_active")
print(f'alarm_active rows: {cur.fetchone()[0]}')
cur.execute("SELECT event_type, tag_id, time FROM historian_raw.historian_events ORDER BY time DESC LIMIT 3")
for r in cur.fetchall():
    print(f'  Latest: {r[0]} | {r[1]} | {r[2]}')
conn.close()
