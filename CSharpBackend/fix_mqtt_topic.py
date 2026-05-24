import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()

# Show full current state
print('--- Current mqtt_topic_config ---')
cur.execute('SELECT topic_id, topic_name, plc_name, is_active FROM historian_raw.mqtt_topic_config ORDER BY topic_name')
for r in cur.fetchall():
    print(r)

# Check column names
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_schema='historian_raw' AND table_name='mqtt_topic_config'
    ORDER BY ordinal_position
""")
cols = [r[0] for r in cur.fetchall()]
print('\nColumns:', cols)

# Insert plc/all mapped to Rockwel_PLC_001 if not exists
cur.execute("SELECT COUNT(*) FROM historian_raw.mqtt_topic_config WHERE topic_name='plc/all'")
exists = cur.fetchone()[0]
if exists == 0:
    cur.execute("""
        INSERT INTO historian_raw.mqtt_topic_config (topic_name, plc_name, qos, is_active)
        VALUES ('plc/all', 'Rockwel_PLC_001', 1, true)
    """)
    conn.commit()
    print('\n✅ Inserted plc/all -> Rockwel_PLC_001')
else:
    # Make sure it's active and mapped correctly
    cur.execute("""
        UPDATE historian_raw.mqtt_topic_config
        SET plc_name='Rockwel_PLC_001', is_active=true
        WHERE topic_name='plc/all'
    """)
    conn.commit()
    print('\n✅ Updated plc/all -> Rockwel_PLC_001 (already existed)')

# Verify
print('\n--- Final mqtt_topic_config ---')
cur.execute('SELECT topic_id, topic_name, plc_name, is_active FROM historian_raw.mqtt_topic_config ORDER BY topic_name')
for r in cur.fetchall():
    print(r)

conn.close()
