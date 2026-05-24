"""
Test complete data flow: OPC API → Database tags → HMI display
"""
import requests
import json

print("=" * 80)
print("TESTING COMPLETE DATA FLOW")
print("=" * 80)

# Step 1: Check OPC service has live values
print("\n1️⃣ Testing OPC service API (http://localhost:5001/api/opc/values)...")
try:
    response = requests.get("http://localhost:5001/api/opc/values", timeout=5)
    opc_data = response.json()
    print(f"   ✅ OPC service responded: {opc_data['count']} tags")
    print(f"   Sample tags:")
    for tag in opc_data['tags'][:3]:
        print(f"      - {tag['tagId']}: value={tag['value']}, quality={tag['quality']}")
    opc_tag_ids = [tag['tagId'] for tag in opc_data['tags']]
except Exception as e:
    print(f"   ❌ OPC service ERROR: {e}")
    opc_tag_ids = []

# Step 2: Check HMI API returns database-mapped tags
print("\n2️⃣ Testing HMI database API (http://localhost:5002/api/tags/enabled)...")
try:
    response = requests.get("http://localhost:5002/api/tags/enabled", timeout=5)
    hmi_data = response.json()
    print(f"   ✅ HMI API responded: {hmi_data['count']} mapped tags from database")
    print(f"   Sample tags:")
    for tag in hmi_data['tags'][:3]:
        print(f"      - {tag['tagId']}: {tag['tagName']}")
    hmi_tag_ids = [tag['tagId'] for tag in hmi_data['tags']]
except Exception as e:
    print(f"   ❌ HMI API ERROR: {e}")
    hmi_tag_ids = []

# Step 3: Check which database tags match OPC tags
print("\n3️⃣ Checking tag matching (database ↔ OPC pool)...")
if opc_tag_ids and hmi_tag_ids:
    matched = [tag for tag in hmi_tag_ids if tag in opc_tag_ids]
    unmatched = [tag for tag in hmi_tag_ids if tag not in opc_tag_ids]
    
    print(f"   ✅ Matched tags: {len(matched)}/{len(hmi_tag_ids)}")
    if matched:
        print(f"   First 5 matches: {matched[:5]}")
    
    if unmatched:
        print(f"   ⚠️  Unmatched tags: {len(unmatched)}")
        print(f"   Missing from OPC: {unmatched[:5]}")
else:
    print(f"   ❌ Cannot compare: OPC={len(opc_tag_ids)}, HMI={len(hmi_tag_ids)}")

# Step 4: Summary
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"OPC Service:     {len(opc_tag_ids)} tags with live values")
print(f"Database:        {len(hmi_tag_ids)} mapped tags")
if opc_tag_ids and hmi_tag_ids:
    print(f"Matching:        {len(matched)} tags will show live values in HMI")
    print(f"\n💡 Expected behavior:")
    print(f"   - HMI loads {len(hmi_tag_ids)} tags from database")
    print(f"   - JavaScript polls OPC every 1 second")
    print(f"   - {len(matched)} matching tags get live values")
    print(f"   - {len(unmatched)} unmatched tags stay at 0.00/WAITING")
    
    if len(matched) > 0:
        print(f"\n✅ SETUP IS CORRECT - Refresh browser (Ctrl+Shift+R) to see values!")
    else:
        print(f"\n❌ NO MATCHING TAGS - Check tag_id names in database vs OPC")
else:
    print(f"\n❌ SERVICES NOT READY - Start both OPC and HMI services")

print("=" * 80)
