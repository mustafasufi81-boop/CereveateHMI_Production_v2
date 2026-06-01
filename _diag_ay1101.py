import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, database='Automation_DB',
                        user='cereveate', password='cereveate@222')
cur = conn.cursor()

print("== TAG MASTER (AY1101) ==")
cur.execute("""
    SELECT tag_id, tag_name, enabled, data_type
    FROM historian_meta.tag_master
    WHERE tag_name ILIKE '%AY1101%' OR tag_id::text ILIKE '%AY1101%'
""")
for r in cur.fetchall():
    print(r)

print("\n== ACTIVE ALARMS (AY1101) ==")
cur.execute("""
    SELECT alarm_key, tag_id, alarm_state, setpoint_value, raised_value
    FROM historian_raw.alarm_active
    WHERE tag_id::text ILIKE '%AY1101%'
""")
for r in cur.fetchall():
    print(r)

print("\n== LATEST VALUE (AY1101) ==")
cur.execute("""
    SELECT lv.tag_id, lv.last_value_num, lv.last_quality, lv.last_time
    FROM historian_raw.historian_latest_value lv
    WHERE lv.tag_id IN (SELECT tag_id FROM historian_meta.tag_master WHERE tag_name ILIKE '%AY1101%' OR tag_id::text ILIKE '%AY1101%')
""")
for r in cur.fetchall():
    print(r)

cur.close()
conn.close()
