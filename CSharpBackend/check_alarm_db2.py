import psycopg2

c = psycopg2.connect(dbname='Automation_DB', user='cereveate', password='cereveate@222', host='localhost')
cur = c.cursor()

print("=== ALARM-ENABLED TAGS + LAST VALUE IN HISTORIAN ===")
cur.execute("""
    SELECT tm.tag_id, tm.alarm_h_limit, tm.alarm_l_limit,
           ht.value, ht.ts,
           CASE WHEN ht.value IS NOT NULL THEN 'HAS DATA' ELSE 'NO DATA IN DB' END as status
    FROM historian_meta.tag_master tm
    LEFT JOIN LATERAL (
        SELECT value::text, ts FROM historian_raw.historian_timeseries
        WHERE tag_id = tm.tag_id ORDER BY ts DESC LIMIT 1
    ) ht ON true
    WHERE tm.alarm_enabled = true
    ORDER BY status, tm.tag_id
    LIMIT 40
""")
for r in cur.fetchall():
    print(r)

print("\n=== ALARM ENABLED TAGS WITH DATA vs WITHOUT ===")
cur.execute("""
    SELECT 
        COUNT(*) FILTER (WHERE ht.value IS NOT NULL) as with_data,
        COUNT(*) FILTER (WHERE ht.value IS NULL) as without_data
    FROM historian_meta.tag_master tm
    LEFT JOIN LATERAL (
        SELECT value FROM historian_raw.historian_timeseries
        WHERE tag_id = tm.tag_id ORDER BY ts DESC LIMIT 1
    ) ht ON true
    WHERE tm.alarm_enabled = true
""")
print(cur.fetchone())

print("\n=== WHAT TAGS ARE IN HISTORIAN_TIMESERIES (sample) ===")
cur.execute("SELECT DISTINCT tag_id FROM historian_raw.historian_timeseries ORDER BY tag_id LIMIT 30")
for r in cur.fetchall():
    print(r[0])

print("\n=== alarm_active schema ===")
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='historian_raw' AND table_name='alarm_active' ORDER BY ordinal_position")
for r in cur.fetchall():
    print(r)

c.close()
