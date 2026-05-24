import psycopg2
from datetime import datetime

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

conn.autocommit = False
cur = conn.cursor()

print("\n" + "="*80)
print("FAST CLEANUP - Using Temp Table Approach")
print("="*80)

try:
    # Get count before
    cur.execute("SELECT COUNT(*) FROM historian_raw.historian_timeseries WHERE tag_id = 'Random.UInt2'")
    before_count = cur.fetchone()[0]
    print(f"\nRows before cleanup: {before_count}")

    # Step 1: Create temp table with deduplicated data (keep first occurrence)
    print("\nStep 1: Creating temp table with unique rows...")
    cur.execute("""
    CREATE TEMP TABLE temp_unique_rows AS
    SELECT DISTINCT ON (tag_id, DATE_TRUNC('second', time), COALESCE(value_num, -999999))
        time, tag_id, value_num, value_text, value_bool, quality, 
        sample_source, mapping_version, opc_timestamp
    FROM historian_raw.historian_timeseries
    WHERE tag_id = 'Random.UInt2'
    ORDER BY tag_id, DATE_TRUNC('second', time), COALESCE(value_num, -999999), time ASC;
    """)
    
    cur.execute("SELECT COUNT(*) FROM temp_unique_rows")
    unique_count = cur.fetchone()[0]
    print(f"✅ Created temp table with {unique_count} unique rows")

    # Step 2: Delete all rows for this tag
    print("\nStep 2: Deleting all rows for Random.UInt2...")
    cur.execute("DELETE FROM historian_raw.historian_timeseries WHERE tag_id = 'Random.UInt2'")
    deleted = cur.rowcount
    print(f"✅ Deleted {deleted} rows")

    # Step 3: Insert deduplicated data back
    print("\nStep 3: Inserting deduplicated data back...")
    cur.execute("""
    INSERT INTO historian_raw.historian_timeseries 
        (time, tag_id, value_num, value_text, value_bool, quality, 
         sample_source, mapping_version, opc_timestamp)
    SELECT time, tag_id, value_num, value_text, value_bool, quality, 
           sample_source, mapping_version, opc_timestamp
    FROM temp_unique_rows;
    """)
    inserted = cur.rowcount
    print(f"✅ Inserted {inserted} deduplicated rows")

    # Commit transaction
    print("\nCommitting transaction...")
    conn.commit()
    
    # Verify
    cur.execute("SELECT COUNT(*) FROM historian_raw.historian_timeseries WHERE tag_id = 'Random.UInt2'")
    after_count = cur.fetchone()[0]
    
    print("\n" + "="*80)
    print("CLEANUP COMPLETE!")
    print("="*80)
    print(f"Before: {before_count:,} rows")
    print(f"After:  {after_count:,} rows")
    print(f"Deleted: {before_count - after_count:,} duplicates ({(before_count - after_count)/before_count*100:.1f}%)")
    print("\n✅ SUCCESS!")

except Exception as e:
    print(f"\n❌ ERROR: {e}")
    print("Rolling back...")
    conn.rollback()
    
finally:
    cur.close()
    conn.close()
