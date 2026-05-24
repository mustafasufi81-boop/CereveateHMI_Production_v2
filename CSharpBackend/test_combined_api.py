import requests
import json

print("\n" + "="*80)
print("TESTING COMBINED API: http://localhost:1202/api/opc/values")
print("="*80)

response = requests.get('http://localhost:1202/api/opc/values')
data = response.json()

print(f"\nTotal tags: {data['count']}")
print(f"Timestamp: {data.get('timestamp')}")
if 'warnings' in data:
    print(f"Warnings: {data['warnings']}")

print("\n" + "="*80)
print("WELDING TAGS IN RESPONSE:")
print("="*80)

welding_tags = [t for t in data['tags'] if any(x in t['tagId'] for x in ['Weld', 'Arc', 'Pipe', 'Joint', 'WPS', 'Power', 'sim_step', 'Welder'])]

for tag in welding_tags:
    print(f"\nTag ID: {tag['tagId']}")
    print(f"  Value: {tag.get('value')}")
    print(f"  Quality: {tag.get('quality')}")
    print(f"  Source: {tag.get('source', 'OPC')}")
    print(f"  Value is None: {tag.get('value') is None}")
    print(f"  Value type: {type(tag.get('value'))}")

print("\n" + "="*80)
