import psycopg2
conn = psycopg2.connect(host='localhost',port=5432,database='Automation_DB',
                        user='cereveate',password='cereveate@222')
cur = conn.cursor()
print("=== AY1101 historian_events (last 6) ===")
cur.execute("""
    SELECT event_type, alarm_state, alarm_actual_value, alarm_setpoint, time
    FROM historian_raw.historian_events
    WHERE tag_id = 'AY1101'
    ORDER BY time DESC LIMIT 6
""")
for r in cur.fetchall():
    print(f"  event_type={r[0]:<25} alarm_state={r[1]:<15} val={r[2]}  sp={r[3]}  time={r[4]}")
cur.close(); conn.close()
