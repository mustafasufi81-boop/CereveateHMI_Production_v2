import psycopg2

c = psycopg2.connect(dbname='Automation_DB', user='cereveate', password='cereveate@222', host='localhost')
cur = c.cursor()

print("=== ALARM ENABLED TAGS ===")
cur.execute("SELECT tag_id, alarm_enabled, alarm_h_limit, alarm_l_limit, alarm_hh_limit, alarm_ll_limit FROM historian_meta.tag_master WHERE alarm_enabled=true LIMIT 20")
rows = cur.fetchall()
for r in rows:
    print(r)
print("COUNT:", len(rows))

print("\n=== TOTAL TAGS WITH alarm_enabled column ===")
cur.execute("SELECT COUNT(*) FROM historian_meta.tag_master WHERE alarm_enabled IS NOT NULL")
print(cur.fetchone())

print("\n=== ALARM ACTIVE TABLE ===")
cur.execute("SELECT COUNT(*) FROM historian_raw.alarm_active")
print("alarm_active rows:", cur.fetchone())

print("\n=== RECENT ALARM EVENTS ===")
try:
    cur.execute("SELECT * FROM historian_raw.historian_events WHERE event_type LIKE '%ALARM%' ORDER BY event_time DESC LIMIT 10")
    rows = cur.fetchall()
    print("Recent alarm events:", len(rows))
    for r in rows:
        print(r)
except Exception as e:
    print("historian_events error:", e)

print("\n=== ALARM_ACTIVE SCHEMA ===")
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='historian_raw' AND table_name='alarm_active'")
for r in cur.fetchall():
    print(r)

print("\n=== SAMPLE CURRENT VALUES FOR ALARM-ENABLED TAGS ===")
cur.execute("""
    SELECT tm.tag_id, tm.alarm_h_limit, tm.alarm_l_limit,
           ht.value, ht.ts
    FROM historian_meta.tag_master tm
    LEFT JOIN LATERAL (
        SELECT value, ts FROM historian_raw.historian_timeseries
        WHERE tag_id = tm.tag_id ORDER BY ts DESC LIMIT 1
    ) ht ON true
    WHERE tm.alarm_enabled = true LIMIT 10
""")
for r in cur.fetchall():
    print(r)

c.close()
