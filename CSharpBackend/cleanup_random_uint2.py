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
print("CLEANUP DUPLICATES FOR Random.UInt2")
print("="*80)

# Get count before
cur.execute("SELECT COUNT(*) FROM historian_raw.historian_timeseries WHERE tag_id = 'Random.UInt2'")
before_count = cur.fetchone()[0]
print(f"\nRows before cleanup: {before_count}")

# Delete duplicates (keep first occurrence per second per value)
print("\nDeleting duplicates (keeping first occurrence per second per value)...")

delete_query = """
DELETE FROM historian_raw.historian_timeseries
WHERE ctid IN (
    SELECT ctid
    FROM (
        SELECT 
            ctid,
            ROW_NUMBER() OVER (
                PARTITION BY tag_id, DATE_TRUNC('second', time), value_num, value_bool, value_text
                ORDER BY time ASC
            ) as row_num
        FROM historian_raw.historian_timeseries
        WHERE tag_id = 'Random.UInt2'
    ) sub
    WHERE row_num > 1
);
"""

cur.execute(delete_query)
deleted_count = cur.rowcount

# Commit transaction
conn.commit()

# Get count after
cur.execute("SELECT COUNT(*) FROM historian_raw.historian_timeseries WHERE tag_id = 'Random.UInt2'")
after_count = cur.fetchone()[0]

print(f"\nDeleted rows: {deleted_count}")
print(f"Rows after cleanup: {after_count}")
print(f"Space saved: {(deleted_count/before_count*100):.1f}%")

# Verify no duplicates remain
print("\nVerifying cleanup...")
cur.execute("""
SELECT COUNT(*)
FROM (
    SELECT 
        DATE_TRUNC('second', time) as second_bucket,
        value_num,
        COUNT(*) as cnt
    FROM historian_raw.historian_timeseries
    WHERE tag_id = 'Random.UInt2'
    GROUP BY second_bucket, value_num
    HAVING COUNT(*) > 1
) dup;
""")
remaining_dups = cur.fetchone()[0]

if remaining_dups == 0:
    print("✅ SUCCESS: No duplicates remaining!")
else:
    print(f"⚠️ WARNING: {remaining_dups} duplicate groups still exist")

cur.close()
conn.close()

print("\n" + "="*80)
print("Cleanup complete for Random.UInt2")
print("="*80)
