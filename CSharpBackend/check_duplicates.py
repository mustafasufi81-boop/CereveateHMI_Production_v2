import psycopg2
from datetime import datetime

# Connect to database
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

print("\n" + "="*80)
print("DUPLICATE CHECK FOR Random.UInt2")
print("="*80)

# Check for duplicates in same second
query = """
SELECT 
    DATE_TRUNC('second', time) as second_bucket,
    value_num,
    COUNT(*) as duplicate_count,
    ARRAY_AGG(time ORDER BY time) as all_times
FROM historian_raw.historian_timeseries
WHERE tag_id = 'Random.UInt2'
GROUP BY second_bucket, value_num
HAVING COUNT(*) > 1
ORDER BY second_bucket DESC
LIMIT 10;
"""

cur.execute(query)
duplicates = cur.fetchall()

print(f"\nFound {len(duplicates)} groups of duplicates:\n")

for row in duplicates:
    second, value, count, times = row
    print(f"Second: {second}")
    print(f"  Value: {value}")
    print(f"  Duplicate count: {count}")
    print(f"  Timestamps: {', '.join([t.strftime('%H:%M:%S.%f')[:-3] for t in times])}")
    print()

# Summary statistics
print("\n" + "="*80)
print("SUMMARY STATISTICS")
print("="*80)

cur.execute("""
SELECT COUNT(*) as total_rows
FROM historian_raw.historian_timeseries
WHERE tag_id = 'Random.UInt2'
""")
total = cur.fetchone()[0]
print(f"Total rows for Random.UInt2: {total}")

cur.execute("""
SELECT COUNT(*) as duplicate_rows
FROM (
    SELECT 
        ROW_NUMBER() OVER (
            PARTITION BY DATE_TRUNC('second', time), value_num 
            ORDER BY time ASC
        ) as row_num
    FROM historian_raw.historian_timeseries
    WHERE tag_id = 'Random.UInt2'
) sub
WHERE row_num > 1;
""")
duplicate_count = cur.fetchone()[0]
print(f"Duplicate rows to be deleted: {duplicate_count}")
print(f"Rows after cleanup: {total - duplicate_count}")
print(f"Space savings: {(duplicate_count/total*100):.1f}%")

cur.close()
conn.close()

print("\n" + "="*80)
print("Next step: Run cleanup script if duplicates found")
print("="*80)
