import psycopg2
from psycopg2.extras import RealDictCursor

# Test the exact query from /api/stats/total
try:
    conn = psycopg2.connect(
        host='192.168.0.120',
        port=5432,
        database='Cereveate',
        user='cereveate',
        password='cereveate@222'
    )
    
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    print("Testing /api/stats/total query...")
    cur.execute("""
        SELECT 
            COUNT(*) as total_records,
            COUNT(DISTINCT tag_id) as unique_tags,
            MIN(timestamp) as earliest_record,
            MAX(timestamp) as latest_record,
            EXTRACT(EPOCH FROM (MAX(timestamp) - MIN(timestamp))) / 3600 as total_hours,
            pg_size_pretty(pg_total_relation_size('historian_raw.historian_timeseries')) as table_size
        FROM historian_raw.historian_timeseries
    """)
    
    result = cur.fetchone()
    print("✅ Query SUCCESS!")
    print(f"Total Records: {result['total_records']}")
    print(f"Unique Tags: {result['unique_tags']}")
    print(f"Table Size: {result['table_size']}")
    
    cur.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Query FAILED: {e}")
    import traceback
    traceback.print_exc()
