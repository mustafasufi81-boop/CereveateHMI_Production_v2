"""
Test if Start button is working - Check what happens when polling starts
"""
import requests
import time

print("=" * 70)
print("TESTING START BUTTON FUNCTIONALITY")
print("=" * 70)

# Get the tags that should be available
print("\n1. Getting available tags...")
response = requests.get("http://localhost:1202/api/tags/enabled")
tags_data = response.json()
print(f"   Found {len(tags_data.get('tags', []))} tags")

# Show tags with "Saw-toothed" in name
print("\n2. Tags matching 'Saw-toothed Waves':")
for tag in tags_data.get('tags', []):
    if 'Saw-toothed Waves' in tag.get('tagId', ''):
        print(f"   - {tag.get('tagId')}")

# Get current values
print("\n3. Getting current OPC values...")
response = requests.get("http://localhost:1202/api/opc/values")
opc_data = response.json()

# Create a map for easy lookup
value_map = {}
for tag in opc_data.get('tags', []):
    value_map[tag['tagId']] = tag['value']

# Check specific tags
print("\n4. Checking selected tags:")
test_tags = [
    "Blastfurnace_Tuyer1_Pressure",
    "Saw-toothed Waves.Int4", 
    "Saw-toothed Waves.Int2"
]

for tag_id in test_tags:
    if tag_id in value_map:
        print(f"   ✅ {tag_id} = {value_map[tag_id]}")
    else:
        print(f"   ❌ {tag_id} NOT FOUND")
        # Try to find similar
        print(f"      Looking for similar tags...")
        for key in value_map.keys():
            if tag_id.replace('_', ' ').lower() in key.lower() or \
               key.replace('.', ' ').lower() in tag_id.lower():
                print(f"      Did you mean: '{key}' = {value_map[key]}?")
                break

print("\n5. Testing the data conversion logic:")
print("   The JavaScript should do:")
print("   ```")
print("   const data = {};")
print("   apiData.tags.forEach(tag => {")
print("       data[tag.tagId] = tag.value;")
print("   });")
print("   ```")

print("\n6. Simulating selectedTags.forEach loop:")
for tag_id in test_tags:
    print(f"   selectedTags.forEach: checking '{tag_id}'")
    if tag_id in value_map:
        print(f"      ✅ data['{tag_id}'] = {value_map[tag_id]}")
        print(f"      Will add to chart and currentValues")
    else:
        print(f"      ❌ data['{tag_id}'] is undefined")
        print(f"      Will NOT add to chart (skipped)")

print("\n" + "=" * 70)
print("DIAGNOSIS:")
print("=" * 70)

all_found = all(tag_id in value_map for tag_id in test_tags)
if all_found:
    print("✅ All selected tags exist in API response")
    print("✅ The Start button should work")
    print("\n💡 If values still show '---', check browser console for errors")
else:
    print("❌ Some selected tags don't exist in API")
    print("\n💡 Make sure the tag IDs in the UI exactly match the API tag IDs")
    print("   Tag IDs are case-sensitive and include dots/spaces")

print("=" * 70)
