"""
Test Script: OPC Minimum Polling Frequency Test
Tests the minimum frequency at which tag values can be fetched and verified
Shows actual polling capability vs configured intervals
"""
import requests
import time
from datetime import datetime
import statistics
from collections import defaultdict

# Your C# OPC Service API
API_BASE = "http://localhost:5001"

def get_tag_values():
    """Get current tag values from OPC via C# service"""
    try:
        response = requests.get(f"{API_BASE}/api/opc/values", timeout=2)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def test_polling_frequency(duration=15, interval_ms=500):
    """Poll OPC at specified interval and measure performance + value freshness"""
    print(f"\n{'='*90}")
    print(f"🔴 OPC MINIMUM POLLING FREQUENCY TEST")
    print(f"{'='*90}")
    print(f"Duration: {duration} seconds")
    print(f"Target Interval: {interval_ms}ms")
    print(f"API Endpoint: {API_BASE}/api/opc/values")
    print(f"{'='*90}\n")
    
    interval_sec = interval_ms / 1000
    start_time = time.time()
    poll_count = 0
    intervals = []
    api_times = []
    errors = 0
    
    # Track tag value changes to detect freshness
    tag_history = defaultdict(list)
    value_changes = defaultdict(int)
    
    last_poll = time.time()
    
    print(f"{'Time':<10} {'Poll#':<6} {'Interval':<10} {'API Time':<10} {'Tags':<6} {'Changes':<8} {'Status'}")
    print(f"{'-'*90}")
    
    while (time.time() - start_time) < duration:
        poll_start = time.time()
        
        # Poll OPC via your C# API
        data = get_tag_values()
        
        poll_end = time.time()
        actual_interval = (poll_start - last_poll) * 1000
        api_response_time = (poll_end - poll_start) * 1000
        
        if data:
            poll_count += 1
            intervals.append(actual_interval)
            api_times.append(api_response_time)
            
            # Extract tags and track changes
            tags = []
            if isinstance(data, list):
                tags = data
            elif isinstance(data, dict):
                tags = data.get('tags', [])
            
            changes = 0
            for tag in tags:
                tag_id = tag.get('tagId') or tag.get('TagId') or tag.get('name')
                value = tag.get('value') or tag.get('Value')
                
                if tag_id:
                    # Check if value changed
                    history = tag_history[tag_id]
                    if len(history) > 0 and history[-1] != value:
                        value_changes[tag_id] += 1
                        changes += 1
                    history.append(value)
            
            status = "✅" if api_response_time < interval_ms else "⚠️"
            elapsed = time.time() - start_time
            
            print(f"{elapsed:>6.1f}s   {poll_count:<6} {actual_interval:>7.0f}ms  {api_response_time:>7.0f}ms  {len(tags):<6} {changes:<8} {status}")
            
        else:
            errors += 1
            elapsed = time.time() - start_time
            print(f"{elapsed:>6.1f}s   ERROR  -          -          -      -        ❌ API failed")
        
        last_poll = poll_start
        
        # Sleep until next poll
        sleep_time = interval_sec - (time.time() - poll_start)
        if sleep_time > 0:
            time.sleep(sleep_time)
    
    # Summary
    print(f"\n{'='*90}")
    print(f"📊 TEST RESULTS - {interval_ms}ms POLLING")
    print(f"{'='*90}")
    print(f"Total Polls:          {poll_count}")
    print(f"Errors:               {errors}")
    print(f"Success Rate:         {(poll_count/(poll_count+errors)*100):.1f}%")
    
    if intervals:
        print(f"\n⏱️  TIMING ANALYSIS:")
        print(f"Target Interval:      {interval_ms}ms")
        print(f"Actual Min:           {min(intervals):.0f}ms")
        print(f"Actual Max:           {max(intervals):.0f}ms")
        print(f"Actual Average:       {statistics.mean(intervals):.0f}ms")
        print(f"Actual Median:        {statistics.median(intervals):.0f}ms")
        print(f"Std Deviation:        {statistics.stdev(intervals):.0f}ms" if len(intervals) > 1 else "N/A")
        
        print(f"\n🔄 API RESPONSE TIMES:")
        print(f"Min API Response:     {min(api_times):.0f}ms")
        print(f"Max API Response:     {max(api_times):.0f}ms")
        print(f"Average API Response: {statistics.mean(api_times):.0f}ms")
        
        # Check if we achieved target interval
        avg_interval = statistics.mean(intervals)
        tolerance = interval_ms * 0.1  # 10% tolerance
        if (interval_ms - tolerance) <= avg_interval <= (interval_ms + tolerance):
            print(f"\n✅ SUCCESS: Achieved ~{interval_ms}ms polling!")
        elif avg_interval < (interval_ms - tolerance):
            print(f"\n⚠️  WARNING: Polling FASTER than target ({avg_interval:.0f}ms vs {interval_ms}ms)")
        else:
            print(f"\n❌ FAILED: Polling SLOWER than target ({avg_interval:.0f}ms vs {interval_ms}ms)")
        
    # Value freshness analysis
    if tag_history:
        total_tags = len(tag_history)
        changing_tags = sum(1 for count in value_changes.values() if count > 0)
        
        print(f"\n📈 TAG VALUE FRESHNESS:")
        print(f"Total Tags Tracked:   {total_tags}")
        print(f"Tags with Changes:    {changing_tags} ({changing_tags/total_tags*100:.1f}%)")
        
        if changing_tags > 0:
            print(f"\n🔄 Top Changing Tags:")
            sorted_tags = sorted(value_changes.items(), key=lambda x: x[1], reverse=True)[:5]
            for tag_id, count in sorted_tags:
                print(f"   {tag_id}: {count} changes")
        
        # Check for stale data
        stale_tags = total_tags - changing_tags
        if stale_tags > total_tags * 0.5:
            print(f"\n⚠️  WARNING: {stale_tags} tags ({stale_tags/total_tags*100:.0f}%) had NO value changes")
            print(f"   This may indicate:")
            print(f"   - OPC server polling interval is slower than your test interval")
            print(f"   - Tags are static/constant values")
            print(f"   - API is returning cached data")
        else:
            print(f"\n✅ Good data freshness - {changing_tags/total_tags*100:.0f}% of tags showing value updates")
    
    print(f"{'='*90}\n")
    return {
        'interval_ms': interval_ms,
        'avg_interval': statistics.mean(intervals) if intervals else 0,
        'avg_api_time': statistics.mean(api_times) if api_times else 0,
        'success_rate': (poll_count/(poll_count+errors)*100) if (poll_count+errors) > 0 else 0,
        'tag_change_rate': (changing_tags/total_tags*100) if tag_history else 0
    }

