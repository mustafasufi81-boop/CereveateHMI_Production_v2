import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()
cur.execute("""
    SELECT event_id, tag_id, event_type, alarm_state, alarm_actual_value
    FROM historian_raw.historian_events
    WHERE event_id >= 32654
    ORDER BY event_id
""")
for r in cur.fetchall():
    print(r)
print("\n--- Count by alarm_state for Random.Real4 ---")
cur.execute("""
    SELECT alarm_state, count(*) 
    FROM historian_raw.historian_events 
    WHERE tag_id = 'Random.Real4' 
    GROUP BY alarm_state
""")
for r in cur.fetchall():
    print(r)
conn.close()
