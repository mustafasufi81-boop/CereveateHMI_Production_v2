import psycopg2
from datetime import datetime
import time

conn_str = "host=localhost port=5432 dbname=Cereveate user=cereveate password=cereveate@222"

print("Waiting 10 seconds for server to establish OPC connection...")
time.sleep(10)

try:
    conn = psycopg2.connect(conn_str)
    cursor = conn.cursor()
    
    # Get latest timestamp
    cursor.execute("SELECT MAX(time) FROM historian_raw.historian_timeseries")
    latest = cursor.fetchone()[0]
    
    print(f"\n=== BEFORE (Latest data): {latest}")
    
    # Wait 5 seconds
    print("\nWaiting 5 seconds for new data...")
    time.sleep(5)
    
    # Check again
    cursor.execute("SELECT MAX(time) FROM historian_raw.historian_timeseries")
    latest_after = cursor.fetchone()[0]
    
    print(f"=== AFTER (Latest data): {latest_after}")
    
    if latest_after > latest:
        print("\n✅ SUCCESS! New data is flowing to database!")
        cursor.execute("""
            SELECT tag_id, time, sample_double
            FROM historian_raw.historian_timeseries
            WHERE time > %s
            ORDER BY time DESC
            LIMIT 10
        """, (latest,))
        
        print("\nNew rows:")
        for row in cursor.fetchall():
            print(f"  {row[0]:40} {row[1]} = {row[2]}")
    else:
        print("\n❌ NO NEW DATA! OPC connection or historian ingest not working")
        print("\nPossible issues:")
        print("  1. DataLoggingService not started (check ServerProgId in config)")
        print("  2. OPC connection not established")
        print("  3. HistorianIngestHostedService not reading from tag pool")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"ERROR: {e}")
