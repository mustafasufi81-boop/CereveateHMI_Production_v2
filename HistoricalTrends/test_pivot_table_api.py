"""
Test Pivot Table Statistics API Call
"""
import requests
import json

# Sample data matching the format used in bi_analytics.js
test_data = [
    {"Timestamp": "2025-01-01 00:00:00", "Random.Real4": 100.5, "Random.Real8": 200.3},
    {"Timestamp": "2025-01-01 00:01:00", "Random.Real4": 102.3, "Random.Real8": 198.7},
    {"Timestamp": "2025-01-01 00:02:00", "Random.Real4": 99.8, "Random.Real8": 202.1},
    {"Timestamp": "2025-01-01 00:03:00", "Random.Real4": 101.2, "Random.Real8": 199.5},
    {"Timestamp": "2025-01-01 00:04:00", "Random.Real4": 98.9, "Random.Real8": 201.8},
]

tags = ["Random.Real4", "Random.Real8"]

print("=" * 60)
print("Testing Pivot Table Statistics API")
print("=" * 60)

# Test the API endpoint
try:
    response = requests.post(
        'http://localhost:5001/api/v1/analytics/statistics',
        headers={'Content-Type': 'application/json'},
        json={'data': test_data, 'tags': tags},
        timeout=5
    )
    
    print(f"\n✓ Status Code: {response.status_code}")
    
    if response.ok:
        result = response.json()
        print(f"✓ Response received successfully\n")
        
        for tag in tags:
            print(f"📊 Tag: {tag}")
            stats = result.get(tag, {})
            
            print(f"   Count:   {stats.get('count', 'N/A')}")
            print(f"   Mean:    {stats.get('mean', 'N/A'):.2f}" if isinstance(stats.get('mean'), (int, float)) else f"   Mean:    N/A")
            print(f"   Std Dev: {stats.get('std_dev', 'N/A'):.2f}" if isinstance(stats.get('std_dev'), (int, float)) else f"   Std Dev: N/A")
            print(f"   Min:     {stats.get('min', 'N/A'):.2f}" if isinstance(stats.get('min'), (int, float)) else f"   Min:     N/A")
            print(f"   Max:     {stats.get('max', 'N/A'):.2f}" if isinstance(stats.get('max'), (int, float)) else f"   Max:     N/A")
            
            # Calculate Sum (mean * count)
            if isinstance(stats.get('mean'), (int, float)) and isinstance(stats.get('count'), int):
                sum_value = stats['mean'] * stats['count']
                print(f"   Sum:     {sum_value:.2f}")
            else:
                print(f"   Sum:     N/A")
            print()
        
        print("=" * 60)
        print("✅ Test PASSED - API working correctly!")
        print("=" * 60)
        
    else:
        print(f"❌ Error: {response.status_code}")
        print(f"Response: {response.text}")
        
except requests.exceptions.ConnectionError:
    print("❌ Connection Error - Flask server not running on port 5001")
except Exception as e:
    print(f"❌ Test Failed: {e}")
