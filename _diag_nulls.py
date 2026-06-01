import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, database='Automation_DB',
                        user='cereveate', password='cereveate@222')
cur = conn.cursor()
cur.execute("""
    SELECT tag_id, level, alarm_state, setpoint_value, raised_value
    FROM historian_raw.alarm_active
    WHERE alarm_state IN ('ACTIVE_UNACK','ACTIVE_ACK','RTN_UNACK')
      AND (setpoint_value IS NULL OR raised_value IS NULL)
    ORDER BY tag_id
""")
rows = cur.fetchall()
print(f"ALARMS WITH NULL setpoint OR raised_value (value block hidden): {len(rows)}")
for r in rows:
    print(f"  tag={r[0]:<14} level={r[1]:<6} state={r[2]:<13} SP={r[3]} PV@trip={r[4]}")
cur.close(); conn.close()
