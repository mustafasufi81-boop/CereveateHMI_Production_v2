import psycopg2
from datetime import datetime
import time

conn_str = "host=localhost port=5432 dbname=Cereveate user=cereveate password=cereveate@222"

try:
    conn = psycopg2.connect(conn_str)
    cursor = conn.cursor()
    
    # Get column names
    cursor.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_schema = 'historian_raw' 
        AND table_name = 'historian_timeseries'
        ORDER BY ordinal_position
    """)
    
    print("=== HISTORIAN_TIMESERIES COLUMNS ===")
    for row in cursor.fetchall():
        print(f"  {row[0]:30} {row[1]}")
    
    # Get latest timestamp
    cursor.execute("SELECT MAX(time) FROM historian_raw.historian_timeseries")
    latest = cursor.fetchone()[0]
    print(f"\n=== LATEST TIMESTAMP: {latest} ===")
    
    # Wait 5 seconds
    print("\nWaiting 5 seconds for new data...")
    time.sleep(5)
    
    # Get latest 10 rows with correct columns
    cursor.execute("""
        SELECT time, tag_id, value_num, value_text, value_bool, quality, sample_source
        FROM historian_raw.historian_timeseries
        WHERE time > %s
        ORDER BY time DESC
        LIMIT 10
    """, (latest,))
    
    rows = cursor.fetchall()
    
    if rows:
        print(f"\n✅ NEW DATA FLOWING! ({len(rows)} new rows)")
        print("\n=== LATEST ROWS ===")
        for row in rows:
            value = row[2] or row[3] or row[4]
            quality = row[5]
            source = row[6]
            print(f"  {row[1]:40} {row[0]} = {value} [Q:{quality}] ({source})")
    else:
        print("\n❌ NO NEW DATA!")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"ERROR: {e}")
