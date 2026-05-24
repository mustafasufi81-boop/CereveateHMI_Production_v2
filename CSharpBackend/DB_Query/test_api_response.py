import requests
import json
from datetime import datetime, timedelta

# Test the actual API response
base_url = "http://localhost:7005"

# Test query for last 5 minutes
end_time = datetime.now()
start_time = end_time - timedelta(minutes=5)

params = {
    'start_time': start_time.strftime('%Y-%m-%d %H:%M:%S'),
    'end_time': end_time.strftime('%Y-%m-%d %H:%M:%S'),
    'tag_id': 'Welding_Current_A',
    'page': 1,
    'per_page': 10
}

print("Testing API endpoint...")
print(f"URL: {base_url}/api/query")
print(f"Params: {params}\n")

try:
    response = requests.get(f"{base_url}/api/query", params=params, timeout=10)
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ API Response SUCCESS\n")
        print(f"Total records: {data.get('total', 0)}")
        print(f"Records returned: {len(data.get('data', []))}\n")
        
        print("=" * 120)
        print("FIRST 10 TIMESTAMP FORMATS FROM API:")
        print("=" * 120)
        
        for i, record in enumerate(data.get('data', [])[:10], 1):
            timestamp = record.get('timestamp')
            value = record.get('value')
            
            print(f"\n{i}. Raw timestamp from API:")
            print(f"   {timestamp}")
            print(f"   Type: {type(timestamp)}")
            print(f"   Value: {value}")
            
            # Check if it has microseconds
            if '.' in str(timestamp):
                decimal_part = str(timestamp).split('.')[1].split('+')[0].split('Z')[0]
                print(f"   Decimal part: .{decimal_part} ({len(decimal_part)} digits)")
                
                if decimal_part == '000' or decimal_part == '000000':
                    print(f"   ❌ PROBLEM: Shows .000")
                else:
                    print(f"   ✅ Has milliseconds")
            else:
                print(f"   ❌ NO DECIMAL PART AT ALL")
        
        print("\n" + "=" * 120)
        print("\nRAW JSON RESPONSE (first record):")
        print(json.dumps(data.get('data', [])[0] if data.get('data') else {}, indent=2))
        
    else:
        print(f"❌ API Error: {response.status_code}")
        print(response.text)
        
except requests.exceptions.ConnectionError:
    print("❌ Cannot connect to server at localhost:7005")
    print("   Make sure historian_query_tool_v2.py is running")
except Exception as e:
    print(f"❌ Error: {e}")