def check_connection():
    """Verify C# OPC service is running"""
    print(f"\n{'='*80}")
    print(f"🔌 CONNECTION CHECK")
    print(f"{'='*80}")
    
    try:
        # Check if API is alive
        response = requests.get(f"{API_BASE}/api/opc/status", timeout=2)
        if response.status_code == 200:
            print(f"✅ OPC Service Running: {API_BASE}")
            status = response.json()
            print(f"   Status: {status}")
            return True
        else:
            print(f"⚠️  API responded with status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to {API_BASE}")
        print(f"   Make sure your C# OPC service is running:")
        print(f"   > dotnet run")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    print(f"\n{'#'*90}")
    print(f"#  OPC MINIMUM POLLING FREQUENCY TEST")
    print(f"#  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*90}")
    
    # Check connection
    if not check_connection():
        print(f"\n❌ Test aborted - OPC service not running")
        return
    
    print(f"\n📋 TEST PLAN:")
    print(f"   Testing multiple polling intervals to find minimum frequency")
    print(f"   Each test runs for 15 seconds")
    print(f"\n⏳ Starting tests in 3 seconds...")
    time.sleep(3)
    
    # Test multiple intervals
    results = []
    test_intervals = [500, 1000, 2000]  # Test 500ms, 1s, 2s
    
    for interval in test_intervals:
        print(f"\n\n{'*'*90}")
        print(f"  TEST: {interval}ms Polling Interval")
        print(f"{'*'*90}")
        time.sleep(2)
        
        result = test_polling_frequency(duration=15, interval_ms=interval)
        results.append(result)
        
        if interval != test_intervals[-1]:
            print(f"\n⏸️  Pausing 3 seconds before next test...")
            time.sleep(3)
    
    # Final comparison
    print(f"\n{'='*90}")
    print(f"📊 FINAL COMPARISON - ALL INTERVALS")
    print(f"{'='*90}")
    print(f"{'Target':<10} {'Actual Avg':<12} {'API Time':<12} {'Success':<10} {'Tag Changes'}")
    print(f"{'-'*90}")
    
    for result in results:
        print(f"{result['interval_ms']:>5}ms    {result['avg_interval']:>7.0f}ms    "
              f"{result['avg_api_time']:>7.0f}ms    {result['success_rate']:>6.1f}%    "
              f"{result['tag_change_rate']:>6.1f}%")
    
    # Find minimum achievable
    fastest = min(results, key=lambda x: x['avg_interval'])
    print(f"\n🎯 MINIMUM ACHIEVABLE FREQUENCY:")
    print(f"   Best interval achieved: {fastest['avg_interval']:.0f}ms")
    print(f"   Tag change rate: {fastest['tag_change_rate']:.1f}%")
    print(f"   API response time: {fastest['avg_api_time']:.0f}ms")
    
    if fastest['avg_interval'] <= 550:
        print(f"\n✅ Your system CAN poll at ~500ms frequency!")
    elif fastest['avg_interval'] <= 1100:
        print(f"\n✅ Your system can poll at ~1000ms (1 second) frequency")
    else:
        print(f"\n⚠️  Your system is limited to ~{fastest['avg_interval']:.0f}ms polling")
    
    print(f"\n💡 RECOMMENDATIONS:")
    print(f"   - Configure OPC polling interval: {int(fastest['avg_interval'])}ms in appsettings.json")
    print(f"   - Database rate control can be different (slower) via Historian.RateControl.MinIntervalMs")
    print(f"   - Lower intervals = higher CPU/network load, choose based on your needs")
    
    print(f"\n✅ All tests complete!")

if __name__ == "__main__":
    main()
