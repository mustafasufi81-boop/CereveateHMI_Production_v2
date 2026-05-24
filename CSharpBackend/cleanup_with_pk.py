import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

# Find primary key column
cur.execute("""
SELECT a.attname
FROM pg_index i
JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
WHERE i.indrelid = 'historian_raw.historian_timeseries'::regclass
AND i.indisprimary;
""")

pk_cols = cur.fetchall()
print("\nPrimary Key columns:")
for col in pk_cols:
    print(f"  - {col[0]}")

# Now do proper cleanup using primary key
print("\n" + "="*80)
print("CLEANUP USING PRIMARY KEY")
print("="*80)

# Get count before
cur.execute("SELECT COUNT(*) FROM historian_raw.historian_timeseries WHERE tag_id = 'Random.UInt2'")
before_count = cur.fetchone()[0]
print(f"\nRows before cleanup: {before_count}")

# Find primary key column name
if pk_cols:
    pk_col = pk_cols[0][0]
    print(f"Using primary key column: {pk_col}")
    
    # Delete duplicates using primary key
    delete_query = f"""
    DELETE FROM historian_raw.historian_timeseries
    WHERE {pk_col} IN (
        SELECT {pk_col}
        FROM (
            SELECT 
                {pk_col},
                ROW_NUMBER() OVER (
                    PARTITION BY tag_id, DATE_TRUNC('second', time), 
                                 COALESCE(value_num::text, ''), 
                                 COALESCE(value_bool::text, ''), 
                                 COALESCE(value_text, '')
                    ORDER BY time ASC
                ) as row_num
            FROM historian_raw.historian_timeseries
            WHERE tag_id = 'Random.UInt2'
        ) sub
        WHERE row_num > 1
    );
    """
    
    print("\nExecuting delete...")
    cur.execute(delete_query)
    deleted_count = cur.rowcount
    
    conn.commit()
    
    # Get count after
    cur.execute("SELECT COUNT(*) FROM historian_raw.historian_timeseries WHERE tag_id = 'Random.UInt2'")
    after_count = cur.fetchone()[0]
    
    print(f"\n✅ Deleted rows: {deleted_count}")
    print(f"✅ Rows after cleanup: {after_count}")
    print(f"✅ Space saved: {(deleted_count/before_count*100):.1f}%")
    
    # Verify
    cur.execute("""
    SELECT COUNT(*)
    FROM (
        SELECT 
            DATE_TRUNC('second', time) as sec,
            COALESCE(value_num::text, '') as val
        FROM historian_raw.historian_timeseries
        WHERE tag_id = 'Random.UInt2'
        GROUP BY sec, val
        HAVING COUNT(*) > 1
    ) dup;
    """)
    remaining = cur.fetchone()[0]
    
    if remaining == 0:
        print("\n✅ SUCCESS: No duplicates remaining!")
    else:
        print(f"\n⚠️ {remaining} duplicate groups still exist")

cur.close()
conn.close()
