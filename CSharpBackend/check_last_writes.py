import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

print("\n" + "="*80)
print("LAST DATA WRITTEN - Check when system stopped writing")
print("="*80)

# Check last write time per tag
cur.execute("""
SELECT 
    tag_id,
    MAX(time) as last_write,
    COUNT(*) as total_rows,
    NOW() - MAX(time) as time_since_last
FROM historian_raw.historian_timeseries
GROUP BY tag_id
ORDER BY last_write DESC
LIMIT 10;
""")

results = cur.fetchall()
print("\nLast writes per tag:")
for r in results:
    print(f"\n{r[0]}")
    print(f"  Last write: {r[1]}")
    print(f"  Total rows: {r[2]:,}")
    print(f"  Time since: {r[3]}")

# Check if specific issue with Random.UInt2
print("\n" + "="*80)
print("Random.UInt2 DETAILED CHECK")
print("="*80)

cur.execute("""
SELECT 
    COUNT(*) as total,
    MIN(time) as first,
    MAX(time) as last,
    COUNT(DISTINCT DATE_TRUNC('second', time)) as unique_seconds
FROM historian_raw.historian_timeseries
WHERE tag_id = 'Random.UInt2';
""")

result = cur.fetchone()
print(f"\nTotal rows: {result[0]:,}")
print(f"First write: {result[1]}")
print(f"Last write: {result[2]}")
print(f"Unique seconds: {result[3]:,}")
print(f"Time since last: {result[2] and (cur.execute('SELECT NOW()'), cur.fetchone()[0] - result[2])}")

cur.close()
conn.close()
