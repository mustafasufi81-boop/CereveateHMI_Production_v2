import psycopg2

DB_CONFIG = {
    'host': '192.168.0.120',
    'port': 5432,
    'database': 'Cereveate',
    'user': 'cereveate',
    'password': 'cereveate@222'
}

try:
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    # Check if ANY records have non-zero milliseconds
    query = """
    SELECT 
        tag_id,
        COUNT(*) as total_records,
        COUNT(CASE WHEN EXTRACT(MILLISECOND FROM time) > 0 THEN 1 END) as records_with_ms,
        MIN(time) as first_time,
        MAX(time) as last_time
    FROM historian_raw.historian_timeseries
    GROUP BY tag_id
    ORDER BY total_records DESC
    LIMIT 10
    """
    
    cursor.execute(query)
    rows = cursor.fetchall()
    
    print("\n" + "="*100)
    print("MILLISECOND DATA CHECK - Top 10 Tags")
    print("="*100)
    
    total_with_ms = 0
    total_without_ms = 0
    
    for row in rows:
        tag_id, total, with_ms, first, last = row
        without_ms = total - with_ms
        total_with_ms += with_ms
        total_without_ms += without_ms
        
        print(f"\nTag: {tag_id}")
        print(f"  Total records: {total:,}")
        print(f"  With milliseconds: {with_ms:,} ({with_ms/total*100:.1f}%)")
        print(f"  Without milliseconds: {without_ms:,} ({without_ms/total*100:.1f}%)")
        print(f"  Time range: {first} to {last}")
    
    print("\n" + "="*100)
    print(f"SUMMARY: {total_with_ms:,} records WITH milliseconds, {total_without_ms:,} WITHOUT")
    print("="*100)
    
    # Show sample records
    print("\n" + "="*100)
    print("SAMPLE RECORDS (showing microsecond precision)")
    print("="*100)
    
    query2 = """
    SELECT time, tag_id, value_num
    FROM historian_raw.historian_timeseries
    ORDER BY time DESC
    LIMIT 5
    """
    
    cursor.execute(query2)
    samples = cursor.fetchall()
    
    for i, (ts, tag, val) in enumerate(samples, 1):
        print(f"\n{i}. {ts} | {tag} | {val}")
        print(f"   Microseconds: {ts.microsecond}")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")
