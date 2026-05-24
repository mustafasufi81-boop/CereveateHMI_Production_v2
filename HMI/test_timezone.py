"""
Test timezone issue with PostgreSQL
"""
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime

# Load database config
with open('config.json', 'r') as f:
    config = json.load(f)
    db_config = config['database']

try:
    conn = psycopg2.connect(**db_config)
    cursor = conn.cursor()
    
    print("=" * 80)
    print("TIMEZONE DIAGNOSTIC")
    print("=" * 80)
    
    # Check PostgreSQL timezone settings
    cursor.execute("SHOW timezone;")
    result = cursor.fetchone()
    print(f"\n1. PostgreSQL timezone: {result[0] if result else 'Unknown'}")
    
    # Check NOW() value
    cursor.execute("SELECT NOW() as server_time, NOW() AT TIME ZONE 'Asia/Kolkata' as ist_time;")
    result = cursor.fetchone()
    print(f"2. Server NOW(): {result[0]}")
    print(f"3. NOW() in IST: {result[1]}")
    
    # Check actual event timestamps
    cursor.execute("""
        SELECT time, time AT TIME ZONE 'UTC' as utc_time, time AT TIME ZONE 'Asia/Kolkata' as ist_time
        FROM historian_raw.historian_events 
        ORDER BY time DESC 
        LIMIT 3
    """)
    print("\n4. Recent event timestamps:")
    for row in cursor.fetchall():
        print(f"   Original: {row[0]}")
        print(f"   UTC: {row[1]}")
        print(f"   IST: {row[2]}")
        print()
    
    # Test the actual query filter
    cursor.execute("""
        SELECT COUNT(*) as count,
               MIN(time) as oldest,
               MAX(time) as newest
        FROM historian_raw.historian_events 
        WHERE time >= NOW() - INTERVAL '24 hours'
          AND time <= NOW() + INTERVAL '1 hour'
    """)
    result = cursor.fetchone()
    print(f"5. Events matching current filter: {result[0]}")
    print(f"   Oldest: {result[1]}")
    print(f"   Newest: {result[2]}")
    
    # Test with wider future range
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM historian_raw.historian_events 
        WHERE time >= NOW() - INTERVAL '24 hours'
          AND time <= NOW() + INTERVAL '6 hours'
    """)
    result = cursor.fetchone()
    print(f"\n6. Events with +6 hour future buffer: {result[0]}")
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 80)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 80)
    
except Exception as e:
    print(f"ERROR: {e}")
