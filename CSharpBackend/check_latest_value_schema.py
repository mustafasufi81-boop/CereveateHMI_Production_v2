import psycopg2

conn = psycopg2.connect(host='localhost', database='Cereveate', user='cereveate', password='cereveate@222')
cur = conn.cursor()

print("\n=== historian_latest_value columns ===")
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema='historian_raw' AND table_name='historian_latest_value' 
    ORDER BY ordinal_position
""")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

cur.close()
conn.close()
