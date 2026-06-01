import psycopg2
c = psycopg2.connect(host='localhost', port=5432, database='Automation_DB',
                     user='cereveate', password='cereveate@222')
cur = c.cursor()

print("=== tag_master ===")
cur.execute("""SELECT tag_id, tag_name, alarm_enabled, alarm_h_limit
               FROM historian_meta.tag_master WHERE tag_id='CV1101B_AUTO'""")
print(cur.fetchone())

print("\n=== alarm_active (live) ===")
cur.execute("""SELECT alarm_key, tag_id, level, alarm_state, raised_value, raised_at
               FROM historian_raw.alarm_active WHERE tag_id='CV1101B_AUTO'
               ORDER BY raised_at DESC""")
for r in cur.fetchall():
    print(r)

print("\n=== last 5 historian_events for this tag ===")
cur.execute("""SELECT event_id, event_type, alarm_state, time, alarm_actual_value
               FROM historian_raw.historian_events
               WHERE tag_id='CV1101B_AUTO' AND event_type LIKE 'ALARM%'
               ORDER BY time DESC LIMIT 5""")
for r in cur.fetchall():
    print(r)
c.close()
