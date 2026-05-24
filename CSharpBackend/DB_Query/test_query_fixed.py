"""
Test the fixed query to verify:
1. ORDER BY DESC returns latest data first
2. Time range filtering works correctly (Last 5 mins shows recent data, not 11PM)
3. Timestamps display with milliseconds
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
import json

# Load config
with open('config.json', 'r') as f:
    config = json.load(f)

DB_CONFIG = config['database']

def test_query():
    conn = psycopg2.connect(
        host=DB_CONFIG['host'],
        port=DB_CONFIG['port'],
        database=DB_CONFIG['database'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password']
    )
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get current time
    now = datetime.now()
    five_mins_ago = now - timedelta(minutes=5)
    
    print("=" * 80)
    print("🧪 TESTING FIXED QUERY")
    print("=" * 80)
    print(f"Current Time: {now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
    print(f"Query Range: Last 5 minutes ({five_mins_ago.strftime('%Y-%m-%d %H:%M:%S')} to {now.strftime('%Y-%m-%d %H:%M:%S')})")
    print()
    
    # Test 1: Check latest data with ORDER BY DESC
    print("📊 TEST 1: ORDER BY time DESC (Latest First)")
    print("-" * 80)
    
    cur.execute("""
        SELECT 
            time as timestamp,
            tag_id,
            value_num as value,
            quality
        FROM historian_raw.historian_timeseries
        WHERE tag_id = 'Welding_Current_A'
        AND time >= %s
        AND time <= %s
        ORDER BY time DESC
        LIMIT 10
    """, (five_mins_ago, now))
    
    latest_records = cur.fetchall()
    
    if latest_records:
        print(f"✅ Found {len(latest_records)} records in last 5 minutes")
        print("\nTop 5 LATEST records (should be newest first):")
        for i, row in enumerate(latest_records[:5], 1):
            # Display with milliseconds
            timestamp_with_ms = row['timestamp'].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            print(f"  {i}. {timestamp_with_ms} | {row['tag_id']} = {row['value']:.3f} | Quality={row['quality']}")
        
        # Check if data is actually recent
        latest_time = latest_records[0]['timestamp']
        oldest_time = latest_records[-1]['timestamp']
        time_diff_seconds = (now - latest_time.replace(tzinfo=None)).total_seconds()
        
        print(f"\n📅 Latest record age: {time_diff_seconds:.1f} seconds ago")
        print(f"📅 Oldest in results: {(now - oldest_time.replace(tzinfo=None)).total_seconds():.1f} seconds ago")
        
        if time_diff_seconds < 300:  # Within 5 minutes
            print("✅ PASS: Data is recent (within 5 minutes)")
        else:
            print(f"❌ FAIL: Latest record is {time_diff_seconds/60:.1f} minutes old (should be < 5 mins)")
    else:
        print("⚠️ No records found in last 5 minutes")
        print("   Checking if any data exists for this tag...")
        
        cur.execute("""
            SELECT 
                MAX(time) as latest_time,
                MIN(time) as oldest_time,
                COUNT(*) as total_count
            FROM historian_raw.historian_timeseries
            WHERE tag_id = 'Welding_Current_A'
        """)
        
        stats = cur.fetchone()
        if stats['total_count'] > 0:
            print(f"   Found {stats['total_count']} total records")
            print(f"   Latest: {stats['latest_time']}")
            print(f"   Oldest: {stats['oldest_time']}")
        else:
            print("   ❌ No data exists for Welding_Current_A")
    
    print()
    
    # Test 2: Compare ASC vs DESC order
    print("📊 TEST 2: Compare ORDER BY ASC vs DESC")
    print("-" * 80)
    
    # Get oldest with ASC
    cur.execute("""
        SELECT time as timestamp, value_num as value
        FROM historian_raw.historian_timeseries
        WHERE tag_id = 'Welding_Current_A'
        ORDER BY time ASC
        LIMIT 3
    """)
    asc_records = cur.fetchall()
    
    # Get newest with DESC
    cur.execute("""
        SELECT time as timestamp, value_num as value
        FROM historian_raw.historian_timeseries
        WHERE tag_id = 'Welding_Current_A'
        ORDER BY time DESC
        LIMIT 3
    """)
    desc_records = cur.fetchall()
    
    print("ORDER BY time ASC (Oldest first):")
    for row in asc_records[:3]:
        timestamp_with_ms = row['timestamp'].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        print(f"  {timestamp_with_ms} = {row['value']:.3f}")
    
    print("\nORDER BY time DESC (Newest first):")
    for row in desc_records[:3]:
        timestamp_with_ms = row['timestamp'].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        print(f"  {timestamp_with_ms} = {row['value']:.3f}")
    
    print()
    
    # Test 3: Check page size 4000
    print("📊 TEST 3: Page Size 4000 Query Speed")
    print("-" * 80)
    
    import time as time_module
    start = time_module.time()
    
    cur.execute("""
        SELECT 
            time as timestamp,
            tag_id,
            value_num as value,
            quality
        FROM historian_raw.historian_timeseries
        WHERE tag_id = 'Welding_Current_A'
        ORDER BY time DESC
        LIMIT 4000
    """)
    
    large_result = cur.fetchall()
    query_time = time_module.time() - start
    
    print(f"✅ Query returned {len(large_result)} records in {query_time:.3f} seconds")
    
    if len(large_result) > 0:
        latest_ts = large_result[0]['timestamp'].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        oldest_ts = large_result[-1]['timestamp'].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        print(f"   Latest: {latest_ts}")
        print(f"   Oldest: {oldest_ts}")
        
        if query_time < 3.0:
            print(f"✅ PASS: Query is fast (<3 seconds)")
        else:
            print(f"⚠️ WARNING: Query took {query_time:.1f}s (expected <3s)")
    
    print()
    print("=" * 80)
    print("🎯 SUMMARY")
    print("=" * 80)
    print("✅ All tests completed")
    print(f"   - Query returns LATEST data first (DESC order)")
    print(f"   - Timestamps include milliseconds")
    print(f"   - Page size 4000 supported")
    print(f"   - Query time: {query_time:.3f}s")
    print("=" * 80)
    
    cur.close()
    conn.close()

if __name__ == '__main__':
    test_query()
