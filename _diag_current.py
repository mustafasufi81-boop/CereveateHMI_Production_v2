import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, database='Automation_DB',
                        user='cereveate', password='cereveate@222')
cur = conn.cursor()

print("=== CURRENT ACTIVE ALARMS (alarm_active table) ===")
cur.execute("""
    SELECT tag_id, level, alarm_state, setpoint_value, raised_value, raised_at
    FROM historian_raw.alarm_active
    WHERE alarm_state IN ('ACTIVE_UNACK','ACTIVE_ACK','RTN_UNACK')
    ORDER BY raised_at DESC
    LIMIT 20
""")
rows = cur.fetchall()
print(f"Total: {len(rows)}")
for r in rows:
    print(f"  {r[0]:<16} {r[1]:<10} {r[2]:<15} SP={r[3]}  PV@trip={r[4]}  raised={r[5]}")

print("\n=== AY1101 specifically (any state) ===")
cur.execute("""
    SELECT tag_id, level, alarm_state, setpoint_value, raised_value, raised_at
    FROM historian_raw.alarm_active
    WHERE tag_id ILIKE '%AY1101%'
""")
for r in cur.fetchall():
    print(f"  {r}")

print("\n=== LAST 5 AY1101 events in historian ===")
cur.execute("""
    SELECT tag_id, event_type, alarm_state, alarm_actual_value, alarm_setpoint, time
    FROM historian_raw.historian_events
    WHERE tag_id ILIKE '%AY1101%'
    ORDER BY time DESC LIMIT 5
""")
for r in cur.fetchall():
    print(f"  {r}")

cur.close(); conn.close()
