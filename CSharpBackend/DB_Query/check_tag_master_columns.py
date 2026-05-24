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
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = 'historian_meta'
    AND table_name = 'tag_master'
    ORDER BY ordinal_position
""")

print("📋 Columns in historian_meta.tag_master:")
for col in cur.fetchall():
    print(f"  • {col[0]} ({col[1]})")

cur.close()
conn.close()
