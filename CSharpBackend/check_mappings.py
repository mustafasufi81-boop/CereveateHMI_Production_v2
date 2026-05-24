import psycopg2
from psycopg2.extras import RealDictCursor

conn_str = "host=localhost port=5432 dbname=Cereveate user=cereveate password=cereveate@222"

try:
    conn = psycopg2.connect(conn_str)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Check tag_master
    cursor.execute("SELECT COUNT(*) as total FROM historian_meta.tag_master")
    total = cursor.fetchone()
    print(f"\n=== TAG_MASTER TABLE ===")
    print(f"Total rows: {total['total']}")
    
    cursor.execute("SELECT COUNT(*) as enabled FROM historian_meta.tag_master WHERE enabled = true")
    enabled = cursor.fetchone()
    print(f"Enabled rows: {enabled['enabled']}")
    
    cursor.execute("SELECT tag_id, tag_name, enabled, db_logging_interval_ms FROM historian_meta.tag_master LIMIT 10")
    tags = cursor.fetchall()
    print(f"\nFirst 10 mappings:")
    for tag in tags:
        print(f"  {tag['tag_id']:30} enabled={tag['enabled']} interval={tag['db_logging_interval_ms']}ms")
    
    # Check historian_timeseries
    cursor.execute("SELECT COUNT(*) as total, MAX(time) as latest FROM historian_raw.historian_timeseries")
    data = cursor.fetchone()
    print(f"\n=== HISTORIAN_TIMESERIES TABLE ===")
    print(f"Total rows: {data['total']}")
    print(f"Latest timestamp: {data['latest']}")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"ERROR: {e}")
