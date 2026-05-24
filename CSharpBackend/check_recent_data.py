import psycopg2
from datetime import datetime, timedelta

conn_str = "host=localhost port=5432 dbname=Cereveate user=cereveate password=cereveate@222"

try:
    conn = psycopg2.connect(conn_str)
    cursor = conn.cursor()
    
    # Check data freshness by tag
    cursor.execute("""
        SELECT tag_id, MAX(time) as latest_time, COUNT(*) as count
        FROM historian_raw.historian_timeseries
        GROUP BY tag_id
        ORDER BY MAX(time) DESC
        LIMIT 10
    """)
    
    print("\n=== LATEST DATA BY TAG ===")
    now = datetime.now()
    for row in cursor.fetchall():
        tag_id, latest, count = row
        age = now - latest.replace(tzinfo=None)
        age_str = f"{int(age.total_seconds())}s ago" if age.total_seconds() < 3600 else f"{int(age.total_seconds()/60)}m ago"
        print(f"{tag_id:40} {latest} ({age_str}) - {count} rows")
    
    # Check if any recent data (last 5 minutes)
    cursor.execute("""
        SELECT COUNT(*) as recent_count
        FROM historian_raw.historian_timeseries
        WHERE time > NOW() - INTERVAL '5 minutes'
    """)
    recent = cursor.fetchone()[0]
    print(f"\n=== DATA IN LAST 5 MINUTES ===")
    print(f"Rows inserted: {recent}")
    
    if recent == 0:
        print("\n⚠️ WARNING: NO DATA in last 5 minutes!")
        print("   - Check if OPC server is connected")
        print("   - Check if DataLoggingService is running")
        print("   - Check if HistorianIngestHostedService is running")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"ERROR: {e}")
