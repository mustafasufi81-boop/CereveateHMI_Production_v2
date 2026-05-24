import psycopg2

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    dbname='Automation_DB',
    user='cereveate',
    password='cereveate@222'
)
cur = conn.cursor()

# Check Random.Real8
cur.execute("""
    SELECT tag_id, COUNT(*), MIN(time), MAX(time)
    FROM historian_raw.historian_timeseries
    WHERE tag_id = 'Random.Real8'
    GROUP BY tag_id
""")
result = cur.fetchone()
if result:
    print(f"Tag: {result[0]}")
    print(f"Count: {result[1]}")
    print(f"First: {result[2]}")
    print(f"Last: {result[3]}")
else:
    print("No data found for Random.Real8")

# Get a sample of recent data
cur.execute("""
    SELECT time, value_num
    FROM historian_raw.historian_timeseries
    WHERE tag_id = 'Random.Real8'
    ORDER BY time DESC
    LIMIT 5
""")
print("\nRecent data samples:")
for row in cur.fetchall():
    print(f"  {row[0]} -> {row[1]}")

conn.close()
