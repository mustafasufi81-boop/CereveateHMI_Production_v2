import requests
import json

# Test API timestamp format
url = "http://localhost:7005/api/data/query"
params = {
    'tag_id[]': 'Welding_Voltage_V',
    'page': 1,
    'page_size': 5
}

response = requests.get(url, params=params)
data = response.json()

print("="*100)
print("API RESPONSE TIMESTAMP FORMAT CHECK")
print("="*100)

if data['success']:
    print(f"\nTotal records: {data['count']}")
    print(f"Page: {data['page']}/{data['total_pages']}")
    print(f"\nFirst 5 timestamp values:")
    print("-"*100)
    
    for i, row in enumerate(data['data'][:5], 1):
        timestamp = row['timestamp']
        print(f"\n{i}. Raw timestamp from API: {timestamp}")
        print(f"   Type: {type(timestamp)}")
        print(f"   Tag: {row['tag_id']}")
        print(f"   Value: {row['value']}")
        print(f"   Quality: {row['quality']}")
        
        # Check if milliseconds are present
        if '.' in str(timestamp):
            parts = str(timestamp).split('.')
            fractional = parts[1].split('+')[0] if '+' in parts[1] else parts[1].split('-')[0] if '-' in parts[1] else parts[1]
            print(f"   Fractional seconds: .{fractional}")
            print(f"   Length: {len(fractional)} digits")
        else:
            print(f"   ⚠️  NO FRACTIONAL SECONDS!")
else:
    print(f"Error: {data.get('error')}")
