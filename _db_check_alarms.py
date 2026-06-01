import psycopg2
conn = psycopg2.connect(dbname='Automation_DB', user='cereveate', password='cereveate@222', host='localhost')
cur = conn.cursor()

print("=== STEP 1: Latest alarm events in historian_events ===")
cur.execute("""
    SELECT event_id, tag_id, event_type, alarm_state, time, alarm_actual_value, alarm_setpoint
    FROM historian_raw.historian_events
    WHERE event_type LIKE 'ALARM%'
    ORDER BY time DESC LIMIT 10
""")
rows = cur.fetchall()
for r in rows:
    print(f"  event_id={r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]}")

print("\n=== STEP 2: alarm_active table ===")
cur.execute("SELECT alarm_key, tag_id, level, alarm_state, current_event_id, raised_at FROM historian_raw.alarm_active ORDER BY raised_at DESC LIMIT 10")
rows = cur.fetchall()
print(f"Total active: {len(rows)}")
for r in rows:
    print(f"  {r[0]} | state={r[2]} | event_id={r[4]} | raised={r[5]}")

print("\n=== STEP 3: OPC tag values in TagValuesPool (via MQTT/cache check) ===")
cur.execute("""
    SELECT tag_id, alarm_hh_limit, alarm_h_limit
    FROM historian_meta.tag_master 
    WHERE alarm_enabled=true AND alarm_h_limit IS NOT NULL
    LIMIT 5
""")
for r in cur.fetchall():
    print(f"  tag={r[0]}, HH={r[1]}, H={r[2]}")

conn.close()
