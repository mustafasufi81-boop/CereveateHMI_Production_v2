"""
Test Minimum Polling Frequency for a Single Tag
Tests: Random.Int2 (updates faster than Saw-tooth)
Shows actual value changes at different polling intervals
"""
import requests
import time
from datetime import datetime
import statistics

API_BASE = "http://localhost:5001"
TAG_NAME = "Random.Int2"

def get_tag_value():
    """Get current value for specific tag from OPC pool"""
    try:
        response = requests.get(f"{API_BASE}/api/opc/values", timeout=2)
        if response.status_code == 200:
            data = response.json()
            tags = data.get('tags', [])
            
            # Find our specific tag
            for tag in tags:
                tag_id = tag.get('tagId') or tag.get('TagId')
                if tag_id == TAG_NAME:
                    return {
                        'value': tag.get('value') or tag.get('Value'),
                        'quality': tag.get('quality') or tag.get('Quality'),
                        'timestamp': tag.get('timestamp') or tag.get('Timestamp')
                    }
            return None
        return None
    except Exception as e:
        print(f"❌ API Error: {e}")
        return None

def test_tag_polling(duration=10, interval_ms=500):
    """Poll single tag at specified interval"""
    print(f"\n{'='*90}")
    print(f"🔴 POLLING TEST: {TAG_NAME}")
    print(f"{'='*90}")
    print(f"Duration: {duration}s | Target Interval: {interval_ms}ms")
    print(f"{'='*90}\n")
    
    interval_sec = interval_ms / 1000
    start_time = time.time()
    
    # Tracking
    poll_count = 0
    successful_reads = 0
    intervals = []
    api_times = []
    values = []
    value_changes = 0
    last_value = None
    last_poll_time = time.time()
    
    print(f"{'Time':<8} {'Poll':<5} {'Interval':<10} {'API':<8} {'Value':<12} {'Changed':<8} {'Quality'}")
    print(f"{'-'*90}")
    
    while (time.time() - start_time) < duration:
        poll_start = time.time()
        
        # Fetch tag value
        tag_data = get_tag_value()
        
        poll_end = time.time()
        actual_interval = (poll_start - last_poll_time) * 1000
        api_time = (poll_end - poll_start) * 1000
        
        poll_count += 1
        intervals.append(actual_interval)
        api_times.append(api_time)
        
        if tag_data:
            successful_reads += 1
            current_value = tag_data['value']
            quality = tag_data['quality']
            
            values.append(current_value)
            
            # Detect value change
            changed = ""
            if last_value is not None and current_value != last_value:
                value_changes += 1
                changed = "✓"
            
            elapsed = time.time() - start_time
            print(f"{elapsed:>5.1f}s  {poll_count:<5} {actual_interval:>7.0f}ms  {api_time:>5.0f}ms  {str(current_value):<12} {changed:<8} {quality}")
            
            last_value = current_value
        else:
            elapsed = time.time() - start_time
            print(f"{elapsed:>5.1f}s  {poll_count:<5} {actual_interval:>7.0f}ms  {api_time:>5.0f}ms  NOT FOUND   -        -")
        
        last_poll_time = poll_start
        
        # Sleep until next poll
        sleep_time = interval_sec - (time.time() - poll_start)
        if sleep_time > 0:
            time.sleep(sleep_time)
    
    # Results
    print(f"\n{'='*90}")
    print(f"📊 RESULTS - {TAG_NAME}")
    print(f"{'='*90}")
    print(f"Total Polls:           {poll_count}")
    print(f"Successful Reads:      {successful_reads}")
    print(f"Success Rate:          {(successful_reads/poll_count*100):.1f}%")
    
    if intervals:
        avg_interval = statistics.mean(intervals)
        avg_api = statistics.mean(api_times)
        
        print(f"\n⏱️  TIMING:")
        print(f"Target Interval:       {interval_ms}ms")
        print(f"Actual Avg Interval:   {avg_interval:.0f}ms")
        print(f"Min/Max Interval:      {min(intervals):.0f}ms / {max(intervals):.0f}ms")
        print(f"Std Deviation:         {statistics.stdev(intervals):.0f}ms" if len(intervals) > 1 else "N/A")
        print(f"\nAPI Response Time:     {avg_api:.0f}ms (min: {min(api_times):.0f}ms, max: {max(api_times):.0f}ms)")
        
        # Check if target achieved
        tolerance = interval_ms * 0.1
        if abs(avg_interval - interval_ms) <= tolerance:
            print(f"\n✅ SUCCESS: Achieved ~{interval_ms}ms polling!")
        elif avg_interval < (interval_ms - tolerance):
            print(f"\n⚠️  Polling faster than target: {avg_interval:.0f}ms")
        else:
            print(f"\n❌ Polling slower than target: {avg_interval:.0f}ms")
    
    # Value analysis
    if successful_reads > 0:
        print(f"\n📈 TAG VALUE ANALYSIS:")
        print(f"Total Value Changes:   {value_changes}")
        print(f"Change Rate:           {(value_changes/successful_reads*100):.1f}% of polls")
        
        if values:
            unique_values = len(set(values))
            print(f"Unique Values Seen:    {unique_values}")
            print(f"Value Range:           {min(values)} to {max(values)}")
            
            if value_changes > 0:
                print(f"\n✅ Tag is CHANGING - good for testing!")
                print(f"   Values changed {value_changes} times in {duration}s")
                avg_change_interval = (duration / value_changes) if value_changes > 0 else 0
                print(f"   Average change every {avg_change_interval:.2f}s")
            else:
                print(f"\n⚠️  Tag value is STATIC (constant: {last_value})")
                print(f"   This is OK for timing tests, but can't verify freshness")
    else:
        print(f"\n❌ Tag NOT FOUND in OPC pool!")
        print(f"   Make sure '{TAG_NAME}' is added to monitoring")
    
    print(f"{'='*90}\n")
    
    return {
        'interval_ms': interval_ms,
        'avg_interval': statistics.mean(intervals) if intervals else 0,
        'avg_api_time': statistics.mean(api_times) if api_times else 0,
        'success_rate': (successful_reads/poll_count*100) if poll_count > 0 else 0,
        'value_changes': value_changes,
        'tag_found': successful_reads > 0
    }

