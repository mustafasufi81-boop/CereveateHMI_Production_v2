import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, database='Cereveate', user='cereveate', password='cereveate@222')
conn.autocommit = True
cur = conn.cursor()

# Fix: actual published topic is plc/plc/all (PublishWithSamplesAsync hardcodes this)
cur.execute("UPDATE historian_raw.mqtt_topic_config SET topic_name='plc/plc/all', updated_at=NOW() WHERE topic_name='plc/all'")
print(f"Updated rows: {cur.rowcount}")

cur.execute("SELECT topic_id, topic_name, plc_name, is_active FROM historian_raw.mqtt_topic_config ORDER BY topic_id")
for r in cur.fetchall():
    print(r)
conn.close()
print("Done")
