import psycopg2
conn = psycopg2.connect(host='localhost', dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()

cur.execute('SELECT topic_id, topic_name, plc_name, is_active FROM historian_raw.mqtt_topic_config WHERE is_active=true')
print('Active topics:', cur.fetchall())

cur.execute("""
    SELECT tag_id, server_progid, plant, area, equipment, sub_equipment
    FROM historian_meta.tag_master
    WHERE tag_id IN ('TY1101A','PY1101A','PY1101B','PY1103A','PY1103B')
    ORDER BY tag_id
""")
print('\nTags:')
for r in cur.fetchall():
    print(r)

conn.close()
