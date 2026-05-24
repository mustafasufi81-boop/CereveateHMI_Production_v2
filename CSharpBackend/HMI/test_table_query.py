import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)
cur = conn.cursor()

print("=== Testing historian_raw.historian_timeseries table ===\n")

# Get total row count
cur.execute("SELECT COUNT(*) FROM historian_raw.historian_timeseries")
total_rows = cur.fetchone()[0]
print(f"Total rows in table: {total_rows:,}\n")

# Get all column names
cur.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_schema='historian_raw' AND table_name='historian_timeseries' 
    ORDER BY ordinal_position
""")
columns = [row[0] for row in cur.fetchall()]
print(f"Columns: {', '.join(columns)}\n")

# Get sample data
print("=== Sample data (5 rows) ===\n")
cur.execute("""
    SELECT time, tag_id, value_num, quality, opc_timestamp 
    FROM historian_raw.historian_timeseries 
    ORDER BY time DESC 
    LIMIT 5
""")

for row in cur.fetchall():
    print(f"Time: {row[0]}")
    print(f"Tag ID: {row[1]}")
    print(f"Value: {row[2]}")
    print(f"Quality: {row[3]}")
    print(f"OPC Timestamp: {row[4]}")
    print("-" * 60)

# Get unique tags
print("\n=== Unique tags in table ===\n")
cur.execute("""
    SELECT tag_id, COUNT(*) as count, MIN(time) as first, MAX(time) as last
    FROM historian_raw.historian_timeseries 
    GROUP BY tag_id 
    ORDER BY count DESC 
    LIMIT 10
""")

for row in cur.fetchall():
    print(f"Tag: {row[0]:<30} | Count: {row[1]:>10,} | First: {row[2]} | Last: {row[3]}")

# Test a specific query with date range
print("\n=== Testing query with date range (last 24 hours) ===\n")
cur.execute("""
    SELECT COUNT(*), MIN(time), MAX(time)
    FROM historian_raw.historian_timeseries 
    WHERE time >= NOW() - INTERVAL '24 hours'
""")
row = cur.fetchone()
print(f"Rows in last 24 hours: {row[0]:,}")
print(f"Earliest: {row[1]}")
print(f"Latest: {row[2]}")

# Test query for a specific tag
print("\n=== Testing query for @ClientCount tag (last 100 rows) ===\n")
cur.execute("""
    SELECT opc_timestamp, value_num, quality
    FROM historian_raw.historian_timeseries 
    WHERE tag_id = '@ClientCount'
    ORDER BY opc_timestamp DESC
    LIMIT 100
""")

rows = cur.fetchall()
print(f"Found {len(rows)} rows for @ClientCount")
if rows:
    print("\nFirst 5 values:")
    for i, row in enumerate(rows[:5]):
        print(f"  {i+1}. Time: {row[0]} | Value: {row[1]} | Quality: {row[2]}")

cur.close()
conn.close()

print("\n✅ Table is working correctly!")
