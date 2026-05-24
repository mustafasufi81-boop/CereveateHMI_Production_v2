import psycopg2

conn = psycopg2.connect(
    host='localhost', 
    port=5432, 
    database='Cereveate', 
    user='cereveate', 
    password='cereveate@222'
)

cur = conn.cursor()
cur.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_schema='historian_raw' 
    AND table_name='historian_timeseries' 
    ORDER BY ordinal_position
""")

print("Columns in historian_raw.historian_timeseries:")
print("-" * 50)
for row in cur.fetchall():
    print(f"  - {row[0]}")

conn.close()
