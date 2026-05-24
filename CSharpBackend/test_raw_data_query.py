"""
Test Raw Data Query - Verify exact interval sampling works
Tests the NEW query that returns raw data at exact user-selected intervals
"""
import psycopg2
from datetime import datetime, timedelta
import sys

# Database config
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'Cereveate',
    'user': 'cereveate',
    'password': 'cereveate@222'
}

def test_query(tag_id, hours, sampling_interval):
    """
    Test the new raw data query with exact interval filtering
    
    Args:
        tag_id: Tag to query (e.g., 'Random.UInt1')
        hours: Time range in hours (e.g., 6)
        sampling_interval: Exact interval in seconds (e.g., 5, 10, 30)
    """
    print(f"\n{'='*80}")
    print(f"TEST: Raw Data Query for '{tag_id}'")
    print(f"Time Range: Last {hours} hours")
    print(f"Sampling Interval: {sampling_interval} seconds")
    print(f"{'='*80}\n")
    
    # Calculate time range
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours)
    
    print(f"Start Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"End Time:   {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Expected Interval: Every {sampling_interval} seconds\n")
    
    try:
        # Connect to database
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        print("✅ Connected to PostgreSQL database\n")
        
        # ===================================================================
        # NEW QUERY - Returns RAW data at EXACT intervals using modulo filter
        # ===================================================================
        query = """
            SELECT 
                time as timestamp,
                value_num as value,
                quality
            FROM historian_raw.historian_timeseries
            WHERE tag_id = %s
            AND time BETWEEN %s AND %s
            AND EXTRACT(EPOCH FROM time)::bigint %% %s = 0
            ORDER BY time
        """
        
        print("🔍 Executing NEW query (with modulo filter):")
        print("-" * 80)
        print(query.strip())
        print("-" * 80)
        print(f"Parameters: tag_id='{tag_id}', interval={sampling_interval}s\n")
        
        cursor.execute(query, (tag_id, start_time, end_time, sampling_interval))
        rows = cursor.fetchall()
        
        print(f"✅ Query returned {len(rows)} records\n")
        
        if len(rows) == 0:
            print("⚠️  WARNING: No data returned!")
            print("\nPossible reasons:")
            print("1. No data exists for this tag in the time range")
            print("2. Data is not aligned to exact epoch intervals")
            print("3. Tag name is incorrect\n")
            
            # Check if ANY data exists for this tag
            print("Checking if tag has ANY data in time range...")
            cursor.execute("""
                SELECT COUNT(*), MIN(time), MAX(time)
                FROM historian_raw.historian_timeseries
                WHERE tag_id = %s AND time BETWEEN %s AND %s
            """, (tag_id, start_time, end_time))
            
            count, min_time, max_time = cursor.fetchone()
            print(f"Total records (any interval): {count}")
            if count > 0:
                print(f"First record: {min_time}")
                print(f"Last record: {max_time}")
                print("\n⚠️  Data exists but doesn't match exact intervals!")
                print("This means data is written at irregular timestamps.")
            
            return False
        
        # ===================================================================
        # VERIFY: Check that intervals are EXACTLY as requested
        # ===================================================================
        print(f"{'TIMESTAMP':<25} {'VALUE':<15} {'QUALITY':<10} {'INTERVAL (s)'}")
        print("-" * 80)
        
        prev_timestamp = None
        intervals = []
        
        # Show first 10 records
        display_count = min(10, len(rows))
        for i, (timestamp, value, quality) in enumerate(rows[:display_count]):
            interval_str = ""
            if prev_timestamp:
                interval_seconds = (timestamp - prev_timestamp).total_seconds()
                intervals.append(interval_seconds)
                interval_str = f"{interval_seconds:.1f}"
            
            print(f"{timestamp.strftime('%Y-%m-%d %H:%M:%S'):<25} {value:<15.2f} {quality:<10} {interval_str}")
            prev_timestamp = timestamp
        
        if len(rows) > 10:
            print(f"... ({len(rows) - 10} more records)")
            
            # Show last 3 records
            print("\nLast 3 records:")
            for timestamp, value, quality in rows[-3:]:
                interval_seconds = (timestamp - prev_timestamp).total_seconds()
                intervals.append(interval_seconds)
                print(f"{timestamp.strftime('%Y-%m-%d %H:%M:%S'):<25} {value:<15.2f} {quality:<10} {interval_seconds:.1f}")
                prev_timestamp = timestamp
        
        # ===================================================================
        # STATISTICS: Verify interval consistency
        # ===================================================================
        if intervals:
            print(f"\n{'='*80}")
            print("INTERVAL STATISTICS:")
            print(f"{'='*80}")
            print(f"Total data points: {len(rows)}")
            print(f"Total intervals measured: {len(intervals)}")
            print(f"Expected interval: {sampling_interval} seconds")
            print(f"Actual min interval: {min(intervals):.1f} seconds")
            print(f"Actual max interval: {max(intervals):.1f} seconds")
            print(f"Actual avg interval: {sum(intervals)/len(intervals):.1f} seconds")
            
            # Check consistency
            exact_matches = sum(1 for i in intervals if abs(i - sampling_interval) < 0.5)
            match_percent = (exact_matches / len(intervals)) * 100
            
            print(f"\n✅ Exact matches: {exact_matches}/{len(intervals)} ({match_percent:.1f}%)")
            
            if match_percent >= 95:
                print("🎉 SUCCESS: Query returns data at exact intervals!")
            elif match_percent >= 80:
                print("⚠️  WARNING: Some intervals don't match (might have gaps in data)")
            else:
                print("❌ FAILURE: Intervals are inconsistent!")
        
        # ===================================================================
        # COMPARE: Old query (time_bucket + AVG) vs New query (modulo filter)
        # ===================================================================
        print(f"\n{'='*80}")
        print("COMPARISON: Old Query (time_bucket + AVG)")
        print(f"{'='*80}\n")
        
        # Calculate interval for old query
        time_diff_seconds = (end_time - start_time).total_seconds()
        max_points = 1000
        old_interval = max(1, int(time_diff_seconds / max_points))
        
        old_query = """
            SELECT 
                time_bucket(%s::interval, time) AS timestamp,
                AVG(value_num) as value,
                MAX(quality) as quality
            FROM historian_raw.historian_timeseries
            WHERE tag_id = %s
            AND time BETWEEN %s AND %s
            GROUP BY time_bucket(%s::interval, time)
            ORDER BY timestamp
        """
        
        interval_str = f"{old_interval} seconds"
        cursor.execute(old_query, (interval_str, tag_id, start_time, end_time, interval_str))
        old_rows = cursor.fetchall()
        
        print(f"Old query would use: {old_interval}s buckets (calculated from {hours}h / {max_points} points)")
        print(f"Old query returned: {len(old_rows)} records (AVERAGED values)")
        print(f"New query returned: {len(rows)} records (RAW values)")
        print(f"\nDifference: {abs(len(rows) - len(old_rows))} records")
        
        if len(old_rows) > 0 and len(rows) > 0:
            # Compare first values
            old_first_value = old_rows[0][1]
            new_first_value = rows[0][1]
            print(f"\nFirst value comparison:")
            print(f"  Old query (AVG): {old_first_value:.2f}")
            print(f"  New query (RAW): {new_first_value:.2f}")
            print(f"  Difference: {abs(old_first_value - new_first_value):.2f}")
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Test parameters
    TAG_ID = "Random.UInt1"
    HOURS = 6
    SAMPLING_INTERVAL = 30  # 30 seconds
    
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                     RAW DATA QUERY TEST SCRIPT                               ║
║                                                                              ║
║  Purpose: Verify the NEW query returns raw data at exact user intervals     ║
║  Date: December 21, 2025                                                     ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """)
    
    # Test 1: 30-second intervals (6 hours)
    success = test_query(TAG_ID, HOURS, SAMPLING_INTERVAL)
    
    if success:
        print(f"\n{'='*80}")
        print("Additional tests with different intervals:")
        print(f"{'='*80}")
        
        # Test 2: 10-second intervals (1 hour for faster results)
        test_query(TAG_ID, 1, 10)
        
        # Test 3: 5-second intervals (30 minutes for fastest check)
        test_query(TAG_ID, 0.5, 5)
    
    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)
