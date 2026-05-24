"""
Test Script: 500ms OPC Direct Polling Test
Tests if we can poll OPC DA server at 500ms intervals
"""
import time
from datetime import datetime
import win32com.client
import pythoncom

# OPC Server Configuration
OPC_SERVER = "Matrikon.OPC.Simulation.1"
TEST_TAGS = [
    "Random.Real4",
    "Random.Int4", 
    "Saw-toothed Waves.Real4",
    "Triangle Waves.Int1",
    "Bucket Brigade.Real8"
]

def connect_opc():
    """Connect to OPC DA server"""
    pythoncom.CoInitialize()
    opc = win32com.client.Dispatch(OPC_SERVER)
    print(f"✅ Connected to {OPC_SERVER}")
    return opc

def check_recent_writes(seconds=10):
    """Check writes in the last N seconds"""
    conn = get_connection()
    cur = conn.cursor()
    
    query = """
    SELECT 
        tag_id,
        COUNT(*) as write_count,
        MIN(time) as first_write,
        MAX(time) as last_write,
        EXTRACT(EPOCH FROM (MAX(time) - MIN(time))) as duration_seconds,
        AVG(value_numeric) as avg_value
    FROM historian_raw.historian_timeseries
    WHERE time >= NOW() - INTERVAL '%s seconds'
    GROUP BY tag_id
    ORDER BY write_count DESC
    """
    
    cur.execute(query, (seconds,))
    results = cur.fetchall()
    
    print(f"\n{'='*80}")
    print(f"📊 WRITES IN LAST {seconds} SECONDS (500ms OPC Polling Test)")
    print(f"{'='*80}")
    print(f"{'Tag ID':<30} {'Writes':<10} {'Duration':<12} {'Avg Value':<15} {'Rate/sec'}")
    print(f"{'-'*80}")
    
    total_writes = 0
    for tag_id, count, first, last, duration, avg_val in results:
        rate = count / duration if duration > 0 else 0
        total_writes += count
        print(f"{tag_id:<30} {count:<10} {duration:<12.2f} {avg_val:<15.2f} {rate:.2f}")
    
    print(f"{'-'*80}")
    print(f"TOTAL: {total_writes} writes across {len(results)} tags")
    
    cur.close()
    conn.close()
    return results

def analyze_intervals(tag_id, limit=20):
    """Analyze actual time intervals between consecutive writes for a specific tag"""
    conn = get_connection()
    cur = conn.cursor()
    
    query = """
    WITH ordered_writes AS (
        SELECT 
            time,
            value_numeric as value,
            LAG(time) OVER (ORDER BY time) as prev_timestamp
        FROM historian_raw.historian_timeseries
        WHERE tag_id = %s
        ORDER BY time DESC
        LIMIT %s
    )
    SELECT 
        time,
        value,
        EXTRACT(EPOCH FROM (time - prev_timestamp)) * 1000 as interval_ms
    FROM ordered_writes
    WHERE prev_timestamp IS NOT NULL
    ORDER BY time DESC
    """
    
    cur.execute(query, (tag_id, limit))
    results = cur.fetchall()
    
    print(f"\n{'='*80}")
    print(f"⏱️  INTERVAL ANALYSIS: {tag_id} (Last {limit} writes)")
    print(f"{'='*80}")
    print(f"{'Timestamp':<25} {'Value':<15} {'Interval (ms)'}")
    print(f"{'-'*80}")
    
    intervals = []
    for ts, val, interval_ms in results:
        if interval_ms is not None:
            intervals.append(interval_ms)
            print(f"{str(ts):<25} {val:<15.2f} {interval_ms:>8.0f}ms")
    
    if intervals:
        print(f"{'-'*80}")
        print(f"Min Interval: {min(intervals):.0f}ms")
        print(f"Max Interval: {max(intervals):.0f}ms")
        print(f"Avg Interval: {sum(intervals)/len(intervals):.0f}ms")
        print(f"Expected:     1000ms (rate-controlled)")
        
        # Check if we're seeing 500ms polling in data
        fast_writes = [i for i in intervals if i < 600]
        if fast_writes:
            print(f"\n⚠️  WARNING: {len(fast_writes)} writes faster than 600ms detected!")
            print(f"   This suggests 500ms polling is bypassing rate control")
        else:
            print(f"\n✅ All writes >= 600ms - Rate controller working correctly")
    
    cur.close()
    conn.close()

