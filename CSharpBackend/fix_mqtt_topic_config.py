"""
Fix PLC → MQTT → HMI data flow:
1. Create historian_raw.mqtt_topic_config table
2. Insert topic mapping: plc/all → Rockwel_PLC_001
"""
import psycopg2

conn = psycopg2.connect(
    host='localhost', port=5432, database='Cereveate',
    user='cereveate', password='cereveate@222'
)
conn.autocommit = True
cur = conn.cursor()

# 1. Create mqtt_topic_config table
print("=== Creating historian_raw.mqtt_topic_config table ===")
cur.execute("""
    CREATE TABLE IF NOT EXISTS historian_raw.mqtt_topic_config (
        topic_id        SERIAL PRIMARY KEY,
        topic_name      VARCHAR(255) NOT NULL UNIQUE,
        plc_name        VARCHAR(255) NOT NULL,
        qos             INTEGER NOT NULL DEFAULT 1,
        is_active       BOOLEAN NOT NULL DEFAULT TRUE,
        thread_group    VARCHAR(100) DEFAULT 'default',
        description     TEXT,
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        updated_at      TIMESTAMPTZ DEFAULT NOW()
    )
""")
print("  Table created (or already exists)")

# 2. Insert topic mappings
# C# gateway publishes ALL tags to topic 'plc/all' (Bulk mode, TopicPrefix = "")
# plc_name must match server_progid in tag_master
topics = [
    ('plc/all',               'Rockwel_PLC_001', 1, True,  'default', 'Rockwell PLC bulk publish topic'),
    ('plc/Rockwel_PLC_001/bulk', 'Rockwel_PLC_001', 1, True, 'default', 'Rockwell PLC per-PLC fallback topic'),
    ('plc/health',            'Rockwel_PLC_001', 1, False, 'health',  'Health status topic (monitoring only)'),
]

print("\n=== Inserting topic mappings ===")
for topic_name, plc_name, qos, is_active, thread_group, description in topics:
    cur.execute("""
        INSERT INTO historian_raw.mqtt_topic_config 
            (topic_name, plc_name, qos, is_active, thread_group, description)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (topic_name) DO UPDATE SET
            plc_name     = EXCLUDED.plc_name,
            qos          = EXCLUDED.qos,
            is_active    = EXCLUDED.is_active,
            thread_group = EXCLUDED.thread_group,
            description  = EXCLUDED.description,
            updated_at   = NOW()
    """, (topic_name, plc_name, qos, is_active, thread_group, description))
    print(f"  {'[ACTIVE]' if is_active else '[inactive]'} {topic_name!s:40s} → plc_name={plc_name}")

# 3. Verify
print("\n=== Verification: mqtt_topic_config ===")
cur.execute("SELECT topic_id, topic_name, plc_name, qos, is_active, thread_group FROM historian_raw.mqtt_topic_config ORDER BY topic_id")
for row in cur.fetchall():
    print(f"  {row}")

# 4. Count how many tags will be matched per plc_name
print("\n=== Tags matched per plc_name (from tag_master, enabled=true) ===")
cur.execute("""
    SELECT server_progid, COUNT(*) as tag_count
    FROM historian_meta.tag_master
    WHERE enabled = true AND server_progid IS NOT NULL
    GROUP BY server_progid
    ORDER BY server_progid
""")
for row in cur.fetchall():
    progid, count = row
    print(f"  server_progid={progid!s:30s} → {count} tags")

print("\n  NOTE: Only 'Rockwel_PLC_001' tags will flow through MQTT (plc/all topic)")
print("  Tags with server_progid='PLC_GATEWAY_01' / 'PLC_SENSORS_01' need separate PLC connections")

conn.close()
print("\nDone!")
