import requests
import json

# Get values from API
response = requests.get('http://localhost:7001/api/values')
values = response.json()

print(f"\n{'='*80}")
print(f"CACHE STATUS - Total tags returned: {len(values)}")
print(f"{'='*80}\n")

# Check how many have actual values vs "---"
tags_with_values = []
tags_with_no_values = []

for tag in values:
    tag_id = tag.get('tag_id', '')
    value = tag.get('value', '')
    
    if value == "---" or value == "" or value is None:
        tags_with_no_values.append(tag_id)
    else:
        tags_with_values.append((tag_id, value))

print(f"✅ Tags WITH values: {len(tags_with_values)}")
if tags_with_values:
    for tag_id, value in tags_with_values[:10]:  # Show first 10
        print(f"   {tag_id}: {value}")
    if len(tags_with_values) > 10:
        print(f"   ... and {len(tags_with_values) - 10} more")

print(f"\n❌ Tags WITHOUT values (showing '---'): {len(tags_with_no_values)}")
if tags_with_no_values:
    for tag_id in tags_with_no_values[:20]:  # Show first 20
        print(f"   {tag_id}")
    if len(tags_with_no_values) > 20:
        print(f"   ... and {len(tags_with_no_values) - 20} more")

print(f"\n{'='*80}")
print(f"SUMMARY: {len(tags_with_values)} working, {len(tags_with_no_values)} not working")
print(f"{'='*80}\n")
