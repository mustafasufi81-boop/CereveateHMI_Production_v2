"""
Show Raw OPC Data Being Read
Displays actual values, timestamps, and change patterns
"""
import requests
import time
from datetime import datetime

API_BASE = "http://localhost:5001"
TAG_NAME = "Random.Int2"

def show_raw_data(duration=5, interval_ms=10):
    """Show raw OPC data as it's being read"""
    print(f"{'='*80}")
    print(f"RAW OPC DATA CAPTURE")
    print(f"Tag: {TAG_NAME}")
    print(f"Polling: {interval_ms}ms intervals")
    print(f"Duration: {duration}s")
    print(f"{'='*80}\n")
    
    print(f"{'Poll':<6} {'Time':<8} {'Value':<10} {'Changed':<10} {'Quality':<10} {'Timestamp'}")
    print(f"{'-'*80}")
    
    poll_count = 0
    last_value = None
    change_count = 0
    start_time = time.time()
    
    while time.time() - start_time < duration:
        poll_count += 1
        elapsed = time.time() - start_time
        
        try:
            response = requests.get(f"{API_BASE}/api/opc/values", timeout=2)
            if response.status_code == 200:
                data = response.json()
                tags = data.get('tags', [])
                
                # Find our tag
                tag_data = None
                for tag in tags:
                    tag_id = tag.get('tagId') or tag.get('TagId')
                    if tag_id == TAG_NAME:
                        tag_data = tag
                        break
                
                if tag_data:
                    value = tag_data.get('value') or tag_data.get('Value')
                    quality = tag_data.get('quality') or tag_data.get('Quality')
                    timestamp = tag_data.get('timestamp') or tag_data.get('Timestamp')
                    
                    changed = ""
                    if last_value is not None and value != last_value:
                        changed = "✓ CHANGE"
                        change_count += 1
                    
                    # Show timestamp (last 12 chars)
                    ts_short = str(timestamp)[-12:] if timestamp else "N/A"
                    
                    print(f"{poll_count:<6} {elapsed:>7.3f}s {value:<10} {changed:<10} {quality:<10} {ts_short}")
                    
                    last_value = value
                else:
                    print(f"{poll_count:<6} {elapsed:>7.3f}s TAG NOT FOUND")
            else:
                print(f"{poll_count:<6} {elapsed:>7.3f}s API ERROR: {response.status_code}")
        
        except Exception as e:
            print(f"{poll_count:<6} {elapsed:>7.3f}s ERROR: {str(e)[:40]}")
        
        time.sleep(interval_ms / 1000.0)
    
    print(f"\n{'-'*80}")
    print(f"SUMMARY:")
    print(f"  Total Polls: {poll_count}")
    print(f"  Value Changes: {change_count}")
    print(f"  Change Rate: {change_count/poll_count*100:.1f}%")
    print(f"  Avg Time Between Changes: {duration/change_count:.3f}s" if change_count > 0 else "  No changes detected")
    print(f"{'='*80}\n")

if __name__ == "__main__":
    print("\n🔍 Showing raw OPC data at different polling rates...\n")
    
    print("\n📊 TEST 1: 10ms Polling (very fast)")
    show_raw_data(duration=3, interval_ms=10)
    
    print("\n📊 TEST 2: 50ms Polling (fast)")
    show_raw_data(duration=3, interval_ms=50)
    
    print("\n📊 TEST 3: 100ms Polling (moderate)")
    show_raw_data(duration=3, interval_ms=100)
    
    print("\n✅ Raw data capture complete!")
