import psycopg2

conn = psycopg2.connect(
    host='192.168.0.120',
    port=5432,
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)

cur = conn.cursor()
cur.execute("""
    SELECT tag_id, tag_name, equipment 
    FROM historian_meta.tag_master 
    WHERE enabled = true 
    AND server_progid LIKE 'Rockwel%'
    ORDER BY tag_id
""")

print("\nPLC Tags:")
print("=" * 80)
for row in cur.fetchall():
    print(f"{row[0]:40} | {row[1]:30} | {row[2]}")

conn.close()
