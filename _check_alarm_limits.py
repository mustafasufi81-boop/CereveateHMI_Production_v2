import psycopg2
conn = psycopg2.connect(dbname='Automation_DB', user='cereveate', password='cereveate@222', host='localhost')
cur = conn.cursor()

# 1. Check if alarm limits are actually set
cur.execute("""
    SELECT 
        COUNT(*) as total_enabled,
        COUNT(alarm_hh_limit) as has_hh,
        COUNT(alarm_h_limit) as has_h,
        COUNT(alarm_l_limit) as has_l,
        COUNT(alarm_ll_limit) as has_ll
    FROM historian_meta.tag_master
    WHERE alarm_enabled = true
""")
r = cur.fetchone()
print(f"Alarm-enabled tags: {r[0]}")
print(f"  With HH limit: {r[1]}")
print(f"  With H limit:  {r[2]}")
print(f"  With L limit:  {r[3]}")
print(f"  With LL limit: {r[4]}")

# 2. Sample 5 tags with actual limits
cur.execute("""
    SELECT tag_id, alarm_hh_limit, alarm_h_limit, alarm_l_limit, alarm_ll_limit
    FROM historian_meta.tag_master
    WHERE alarm_enabled = true
      AND (alarm_hh_limit IS NOT NULL OR alarm_h_limit IS NOT NULL)
    LIMIT 5
""")
rows = cur.fetchall()
print("\nSample tags with limits:")
for r in rows:
    print(f"  {r[0]}: HH={r[1]}, H={r[2]}, L={r[3]}, LL={r[4]}")

# 3. Check historian_events for latest events (any time)
cur.execute("""
    SELECT event_type, COUNT(*), MAX(time)::text
    FROM historian_raw.historian_events
    WHERE time > NOW() - INTERVAL '10 minutes'
    GROUP BY event_type ORDER BY MAX(time) DESC
""")
rows = cur.fetchall()
print("\nhistorian_events last 10 min:")
if rows:
    for r in rows:
        print(f"  {r[0]}: count={r[1]}, latest={r[2]}")
else:
    print("  NONE")

# 4. Check alarm_active
cur.execute("SELECT COUNT(*), MAX(updated_at)::text FROM historian_raw.alarm_active")
r = cur.fetchone()
print(f"\nalarm_active: count={r[0]}, latest_update={r[1]}")

# 5. Check if tag_master tags match what's in OPC pool (via historian_raw)
cur.execute("""
    SELECT COUNT(DISTINCT tag_id) 
    FROM historian_raw.historian_events
    WHERE time > NOW() - INTERVAL '1 hour'
""")
print(f"\nTags with events in last hour: {cur.fetchone()[0]}")

conn.close()
