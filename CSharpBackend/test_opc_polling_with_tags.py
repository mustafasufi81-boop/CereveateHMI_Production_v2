"""
Test Script: OPC Minimum Polling Frequency with Tag Monitoring
This script:
1. Connects to OPC server
2. Browses and adds tags to monitor
3. Tests polling at different frequencies
4. Shows actual tag value changes
"""
import requests
import time
from datetime import datetime
import statistics
from collections import defaultdict
import json

# Your C# OPC Service API
API_BASE = "http://localhost:5001"

def check_connection():
    """Check if OPC service is running and connected"""
    try:
        response = requests.get(f"{API_BASE}/api/opc/status", timeout=2)
        if response.status_code == 200:
            status = response.json()
            print(f"✅ OPC Service Status:")
            print(f"   Connected: {status.get('connected')}")
            print(f"   Server: {status.get('serverName')}")
            print(f"   Tag Count: {status.get('tagCount')}")
            print(f"   Last Update: {status.get('lastUpdate')}")
            return status
        return None
    except Exception as e:
        print(f"❌ Error checking connection: {e}")
        return None

def connect_to_server(server_name="Matrikon.OPC.Simulation.1", polling_ms=500):
    """Connect to OPC server with specified polling interval"""
    try:
        print(f"\n🔌 Connecting to {server_name} with {polling_ms}ms polling...")
        
        payload = {
            "serverProgID": server_name,
            "pollingIntervalMs": polling_ms
        }
        
        response = requests.post(
            f"{API_BASE}/api/opcda/connect",
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Connected successfully!")
            print(f"   Connection ID: {result.get('connectionId')}")
            return True
        else:
            print(f"❌ Connection failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False

def browse_tags():
    """Browse available OPC tags"""
    try:
        print(f"\n📋 Browsing available tags...")
        response = requests.get(f"{API_BASE}/api/opcda/tags", timeout=10)
        
        if response.status_code == 200:
            tags = response.json()
            print(f"✅ Found {len(tags)} tags")
            
            # Filter only leaf tags (not folders)
            leaf_tags = [t for t in tags if not t.get('isFolder', False)]
            print(f"   Leaf tags (monitorable): {len(leaf_tags)}")
            
            return leaf_tags
        else:
            print(f"❌ Browse failed: {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ Browse error: {e}")
        return []

def add_tag_to_monitor(tag_id, display_name):
    """Add a single tag to monitoring"""
    try:
        payload = {
            "itemID": tag_id,
            "displayName": display_name
        }
        
        response = requests.post(
            f"{API_BASE}/api/opcda/tags/add",
            json=payload,
            timeout=5
        )
        
        if response.status_code == 200:
            return True
        else:
            print(f"⚠️  Failed to add tag {tag_id}: {response.status_code}")
            return False
    except Exception as e:
        print(f"⚠️  Error adding tag {tag_id}: {e}")
        return False

def add_multiple_tags(tags, max_tags=20):
    """Add multiple tags to monitoring"""
    print(f"\n➕ Adding tags to monitor (max {max_tags})...")
    
    added = 0
    for tag in tags[:max_tags]:
        tag_id = tag.get('itemID')
        name = tag.get('name', tag_id)
        
        if add_tag_to_monitor(tag_id, name):
            added += 1
            print(f"   ✅ {name}")
        
        time.sleep(0.1)  # Small delay between adds
    
    print(f"\n✅ Added {added} tags to monitoring")
    return added

def get_tag_values():
    """Get current tag values from OPC"""
    try:
        response = requests.get(f"{API_BASE}/api/opc/values", timeout=2)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        return None

def test_polling_frequency(duration=15, interval_ms=500):
    """Poll OPC at specified interval and measure performance"""
    print(f"\n{'='*100}")
    print(f"🔴 POLLING TEST - {interval_ms}ms INTERVAL")
    print(f"{'='*100}")
    print(f"Duration: {duration} seconds | Target: {interval_ms}ms")
    print(f"{'='*100}\n")
    
    interval_sec = interval_ms / 1000
    start_time = time.time()
    poll_count = 0
    intervals = []
    api_times = []
    errors = 0
    
    # Track tag value changes
    tag_history = defaultdict(list)
    value_changes = defaultdict(int)
    
    last_poll = time.time()
    
    print(f"{'Time':<8} {'Poll':<5} {'Interval':<10} {'API':<8} {'Tags':<5} {'Changes':<8} {'Status'}")
    print(f"{'-'*100}")
    
    while (time.time() - start_time) < duration:
        poll_start = time.time()
        data = get_tag_values()
        poll_end = time.time()
        
        actual_interval = (poll_start - last_poll) * 1000
        api_time = (poll_end - poll_start) * 1000
        
        if data:
            poll_count += 1
            intervals.append(actual_interval)
            api_times.append(api_time)
            
            # Extract tags
            tags = data.get('tags', [])
            
            # Track value changes
            changes = 0
            for tag in tags:
                tag_id = tag.get('tagId') or tag.get('TagId')
                value = tag.get('value') or tag.get('Value')
                
                if tag_id:
                    history = tag_history[tag_id]
                    if len(history) > 0 and history[-1] != value:
                        value_changes[tag_id] += 1
                        changes += 1
                    history.append(value)
            
            elapsed = time.time() - start_time
            status = "✅" if api_time < interval_ms else "⚠️"
            
            print(f"{elapsed:>5.1f}s  {poll_count:<5} {actual_interval:>7.0f}ms  {api_time:>5.0f}ms  {len(tags):<5} {changes:<8} {status}")
        else:
            errors += 1
            elapsed = time.time() - start_time
            print(f"{elapsed:>5.1f}s  ERROR -          -        -     -        ❌")
        
        last_poll = poll_start
        
        # Sleep until next poll
        sleep_time = interval_sec - (time.time() - poll_start)
        if sleep_time > 0:
            time.sleep(sleep_time)
    
    # Summary
    print(f"\n{'='*100}")
    print(f"📊 RESULTS - {interval_ms}ms Target")
    print(f"{'='*100}")
    print(f"Total Polls:          {poll_count}")
    print(f"Errors:               {errors}")
    print(f"Success Rate:         {(poll_count/(poll_count+errors)*100):.1f}%")
    
    if intervals:
        avg_interval = statistics.mean(intervals)
        avg_api = statistics.mean(api_times)
        
        print(f"\n⏱️  TIMING:")
        print(f"Target Interval:      {interval_ms}ms")
        print(f"Actual Avg Interval:  {avg_interval:.0f}ms")
        print(f"Actual Min/Max:       {min(intervals):.0f}ms / {max(intervals):.0f}ms")
        print(f"Std Deviation:        {statistics.stdev(intervals):.0f}ms" if len(intervals) > 1 else "N/A")
        print(f"\nAPI Response Time:    {avg_api:.0f}ms (min: {min(api_times):.0f}ms, max: {max(api_times):.0f}ms)")
        
        tolerance = interval_ms * 0.1
        if abs(avg_interval - interval_ms) <= tolerance:
            print(f"\n✅ SUCCESS: Achieved ~{interval_ms}ms polling!")
        elif avg_interval < (interval_ms - tolerance):
            print(f"\n⚠️  Polling faster than target: {avg_interval:.0f}ms")
        else:
            print(f"\n❌ Polling slower than target: {avg_interval:.0f}ms")
    
    # Value freshness
    if tag_history:
        total_tags = len(tag_history)
        changing_tags = sum(1 for count in value_changes.values() if count > 0)
        
        print(f"\n📈 TAG VALUE FRESHNESS:")
        print(f"Total Tags:           {total_tags}")
        print(f"Tags with Changes:    {changing_tags} ({changing_tags/total_tags*100:.1f}%)")
        
        if changing_tags > 0:
            print(f"\n🔄 Most Active Tags:")
            sorted_tags = sorted(value_changes.items(), key=lambda x: x[1], reverse=True)[:5]
            for tag_id, count in sorted_tags:
                rate = (count / poll_count * 100) if poll_count > 0 else 0
                print(f"   {tag_id}: {count} changes ({rate:.0f}% of polls)")
        
        if changing_tags == 0:
            print(f"\n⚠️  WARNING: NO tag values changed!")
            print(f"   Possible reasons:")
            print(f"   - Tags are constant values")
            print(f"   - OPC server update rate is slower than polling")
            print(f"   - Need to monitor different tags (e.g., Random.* tags)")
    
    print(f"{'='*100}\n")
    
    return {
        'interval_ms': interval_ms,
        'avg_interval': statistics.mean(intervals) if intervals else 0,
        'avg_api_time': statistics.mean(api_times) if api_times else 0,
        'success_rate': (poll_count/(poll_count+errors)*100) if (poll_count+errors) > 0 else 0,
        'tag_change_rate': (changing_tags/total_tags*100) if tag_history else 0,
        'total_tags': len(tag_history),
        'changing_tags': changing_tags if tag_history else 0
    }

def main():
    print(f"\n{'#'*100}")
    print(f"#  OPC POLLING FREQUENCY TEST WITH TAG MONITORING")
    print(f"#  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*100}")
    
    # Step 1: Check initial connection
    print(f"\n{'='*100}")
    print(f"STEP 1: CHECK CONNECTION")
    print(f"{'='*100}")
    
    status = check_connection()
    if not status:
        print(f"\n❌ OPC service not running! Start with: dotnet run")
        return
    
    # If already connected and has tags, ask if user wants to reconnect
    if status.get('connected') and status.get('tagCount', 0) > 0:
        print(f"\n✅ Already connected with {status.get('tagCount')} monitored tags")
        print(f"   Proceeding with existing connection...")
        time.sleep(2)
    else:
        # Step 2: Connect with desired polling interval
        print(f"\n{'='*100}")
        print(f"STEP 2: CONNECT TO OPC SERVER")
        print(f"{'='*100}")
        
        polling_interval = 500  # Start with 500ms
        if not connect_to_server(polling_ms=polling_interval):
            print(f"\n❌ Failed to connect!")
            return
        
        time.sleep(2)
        
        # Step 3: Browse and add tags
        print(f"\n{'='*100}")
        print(f"STEP 3: BROWSE AND ADD TAGS")
        print(f"{'='*100}")
        
        tags = browse_tags()
        if not tags:
            print(f"\n⚠️  No tags found! Using simulation server?")
            return
        
        # Prioritize Random.* tags (they change frequently)
        random_tags = [t for t in tags if 'Random' in t.get('name', '')]
        other_tags = [t for t in tags if 'Random' not in t.get('name', '')]
        
        print(f"\n   Found {len(random_tags)} Random.* tags (high-frequency)")
        print(f"   Found {len(other_tags)} other tags")
        
        # Add Random tags first, then others
        tags_to_add = random_tags[:10] + other_tags[:10]
        
        if add_multiple_tags(tags_to_add, max_tags=20) == 0:
            print(f"\n❌ No tags added!")
            return
        
        time.sleep(2)
        
        # Verify tags were added
        status = check_connection()
        if status and status.get('tagCount', 0) > 0:
            print(f"\n✅ Ready to test with {status.get('tagCount')} monitored tags")
        else:
            print(f"\n❌ Tags were not added successfully!")
            return
    
    # Step 4: Run polling tests
    print(f"\n{'='*100}")
    print(f"STEP 4: RUN POLLING FREQUENCY TESTS")
    print(f"{'='*100}")
    
    print(f"\n⏳ Starting tests in 3 seconds...")
    time.sleep(3)
    
    # Test multiple intervals
    results = []
    test_intervals = [500, 1000, 2000]
    
    for interval in test_intervals:
        print(f"\n\n{'*'*100}")
        print(f"  TESTING {interval}ms POLLING INTERVAL")
        print(f"{'*'*100}")
        time.sleep(2)
        
        result = test_polling_frequency(duration=15, interval_ms=interval)
        results.append(result)
        
        if interval != test_intervals[-1]:
            print(f"\n⏸️  Pausing 3 seconds before next test...")
            time.sleep(3)
    
    # Final comparison
    print(f"\n{'='*100}")
    print(f"📊 FINAL COMPARISON")
    print(f"{'='*100}")
    print(f"{'Target':<8} {'Actual':<10} {'API Time':<10} {'Success':<10} {'Tags':<8} {'Changing':<10} {'Change %'}")
    print(f"{'-'*100}")
    
    for r in results:
        print(f"{r['interval_ms']:>5}ms  {r['avg_interval']:>7.0f}ms  {r['avg_api_time']:>7.0f}ms  "
              f"{r['success_rate']:>7.1f}%  {r['total_tags']:>5}    {r['changing_tags']:>7}    "
              f"{r['tag_change_rate']:>6.1f}%")
    
    # Find best result
    fastest = min(results, key=lambda x: x['avg_interval'])
    most_changes = max(results, key=lambda x: x['tag_change_rate'])
    
    print(f"\n🎯 CONCLUSIONS:")
    print(f"   Fastest polling achieved:     {fastest['avg_interval']:.0f}ms")
    print(f"   Best tag update rate:         {most_changes['tag_change_rate']:.1f}% at {most_changes['interval_ms']}ms")
    
    if fastest['avg_interval'] <= 550:
        print(f"\n✅ Your system CAN poll at 500ms frequency!")
    elif fastest['avg_interval'] <= 1100:
        print(f"\n✅ Your system can reliably poll at 1000ms frequency")
    else:
        print(f"\n⚠️  Recommended polling interval: {int(fastest['avg_interval'])}ms")
    
    if most_changes['tag_change_rate'] < 10:
        print(f"\n⚠️  Low tag change rate - consider monitoring different tags or check OPC server update rate")
    
    print(f"\n💡 RECOMMENDATIONS:")
    print(f"   - Configure OPC polling: {int(fastest['avg_interval'])}ms in connection")
    print(f"   - DB rate control: Keep at 1000ms+ via Historian.RateControl.MinIntervalMs")
    print(f"   - Monitor Random.* tags for high-frequency test data")
    
    print(f"\n✅ All tests complete!\n")

if __name__ == "__main__":
    main()
