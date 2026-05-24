import psycopg2

conn = psycopg2.connect(
    host='192.168.0.120',
    port=5432,
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)

cur = conn.cursor()

# Check distinct server_progid values
cur.execute("""
    SELECT server_progid, COUNT(*) as count
    FROM historian_meta.tag_master 
    GROUP BY server_progid 
    ORDER BY server_progid
""")

print("\nserver_progid distribution:")
print("-" * 60)
for row in cur.fetchall():
    print(f"{row[0]:40} | {row[1]}")

# Show sample OPC tags (non-PLC)
print("\n\nSample OPC tags (non-Rockwell):")
print("-" * 60)
cur.execute("""
    SELECT tag_id, server_progid 
    FROM historian_meta.tag_master 
    WHERE server_progid NOT LIKE 'Rockwel%'
    LIMIT 10
""")
for row in cur.fetchall():
    print(f"{row[0]:40} | {row[1]}")

# Show sample PLC tags
print("\n\nSample PLC tags (Rockwell):")
print("-" * 60)
cur.execute("""
    SELECT tag_id, server_progid, plc_protocol
    FROM historian_meta.tag_master 
    WHERE server_progid LIKE 'Rockwel%'
    LIMIT 10
""")
for row in cur.fetchall():
    print(f"{row[0]:40} | {row[1]:30} | {row[2]}")

conn.close()
