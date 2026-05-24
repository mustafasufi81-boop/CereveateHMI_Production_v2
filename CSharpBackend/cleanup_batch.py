import psycopg2
import time

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
print("BATCH DELETE APPROACH - Delete in chunks")
print("="*80)

try:
    # Get count before
    cur.execute("SELECT COUNT(*) FROM historian_raw.historian_timeseries WHERE tag_id = 'Random.UInt2'")
    before_count = cur.fetchone()[0]
    print(f"\nRows before cleanup: {before_count}")

    # Step 1: Create new table with unique rows only
    print("\nStep 1: Creating new table with deduplicated data...")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS historian_raw.historian_timeseries_clean AS
    SELECT DISTINCT ON (tag_id, DATE_TRUNC('second', time), COALESCE(value_num, -999999))
        time, tag_id, value_num, value_text, value_bool, quality, 
        sample_source, mapping_version, opc_timestamp
    FROM historian_raw.historian_timeseries
    WHERE tag_id = 'Random.UInt2'
    ORDER BY tag_id, DATE_TRUNC('second', time), COALESCE(value_num, -999999), time ASC;
    """)
    
    conn.commit()
    
    cur.execute("SELECT COUNT(*) FROM historian_raw.historian_timeseries_clean")
    clean_count = cur.fetchone()[0]
    print(f"✅ Created clean table with {clean_count:,} unique rows")

    # Step 2: Batch delete old rows
    print(f"\nStep 2: Batch deleting {before_count:,} rows in chunks of 10,000...")
    total_deleted = 0
    batch_size = 10000
    batch_num = 0
    
    while True:
        batch_num += 1
        start = time.time()
        
        cur.execute(f"""
        DELETE FROM historian_raw.historian_timeseries 
        WHERE ctid IN (
            SELECT ctid FROM historian_raw.historian_timeseries 
            WHERE tag_id = 'Random.UInt2' 
            LIMIT {batch_size}
        );
        """)
        
        deleted = cur.rowcount
        total_deleted += deleted
        
        conn.commit()
        
        elapsed = time.time() - start
        print(f"  Batch {batch_num}: Deleted {deleted:,} rows in {elapsed:.1f}s (Total: {total_deleted:,})")
        
        if deleted == 0:
            break
    
    print(f"✅ Deleted total: {total_deleted:,} rows")

    # Step 3: Insert clean data back
    print("\nStep 3: Inserting deduplicated data back...")
    cur.execute("""
    INSERT INTO historian_raw.historian_timeseries 
        (time, tag_id, value_num, value_text, value_bool, quality, 
         sample_source, mapping_version, opc_timestamp)
    SELECT time, tag_id, value_num, value_text, value_bool, quality, 
           sample_source, mapping_version, opc_timestamp
    FROM historian_raw.historian_timeseries_clean;
    """)
    inserted = cur.rowcount
    print(f"✅ Inserted {inserted:,} deduplicated rows")
    
    conn.commit()

    # Step 4: Drop temp table
    print("\nStep 4: Dropping temp table...")
    cur.execute("DROP TABLE historian_raw.historian_timeseries_clean;")
    conn.commit()
    print("✅ Temp table dropped")

    # Verify
    cur.execute("SELECT COUNT(*) FROM historian_raw.historian_timeseries WHERE tag_id = 'Random.UInt2'")
    after_count = cur.fetchone()[0]
    
    print("\n" + "="*80)
    print("CLEANUP COMPLETE!")
    print("="*80)
    print(f"Before: {before_count:,} rows")
    print(f"After:  {after_count:,} rows")
    print(f"Removed: {before_count - after_count:,} duplicates ({(before_count - after_count)/before_count*100:.1f}%)")
    print("\n✅ SUCCESS!")

except Exception as e:
    print(f"\n❌ ERROR: {e}")
    print("Rolling back...")
    conn.rollback()
    import traceback
    traceback.print_exc()
    
finally:
    cur.close()
    conn.close()
