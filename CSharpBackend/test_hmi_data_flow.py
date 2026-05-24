import requests
import json

print("\n" + "="*80)
print("TESTING HMI DATA FLOW - WELDING TAGS")
print("="*80)

# Test 1: Check what HMI proxy returns
print("\n1. Testing HMI proxy endpoint (http://localhost:1202/api/opc/values):")
try:
    response = requests.get('http://localhost:1202/api/opc/values', timeout=3)
    data = response.json()
    
    print(f"   Status: {response.status_code}")
    print(f"   Total tags: {data.get('count', 0)}")
    
    welding_tags = [t for t in data.get('tags', []) if 'Weld' in t.get('tagId', '') or 'Arc' in t.get('tagId', '') or 'WPS' in t.get('tagId', '')]
    
    print(f"\n   Welding tags found: {len(welding_tags)}")
    for tag in welding_tags:
        print(f"      • tagId: {tag.get('tagId'):30s} | value: {tag.get('value'):15} | quality: {tag.get('quality')}")
    
except Exception as e:
    print(f"   ❌ ERROR: {e}")

# Test 2: Check C# backend directly
print("\n2. Testing C# backend PLC endpoint (http://localhost:5001/api/plc/values):")
try:
    response = requests.get('http://localhost:5001/api/plc/values', timeout=3)
    data = response.json()
    
    print(f"   Status: {response.status_code}")
    print(f"   Success: {data.get('success')}")
    print(f"   Total values: {data.get('count', 0)}")
    
    welding_values = [v for v in data.get('values', []) if 'Weld' in v.get('tagName', '') or 'Arc' in v.get('tagName', '') or 'WPS' in v.get('tagName', '')]
    
    print(f"\n   Welding tags found: {len(welding_values)}")
    for val in welding_values:
        print(f"      • tagName: {val.get('tagName'):30s} | value: {val.get('value'):15} | quality: {val.get('quality')}")
    
except Exception as e:
    print(f"   ❌ ERROR: {e}")

# Test 3: Simulate JavaScript data map creation
print("\n3. Simulating JavaScript data map (like line 590 in realtime_trends.html):")
try:
    response = requests.get('http://localhost:1202/api/opc/values', timeout=3)
    apiData = response.json()
    
    # JavaScript: data[tag.tagId] = tag.value
    data_map = {}
    for tag in apiData.get('tags', []):
        data_map[tag['tagId']] = tag['value']
    
    # Check specific welding tags
    test_tags = ['Welding_Current_A', 'Welding_Voltage_V', 'Arc', 'WPS_ID']
    
    print(f"   Created data map with {len(data_map)} entries")
    print(f"\n   Testing welding tag lookups:")
    for tag_id in test_tags:
        if tag_id in data_map:
            value = data_map[tag_id]
            print(f"      ✅ data['{tag_id}'] = {value} (type: {type(value).__name__})")
        else:
            print(f"      ❌ data['{tag_id}'] = MISSING!")
    
except Exception as e:
    print(f"   ❌ ERROR: {e}")

print("\n" + "="*80)
print("DIAGNOSIS:")
print("="*80)
print("""
If welding tags show values in Test 1 and Test 2 but HMI shows "---":
→ JavaScript data map issue (tag ID mismatch or undefined check)

If Test 1 shows values but Test 2 is empty:
→ HMI proxy not fetching from PLC endpoint correctly

If both tests show values but map lookup fails:
→ Tag ID naming mismatch between selection and API response
""")
print("="*80)
