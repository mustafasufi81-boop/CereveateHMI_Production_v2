"""
Debug script - Check why values not showing in UI
"""
import requests
import json

print("=" * 70)
print("DEBUGGING: Why values not showing in Live Values table")
print("=" * 70)

# Step 1: Call the API and see exact response
print("\n📡 Step 1: Calling /api/opc/values endpoint...")
try:
    response = requests.get("http://localhost:1202/api/opc/values", timeout=5)
    data = response.json()
    
    print(f"✅ Response received")
    print(f"   Status Code: {response.status_code}")
    print(f"   Total tags in response: {len(data.get('tags', []))}")
    
    # Step 2: Check specific tags that user selected
    print("\n🔍 Step 2: Looking for selected tags...")
    selected_tags = ["Pump_Discharge_Pressure", "Random.UInt4", "Random.UInt2"]
    
    found_tags = {}
    for tag in data.get('tags', []):
        tag_id = tag.get('tagId')
        if tag_id in selected_tags:
            found_tags[tag_id] = tag
            print(f"   ✅ Found: {tag_id}")
            print(f"      Value: {tag.get('value')}")
            print(f"      Quality: {tag.get('quality')}")
    
    if not found_tags:
        print(f"\n   ❌ PROBLEM: None of the selected tags found in response!")
        print(f"   Selected tags: {selected_tags}")
        print(f"\n   Available tags (first 10):")
        for i, tag in enumerate(data.get('tags', [])[:10]):
            print(f"      {i+1}. {tag.get('tagId')} = {tag.get('value')}")
    
    # Step 3: Test the JavaScript logic
    print("\n🧪 Step 3: Simulating JavaScript data processing...")
    print("   JavaScript expects: data[tagId] = value")
    print("   But API returns: data.tags[i].tagId and data.tags[i].value")
    print()
    
    # Simulate what JavaScript should do
    data_map = {}
    for tag in data.get('tags', []):
        data_map[tag.get('tagId')] = tag.get('value')
    
    print("   After conversion to map:")
    for tag_id in selected_tags:
        if tag_id in data_map:
            print(f"   ✅ data_map['{tag_id}'] = {data_map[tag_id]}")
        else:
            print(f"   ❌ data_map['{tag_id}'] = undefined")
    
    # Step 4: Check the actual response format
    print("\n📋 Step 4: Checking response structure...")
    if data.get('tags') and len(data['tags']) > 0:
        sample_tag = data['tags'][0]
        print("   Sample tag structure:")
        print(f"   {json.dumps(sample_tag, indent=6)}")
    
    # Step 5: Find what tags are actually available
    print("\n📊 Step 5: All available tag IDs (first 20):")
    for i, tag in enumerate(data.get('tags', [])[:20]):
        print(f"   {i+1:2d}. {tag.get('tagId')}")
    
    print("\n" + "=" * 70)
    print("DIAGNOSIS:")
    print("=" * 70)
    
    if found_tags:
        print("✅ Selected tags ARE in the API response")
        print("✅ The issue is in the JavaScript code")
        print("\n💡 SOLUTION: The JavaScript fix has been applied")
        print("   It now converts tags array to map: data[tagId] = value")
    else:
        print("❌ Selected tags NOT in API response")
        print("\n💡 SOLUTION: User needs to select tags that exist in the API")
        print(f"   Try selecting from the list above")
    
    print("=" * 70)
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
