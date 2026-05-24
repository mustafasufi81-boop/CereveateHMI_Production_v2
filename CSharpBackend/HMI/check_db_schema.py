import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)
cur = conn.cursor()

print("=== Checking historian_raw.historian_timeseries ===\n")
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema='historian_raw' AND table_name='historian_timeseries' 
    ORDER BY ordinal_position
""")

rows = cur.fetchall()
if rows:
    print("Columns found:")
    for row in rows:
        print(f"  {row[0]}: {row[1]}")
else:
    print("Table not found or no columns")

print("\n=== Sample data from historian_raw.historian_timeseries ===\n")
try:
    cur.execute("""
        SELECT * FROM historian_raw.historian_timeseries 
        LIMIT 1
    """)
    row = cur.fetchone()
    if row:
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema='historian_raw' AND table_name='historian_timeseries' 
            ORDER BY ordinal_position
        """)
        columns = [r[0] for r in cur.fetchall()]
        print("Sample row:")
        for col, val in zip(columns, row):
            print(f"  {col} = {val}")
    else:
        print("No data in table")
except Exception as e:
    print(f"Error: {e}")

cur.close()
conn.close()
