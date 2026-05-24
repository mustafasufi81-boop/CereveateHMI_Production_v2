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
    WHERE table_schema = 'historian_raw' 
    AND table_name = 'historian_timeseries'
    ORDER BY ordinal_position
""")

cols = cur.fetchall()

print("📋 Columns in historian_raw.historian_timeseries:\n")
for name, dtype in cols:
    print(f"  • {name} ({dtype})")

# Get sample data
print("\n📊 Sample data (first 3 records):\n")
cur.execute("SELECT * FROM historian_raw.historian_timeseries LIMIT 3")
rows = cur.fetchall()
for row in rows:
    print(f"  {row}")

conn.close()
