import requests
from datetime import datetime

# Test API query
url = 'http://localhost:7005/api/data/query'
params = {
    'tag_id[]': 'Welding_Current_A',
    'page': 1,
    'page_size': 5
}

print("=" * 80)
print("🧪 TESTING API - ORDER BY DESC & TIMESTAMP FORMAT")
print("=" * 80)

response = requests.get(url, params=params)
data = response.json()

print(f"✅ Success: {data['success']}")
print(f"📊 Total Records: {data['total_records']}")
print(f"📄 Page: {data['page']} of {data['total_pages']}")
print(f"⏱️ Query Time: {data['execution_time_ms']}ms")
print()

print("🔍 First 5 Records (Should be LATEST first with milliseconds):")
print("-" * 80)

for i, row in enumerate(data['data'], 1):
    # Parse timestamp to show with milliseconds
    ts = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
    ts_with_ms = ts.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    
    print(f"{i}. {ts_with_ms} | {row['tag_id']} = {row['value']:.3f} | Quality={row['quality']}")

print()

# Check if newest is first
if len(data['data']) > 1:
    first_ts = datetime.fromisoformat(data['data'][0]['timestamp'].replace('Z', '+00:00'))
    last_ts = datetime.fromisoformat(data['data'][-1]['timestamp'].replace('Z', '+00:00'))
    
    if first_ts > last_ts:
        print("✅ PASS: ORDER BY DESC working correctly (newest first)")
    else:
        print("❌ FAIL: ORDER BY ASC detected (oldest first) - NEED TO FIX!")
else:
    print("⚠️ Not enough data to verify order")

print("=" * 80)
