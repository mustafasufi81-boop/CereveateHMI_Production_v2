import requests
import time

time.sleep(2)  # Wait for server to be ready

print("\n🔍 TESTING API ENDPOINTS\n")
print("=" * 80)

try:
    # Test /api/values
    print("\n1. Testing /api/values endpoint...")
    r = requests.get('http://localhost:7001/api/values', timeout=5)
    values = r.json()
    print(f"   Status: {r.status_code}")
    print(f"   Total values returned: {len(values)}")
    
    if len(values) == 0:
        print("   ❌ NO VALUES RETURNED!")
    else:
        print(f"   ✅ Values are being returned")
        print("\n   Sample values:")
        for i, (tag_id, data) in enumerate(list(values.items())[:5]):
            value = data.get('value', 'N/A')
            timestamp = data.get('timestamp', 'N/A')
            print(f"     - {tag_id}: {value} @ {timestamp}")
    
    # Test /api/tags
    print("\n2. Testing /api/tags endpoint...")
    r = requests.get('http://localhost:7001/api/tags', timeout=5)
    tags = r.json()
    print(f"   Status: {r.status_code}")
    print(f"   Total tags returned: {len(tags)}")
    
    # Test /api/stats
    print("\n3. Testing /api/stats endpoint...")
    r = requests.get('http://localhost:7001/api/stats', timeout=5)
    stats = r.json()
    print(f"   Status: {r.status_code}")
    print(f"   Cache size: {stats.get('cache_size', 'N/A')}")
    print(f"   Tags with data: {stats.get('tags_with_data', 'N/A')}")
    print(f"   PLC errors: {stats.get('plc_errors', 'N/A')}")
    
    print("\n" + "=" * 80)
    
    if len(values) == 0:
        print("\n⚠️  PROBLEM: API is running but returning NO VALUES")
        print("   Possible causes:")
        print("   1. PLC scanner thread not reading values")
        print("   2. Cache not being populated")
        print("   3. PLC connection issue")
    else:
        print("\n✅ API is working correctly!")

except requests.exceptions.ConnectionError:
    print("   ❌ ERROR: Cannot connect to http://localhost:7001")
    print("   Make sure plc_scanner_web.py is running!")
except Exception as e:
    print(f"   ❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
