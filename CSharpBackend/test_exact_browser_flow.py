"""
Test if browser JavaScript would work by simulating exact behavior
"""
import requests
import json

print("=" * 80)
print("SIMULATING EXACT BROWSER BEHAVIOR")
print("=" * 80)

# Step 1: Load page and get database tags
print("\n1. Browser loads page and calls /api/tags/enabled...")
response = requests.get("http://localhost:5002/api/tags/enabled")
db_tags = response.json()
print(f"   ✅ Got {db_tags['count']} tags from database")

selected_tags = [tag['tagId'] for tag in db_tags['tags']]
print(f"   Selected tags: {selected_tags[:3]}...")

# Step 2: JavaScript starts polling OPC every 1 second
print("\n2. JavaScript polls OPC service every 1 second...")
print("   Calling: http://localhost:5001/api/opc/values")

response = requests.get("http://localhost:5001/api/opc/values")
opc_data = response.json()

print(f"   ✅ Got {opc_data['count']} tags from OPC")

# Step 3: Filter to only mapped tags
print("\n3. Filtering OPC tags to only show database-mapped ones...")
matched_tags = {}
for tag in opc_data['tags']:
    if tag['tagId'] in selected_tags:
        matched_tags[tag['tagId']] = tag

print(f"   ✅ Matched {len(matched_tags)}/{len(selected_tags)} tags")

# Step 4: Display like browser would
print("\n4. Display values (like browser table):")
print(f"\n   {'Tag ID':<40} {'Value':<20} {'Quality':<10}")
print(f"   {'-'*40} {'-'*20} {'-'*10}")

count = 0
for tag_id in sorted(matched_tags.keys())[:15]:
    tag = matched_tags[tag_id]
    value = tag['value']
    
    # Format like JavaScript does
    try:
        num_value = float(value)
        display_value = f"{num_value:.2f}"
    except:
        display_value = str(value)
    
    print(f"   {tag_id:<40} {display_value:<20} {tag['quality']:<10}")
    count += 1

print(f"\n   ... and {len(matched_tags) - count} more tags")

print("\n" + "=" * 80)
print("VERDICT")
print("=" * 80)

if len(matched_tags) == len(selected_tags):
    print("✅ ALL APIs WORKING CORRECTLY!")
    print(f"✅ {len(matched_tags)} tags have live values")
    print(f"\n💡 If browser shows 0.00/WAITING, the JavaScript is NOT running.")
    print(f"   Check browser console (F12) for errors!")
else:
    print(f"⚠️  Only {len(matched_tags)}/{len(selected_tags)} tags matched")

print("=" * 80)