def check_tag_exists():
    """Check if the tag exists in OPC pool"""
    print(f"\n🔍 Checking if '{TAG_NAME}' is in OPC pool...")
    
    try:
        response = requests.get(f"{API_BASE}/api/opc/values", timeout=2)
        if response.status_code == 200:
            data = response.json()
            tags = data.get('tags', [])
            
            # Look for our tag
            found = None
            for tag in tags:
                tag_id = tag.get('tagId') or tag.get('TagId')
                if tag_id == TAG_NAME:
                    found = tag
                    break
            
            if found:
                print(f"✅ Tag FOUND in pool!")
                print(f"   Current Value: {found.get('value')}")
                print(f"   Quality: {found.get('quality')}")
                print(f"   Total tags in pool: {len(tags)}")
                return True
            else:
                print(f"❌ Tag NOT FOUND in pool")
                print(f"   Total tags in pool: {len(tags)}")
                
                if len(tags) > 0:
                    print(f"\n   Available tags (first 10):")
                    for i, tag in enumerate(tags[:10]):
                        tag_id = tag.get('tagId') or tag.get('TagId')
                        print(f"      {i+1}. {tag_id}")
                else:
                    print(f"\n   ⚠️  Pool is EMPTY - no tags are monitored!")
                    print(f"   💡 Add '{TAG_NAME}' via web UI: http://localhost:5001")
                
                return False
        else:
            print(f"❌ API error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Connection error: {e}")
        print(f"💡 Make sure C# service is running: dotnet run")
        return False

def main():
    print(f"\n{'#'*90}")
    print(f"#  SINGLE TAG MINIMUM POLLING FREQUENCY TEST")
    print(f"#  Tag: {TAG_NAME}")
    print(f"#  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*90}")
    
    # Check if tag exists first
    if not check_tag_exists():
        print(f"\n❌ Cannot proceed - tag not found in OPC pool")
        print(f"\n💡 Next steps:")
        print(f"   1. Open http://localhost:5001 in browser")
        print(f"   2. Browse OPC tags")
        print(f"   3. Find and add '{TAG_NAME}' to monitoring")
        print(f"   4. Run this script again")
        return
    
    print(f"\n✅ Ready to test!")
    print(f"\n⏳ Starting tests in 3 seconds...\n")
    time.sleep(3)
    
    # Test multiple intervals - extreme speed test
    results = []
    test_intervals = [1, 5, 10]
    
    for interval in test_intervals:
        print(f"\n{'*'*90}")
        print(f"  TEST #{len(results)+1}: {interval}ms Polling Interval")
        print(f"{'*'*90}")
        time.sleep(2)
        
        result = test_tag_polling(duration=10, interval_ms=interval)
        results.append(result)
        
        if interval != test_intervals[-1]:
            print(f"\n⏸️  Pausing 3 seconds before next test...")
            time.sleep(3)
    
    # Final comparison
    print(f"\n{'='*90}")
    print(f"📊 FINAL COMPARISON - ALL INTERVALS")
    print(f"{'='*90}")
    print(f"{'Target':<10} {'Actual':<10} {'API Time':<10} {'Success':<10} {'Changes':<10} {'Tag Found'}")
    print(f"{'-'*90}")
    
    for r in results:
        found_str = "YES" if r['tag_found'] else "NO"
        print(f"{r['interval_ms']:>5}ms    {r['avg_interval']:>7.0f}ms  {r['avg_api_time']:>7.0f}ms  "
              f"{r['success_rate']:>7.1f}%  {r['value_changes']:>8}    {found_str}")
    
    # Determine minimum frequency
    successful_results = [r for r in results if r['tag_found']]
    
    if successful_results:
        fastest = min(successful_results, key=lambda x: x['avg_interval'])
        most_changes = max(successful_results, key=lambda x: x['value_changes'])
        
        print(f"\n🎯 CONCLUSIONS:")
        print(f"   Fastest polling achieved:  {fastest['avg_interval']:.0f}ms")
        print(f"   Most value changes:        {most_changes['value_changes']} at {most_changes['interval_ms']}ms")
        
        if fastest['avg_interval'] <= 550:
            print(f"\n✅ YOUR SYSTEM CAN POLL AT 500ms (0.5 SECOND) FREQUENCY!")
        elif fastest['avg_interval'] <= 1100:
            print(f"\n✅ Your system can reliably poll at 1000ms (1 second)")
        else:
            print(f"\n⚠️  Recommended minimum: {int(fastest['avg_interval'])}ms")
        
        print(f"\n💡 CONFIGURATION:")
        print(f"   - API endpoint: GET {API_BASE}/api/opc/values")
        print(f"   - Minimum interval: {int(fastest['avg_interval'])}ms")
        print(f"   - API response time: {fastest['avg_api_time']:.0f}ms")
        print(f"   - Tag tested: {TAG_NAME}")
    else:
        print(f"\n❌ No successful tests - tag not found in any test")
    
    print(f"\n✅ All tests complete!\n")

if __name__ == "__main__":
    main()
