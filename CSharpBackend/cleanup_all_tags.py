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
print("CLEANUP ALL TAGS - Remove duplicates for entire table")
print("="*80)

try:
    # Get total count and tag list before
    cur.execute("SELECT COUNT(*) FROM historian_raw.historian_timeseries")
    total_before = cur.fetchone()[0]
    print(f"\nTotal rows in table: {total_before:,}")
    
    cur.execute("SELECT tag_id, COUNT(*) FROM historian_raw.historian_timeseries GROUP BY tag_id ORDER BY COUNT(*) DESC")
    all_tags = cur.fetchall()
    print(f"Total unique tags: {len(all_tags)}")
    
    # Step 1: Create clean table with ALL deduplicated data
    print("\nStep 1: Creating clean table with deduplicated data for ALL tags...")
    print("This may take a few minutes...")
    
    start_time = time.time()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS historian_raw.historian_timeseries_clean AS
    SELECT DISTINCT ON (
        tag_id, 
        DATE_TRUNC('second', time), 
        COALESCE(value_num, -999999),
        COALESCE(value_bool::text, ''),
        COALESCE(value_text, '')
    )
        time, tag_id, value_num, value_text, value_bool, quality, 
        sample_source, mapping_version, opc_timestamp
    FROM historian_raw.historian_timeseries
    ORDER BY 
        tag_id, 
        DATE_TRUNC('second', time), 
        COALESCE(value_num, -999999),
        COALESCE(value_bool::text, ''),
        COALESCE(value_text, ''),
        time ASC;
    """)
    
    conn.commit()
    elapsed = time.time() - start_time
    
    cur.execute("SELECT COUNT(*) FROM historian_raw.historian_timeseries_clean")
    clean_count = cur.fetchone()[0]
    print(f"✅ Created clean table with {clean_count:,} unique rows in {elapsed:.1f}s")
    print(f"   Duplicates to remove: {total_before - clean_count:,} ({(total_before - clean_count)/total_before*100:.1f}%)")

    # Step 2: Rename tables (fast atomic swap)
    print("\nStep 2: Swapping tables (atomic operation)...")
    cur.execute("ALTER TABLE historian_raw.historian_timeseries RENAME TO historian_timeseries_old;")
    cur.execute("ALTER TABLE historian_raw.historian_timeseries_clean RENAME TO historian_timeseries;")
    conn.commit()
    print("✅ Tables swapped")

    # Step 3: Drop old table
    print("\nStep 3: Dropping old table with duplicates...")
    cur.execute("DROP TABLE historian_raw.historian_timeseries_old;")
    conn.commit()
    print("✅ Old table dropped")

    # Step 4: Recreate indexes
    print("\nStep 4: Recreating indexes...")
    
    # Primary key (check what columns are in PK first)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_historian_timeseries_tag_time 
        ON historian_raw.historian_timeseries(tag_id, time DESC);
    """)
    
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_historian_timeseries_time 
        ON historian_raw.historian_timeseries(time DESC);
    """)
    
    conn.commit()
    print("✅ Indexes recreated")

    # Verify
    cur.execute("SELECT COUNT(*) FROM historian_raw.historian_timeseries")
    total_after = cur.fetchone()[0]
    
    # Check duplicates per tag
    cur.execute("""
    SELECT tag_id, COUNT(*) as row_count
    FROM historian_raw.historian_timeseries
    GROUP BY tag_id
    ORDER BY row_count DESC
    LIMIT 10;
    """)
    top_tags = cur.fetchall()
    
    print("\n" + "="*80)
    print("CLEANUP COMPLETE FOR ALL TAGS!")
    print("="*80)
    print(f"Before: {total_before:,} rows")
    print(f"After:  {total_after:,} rows")
    print(f"Removed: {total_before - total_after:,} duplicates ({(total_before - total_after)/total_before*100:.1f}%)")
    
    print("\nTop 10 tags by row count after cleanup:")
    for tag, count in top_tags:
        print(f"  {tag:<40} {count:>10,} rows")
    
    print("\n✅ SUCCESS! All duplicates removed from entire table")

except Exception as e:
    print(f"\n❌ ERROR: {e}")
    print("Rolling back...")
    conn.rollback()
    import traceback
    traceback.print_exc()
    
finally:
    cur.close()
    conn.close()
