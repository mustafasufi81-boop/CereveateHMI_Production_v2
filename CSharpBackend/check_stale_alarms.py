import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()

# Check stale ACTIVE/ACK alarms blocking new raises
cur.execute("""
SELECT event_id, tag_id, alarm_state, alarm_priority, alarm_actual_value, time
FROM historian_raw.historian_events
WHERE alarm_state IN ('ACTIVE','ACKNOWLEDGED')
ORDER BY time DESC LIMIT 30
""")
rows = cur.fetchall()
print(f"Stale ACTIVE/ACK alarms blocking new raises: {len(rows)}")
for r in rows:
    print(f"  event_id={r[0]}  tag={r[1]}  state={r[2]}  priority={r[3]}  value={r[4]}  time={r[5]}")

# Check if the 3 Matrikon tags are among them
cur.execute("""
SELECT event_id, tag_id, alarm_state, time
FROM historian_raw.historian_events
WHERE tag_id IN ('Random.Real4', 'Triangle Waves.Real4', 'Bucket Brigade.Real4')
ORDER BY time DESC LIMIT 10
""")
rows2 = cur.fetchall()
print(f"\nMatrikon tag alarm history ({len(rows2)} rows):")
for r in rows2:
    print(f"  event_id={r[0]}  tag={r[1]}  state={r[2]}  time={r[3]}")

# Check current OPC tag values in pool via API would be best, but show tag counts
cur.execute("SELECT alarm_state, COUNT(*) FROM historian_raw.historian_events GROUP BY alarm_state ORDER BY COUNT(*) DESC")
print("\nAlarm state breakdown:")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

conn.close()
