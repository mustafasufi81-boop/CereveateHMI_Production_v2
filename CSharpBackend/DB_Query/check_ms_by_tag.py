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
    
    # Check recent data for ALL tags - see which have milliseconds
    query = """
    SELECT DISTINCT ON (tag_id)
        tag_id,
        time,
        EXTRACT(MILLISECONDS FROM time) as milliseconds,
        EXTRACT(MICROSECONDS FROM time) as microseconds,
        value_num
    FROM historian_raw.historian_timeseries
    WHERE time > NOW() - INTERVAL '10 minutes'
    ORDER BY tag_id, time DESC
    LIMIT 20
    """
    
    cursor.execute(query)
    rows = cursor.fetchall()
    
    print("\n" + "="*100)
    print("MILLISECOND CHECK BY TAG (Last 10 minutes)")
    print("="*100)
    
    tags_with_ms = []
    tags_without_ms = []
    
    for row in rows:
        tag_id = row[0]
        timestamp = row[1]
        ms = row[2]
        us = row[3]
        value = row[4]
        
        fractional = us % 1000000  # Get microseconds part
        ms_part = fractional // 1000  # Extract milliseconds
        
        print(f"\nTag: {tag_id}")
        print(f"  Time: {timestamp}")
        print(f"  Milliseconds: {ms_part:03d}")
        print(f"  Microseconds: {fractional:06d}")
        print(f"  Value: {value}")
        
        if fractional == 0:
            tags_without_ms.append(tag_id)
            print(f"  ⚠️  NO FRACTIONAL SECONDS!")
        else:
            tags_with_ms.append(tag_id)
            print(f"  ✅ Has millisecond precision")
    
    print("\n" + "="*100)
    print("SUMMARY")
    print("="*100)
    print(f"\n✅ Tags WITH milliseconds ({len(tags_with_ms)}):")
    for tag in tags_with_ms:
        print(f"   - {tag}")
    
    print(f"\n⚠️  Tags WITHOUT milliseconds ({len(tags_without_ms)}):")
    for tag in tags_without_ms:
        print(f"   - {tag}")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")
