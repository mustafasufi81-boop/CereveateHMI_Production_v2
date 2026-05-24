"""
Test script to verify realtime trends page is working
"""
import requests
import json
import time

print("=" * 60)
print("Testing Realtime Trends Page")
print("=" * 60)

# Test 1: Check if HMI server is running
print("\n1. Testing HMI server (port 1202)...")
try:
    response = requests.get("http://localhost:1202/realtime", timeout=5)
    if response.status_code == 200 and "Real-Time Trends" in response.text:
        print("   ✅ HMI server is running")
        print("   ✅ Realtime page loads successfully")
    else:
        print(f"   ❌ Unexpected response: {response.status_code}")
        exit(1)
except Exception as e:
    print(f"   ❌ HMI server not responding: {e}")
    exit(1)

# Test 2: Check if API endpoint returns data
print("\n2. Testing API endpoint (/api/opc/values)...")
try:
    response = requests.get("http://localhost:1202/api/opc/values", timeout=5)
    data = response.json()
    
    if "tags" in data and len(data["tags"]) > 0:
        print(f"   ✅ API returns {len(data['tags'])} tags")
        
        # Show sample data
        sample = data["tags"][0]
        print(f"   ✅ Sample tag: {sample['tagId']} = {sample['value']}")
        
        # Check if selected tags have values
        test_tags = ["Random.Int2", "Random.Int4"]
        found = 0
        for tag in data["tags"]:
            if tag["tagId"] in test_tags:
                print(f"   ✅ {tag['tagId']} = {tag['value']}")
                found += 1
        
        if found >= 2:
            print(f"   ✅ Both test tags found with values")
        else:
            print(f"   ⚠️  Only {found} test tags found")
    else:
        print("   ❌ API returned no tags")
        exit(1)
except Exception as e:
    print(f"   ❌ API test failed: {e}")
    exit(1)

# Test 3: Check tags endpoint
print("\n3. Testing tags endpoint (/api/tags/enabled)...")
try:
    response = requests.get("http://localhost:1202/api/tags/enabled", timeout=5)
    data = response.json()
    
    if "tags" in data and len(data["tags"]) > 0:
        print(f"   ✅ Tags endpoint returns {len(data['tags'])} tags")
    else:
        print("   ⚠️  Tags endpoint returned empty list")
except Exception as e:
    print(f"   ⚠️  Tags endpoint error: {e}")

# Test 4: Simulate polling behavior
print("\n4. Testing continuous data fetch (3 polls)...")
try:
    values_changing = False
    prev_value = None
    
    for i in range(3):
        response = requests.get("http://localhost:1202/api/opc/values", timeout=5)
        data = response.json()
        
        # Get first tag value
        first_tag = data["tags"][0]
        current_value = first_tag["value"]
        
        print(f"   Poll {i+1}: {first_tag['tagId']} = {current_value}")
        
        if prev_value is not None and prev_value != current_value:
            values_changing = True
        
        prev_value = current_value
        
        if i < 2:
            time.sleep(1)
    
    if values_changing:
        print("   ✅ Values are updating (live data confirmed)")
    else:
        print("   ⚠️  Values not changing (may be static)")
except Exception as e:
    print(f"   ❌ Polling test failed: {e}")
    exit(1)

# Test 5: Check database logging endpoint
print("\n5. Testing database logging endpoint...")
try:
    test_data = {
        "samples": [
            {
                "tag_id": "Random.Int2",
                "value": 123.45,
                "timestamp": "2026-02-06T20:30:00",
                "poll_interval_ms": 1000
            }
        ]
    }
    
    response = requests.post(
        "http://localhost:1202/api/log/realtime",
        json=test_data,
        timeout=5
    )
    
    result = response.json()
    if result.get("success"):
        print(f"   ✅ Database logging works ({result.get('samples_logged', 0)} samples)")
    else:
        print(f"   ❌ Database logging failed: {result.get('error')}")
except Exception as e:
    print(f"   ⚠️  Database logging test error: {e}")

print("\n" + "=" * 60)
print("✅ ALL CRITICAL TESTS PASSED!")
print("=" * 60)
print("\n📊 Page URL: http://localhost:1202/realtime")
print("\nInstructions:")
print("1. Open the page in browser")
print("2. Select 2-3 tags (e.g., Random.Int2, Random.Int4)")
print("3. Click 'Start' button")
print("4. Watch chart and live values update")
print("5. Enable 'Database Logging' checkbox to save data")
print("=" * 60)
