import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()

print('--- mqtt_topic_config (active topics) ---')
cur.execute('SELECT topic_name, plc_name, is_active FROM historian_raw.mqtt_topic_config ORDER BY topic_name')
for r in cur.fetchall():
    print(r)

print()
print('--- TY1101A in tag_master ---')
cur.execute("SELECT tag_id, server_progid, enabled FROM historian_meta.tag_master WHERE tag_id='TY1101A'")
for r in cur.fetchall():
    print(r)

conn.close()
