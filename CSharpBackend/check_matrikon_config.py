import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()

print("=" * 90)
print("tag_master alarm/interlock config for Matrikon OPC tags")
print("=" * 90)

cur.execute("""
SELECT 
    tag_id,
    enabled,
    alarm_enabled,
    alarm_hh_limit,
    alarm_h_limit,
    alarm_l_limit,
    alarm_ll_limit,
    alarm_deadband,
    alarm_priority,
    interlock_type,
    deadband_value,
    associated_equipment
FROM historian_meta.tag_master
WHERE tag_id IN ('Random.Real4', 'Triangle Waves.Real4', 'Bucket Brigade.Real4')
ORDER BY tag_id
""")

cols = [d[0] for d in cur.description]
rows = cur.fetchall()
print(f"Rows found: {len(rows)}\n")
for row in rows:
    print("-" * 60)
    for col, val in zip(cols, row):
        print(f"  {col:<30} = {val}")

# Also show the CURRENT OPC value for these tags from historian_timeseries
print("\n" + "=" * 90)
print("Latest values in historian_timeseries (last 1 minute)")
print("=" * 90)
# Discover actual column names first
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='historian_raw' AND table_name='historian_timeseries' ORDER BY ordinal_position LIMIT 15")
print("historian_timeseries columns:", [r[0] for r in cur.fetchall()])

cur.execute("""
SELECT DISTINCT ON (tag_id) tag_id, value_num, quality, time
FROM historian_raw.historian_timeseries
WHERE tag_id IN ('Random.Real4', 'Triangle Waves.Real4', 'Bucket Brigade.Real4')
ORDER BY tag_id, time DESC
""")
rows2 = cur.fetchall()
print(f"\nLatest stored values ({len(rows2)} tags):")
for r in rows2:
    print(f"  tag={r[0]:<30} value={r[1]:<12} quality={r[2]}  ts={r[3]}")

conn.close()