def real_time_monitor(duration=15):
    """Monitor database writes in real-time"""
    conn = get_connection()
    cur = conn.cursor()
    
    print(f"\n{'='*80}")
    print(f"🔴 LIVE MONITORING: {duration} seconds (500ms polling test)")
    print(f"{'='*80}")
    
    start_time = datetime.now()
    last_count = 0
    
    while (datetime.now() - start_time).seconds < duration:
        cur.execute("""
            SELECT COUNT(*), COUNT(DISTINCT tag_id)
            FROM historian_raw.historian_timeseries
            WHERE time >= %s
        """, (start_time,))
        
        total, tags = cur.fetchone()
        new_writes = total - last_count
        elapsed = (datetime.now() - start_time).total_seconds()
        
        if new_writes > 0:
            rate = total / elapsed if elapsed > 0 else 0
            print(f"[{elapsed:>5.1f}s] Total: {total:>4} | New: +{new_writes:>2} | Tags: {tags:>2} | Rate: {rate:>5.1f}/s")
        
        last_count = total
        time.sleep(1)
    
    print(f"{'='*80}")
    print(f"✅ Monitoring complete: {total} total writes in {duration} seconds")
    
    cur.close()
    conn.close()

def check_config_loaded():
    """Verify the 500ms configuration is actually loaded"""
    print(f"\n{'='*80}")
    print(f"⚙️  CONFIGURATION CHECK")
    print(f"{'='*80}")
    
    conn = get_connection()
    cur = conn.cursor()
    
    # Check tag intervals in database
    cur.execute("""
        SELECT tag_id, db_logging_interval_ms, enabled
        FROM historian_meta.tag_master
        WHERE enabled = true
        ORDER BY tag_id
        LIMIT 5
    """)
    
    print(f"\n📋 Database Tag Intervals (historian_meta.tag_master):")
    print(f"{'Tag ID':<35} {'DB Interval':<15} {'Enabled'}")
    print(f"{'-'*80}")
    for tag_id, interval, enabled in cur.fetchall():
        print(f"{tag_id:<35} {interval:<15}ms {enabled}")
    
    print(f"\n📄 Config File Location:")
    print(f"   bin\\Debug\\net8.0\\win-x86\\logging-config.json")
    print(f"   Expected: OpcPollingIntervalMs: 500, IntervalSeconds: 0.5")
    print(f"   Database writes should still be at 1000ms (rate-controlled)")
    
    cur.close()
    conn.close()

def main():
    print(f"\n{'#'*80}")
    print(f"#  500ms OPC POLLING TEST - Database Performance Monitor")
    print(f"#  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*80}")
    
    try:
        # 1. Check configuration
        check_config_loaded()
        
        # 2. Check recent writes (last 10 seconds)
        recent = check_recent_writes(seconds=10)
        
        # 3. Analyze intervals for a specific tag
        if recent:
            tag_to_analyze = recent[0][0]  # Most active tag
            analyze_intervals(tag_to_analyze, limit=20)
        
        # 4. Real-time monitoring
        print(f"\n{'='*80}")
        input("Press ENTER to start 15-second real-time monitoring...")
        real_time_monitor(duration=15)
        
        # 5. Final summary
        print(f"\n{'='*80}")
        print(f"📈 FINAL SUMMARY")
        print(f"{'='*80}")
        check_recent_writes(seconds=30)
        
        print(f"\n✅ Test Complete!")
        print(f"\nEXPECTED RESULTS with 500ms OPC polling:")
        print(f"  • OPC reads tags every 500ms (twice per second)")
        print(f"  • Rate controller filters to 1000ms intervals")
        print(f"  • Database writes every 1 second (only changed values)")
        print(f"  • Should see ~1-2 writes/second per active tag")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
