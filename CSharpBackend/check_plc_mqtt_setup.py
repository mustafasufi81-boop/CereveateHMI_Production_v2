import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(host='localhost', port=5432, database='Cereveate', user='cereveate', password='cereveate@222')
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=== MQTT/Topic related tables ===")
cur.execute("""
    SELECT table_schema, table_name 
    FROM information_schema.tables 
    WHERE table_name ILIKE '%mqtt%' OR table_name ILIKE '%topic%'
    ORDER BY table_schema, table_name
""")
for r in cur.fetchall():
    print(r)

print("\n=== historian_raw tables ===")
cur.execute("""
    SELECT table_name FROM information_schema.tables WHERE table_schema='historian_raw' ORDER BY table_name
""")
for r in cur.fetchall():
    print(r)

print("\n=== historian_meta tables ===")
cur.execute("""
    SELECT table_name FROM information_schema.tables WHERE table_schema='historian_meta' ORDER BY table_name
""")
for r in cur.fetchall():
    print(r)

print("\n=== tag_master sample (server_progid) ===")
try:
    cur.execute("""
        SELECT tag_id, tag_name, server_progid, enabled 
        FROM historian_meta.tag_master 
        ORDER BY tag_id LIMIT 30
    """)
    for r in cur.fetchall():
        print(r)
except Exception as e:
    print(f"ERROR: {e}")

print("\n=== mqtt_topic_config ===")
try:
    cur.execute("SELECT * FROM historian_raw.mqtt_topic_config ORDER BY topic_name")
    for r in cur.fetchall():
        print(r)
except Exception as e:
    print(f"ERROR: {e}")

conn.close()
