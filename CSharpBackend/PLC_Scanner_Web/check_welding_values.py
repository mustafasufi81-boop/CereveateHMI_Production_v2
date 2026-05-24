import requests
import json

# Check API response
response = requests.get('http://localhost:7001/api/values')
data = response.json()

print(f"Total tags: {len(data)}")
print("\nWelding Parameters:")
welding_tags = ['Welding_Current_A', 'Welding_Voltage_V', 'Pipe_Id', 'WPS_ID', 'Joint_Id', 'Arc']

for tag in welding_tags:
    if tag in data:
        value = data[tag]
        print(f"  {tag}: {value}")
    else:
        print(f"  {tag}: NOT FOUND in API response")

print("\nAll tags in response:")
for tag_id in sorted(data.keys())[:10]:
    print(f"  {tag_id}: {data[tag_id]}")
