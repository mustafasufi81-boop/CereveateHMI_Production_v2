"""
Direct test - simulate clicking Grouped Bar button
"""
import requests
import json

base_url = "http://127.0.0.1:5002"

print("="*80)
print("SIMULATING GROUPED BAR BUTTON CLICK")
print("="*80)

try:
    # Step 1: Get tags (like UI does)
    print("\n1️⃣  Getting tags...")
    tags_resp = requests.get(f"{base_url}/api/tags", timeout=5)
    tags_data = tags_resp.json()
    all_tags = tags_data['tags']
    print(f"   Found {len(all_tags)} tags")
    
    # Step 2: Load data (like UI does)
    print("\n2️⃣  Loading data (March 2025)...")
    params = {
        'start_date': '2025-03-01',
        'end_date': '2025-03-20',
        'tags': json.dumps(all_tags[:10])  # First 10 tags like UI
    }
    
    data_resp = requests.get(f"{base_url}/api/data", params=params, timeout=10)
    data_result = data_resp.json()
    
    if not data_result['success']:
        print(f"   ❌ Error: {data_result}")
        exit(1)
    
    currentData = data_result['data']
    print(f"   ✅ Loaded {len(currentData)} rows")
    
    # Step 3: Simulate what JavaScript does
    print("\n3️⃣  Simulating JavaScript auto-detection...")
    
    if not currentData or len(currentData) == 0:
        print("   ❌ currentData is empty!")
        exit(1)
    
    firstRow = currentData[0]
    print(f"\n   First row structure:")
    print(f"   Type: {type(firstRow)}")
    print(f"   Keys: {list(firstRow.keys())}")
    print(f"\n   Full first row:")
    for key, value in firstRow.items():
        print(f"      {key}: {value} (type: {type(value).__name__})")
    
    # Step 4: Apply JavaScript filter logic
    print(f"\n4️⃣  Applying JavaScript filter (typeof === 'number')...")
    numeric_tags = []
    
    for key in firstRow.keys():
        lowerKey = key.lower()
        value = firstRow[key]
        
        # JavaScript checks
        isTimestamp = lowerKey == 'timestamp'
        isNumber = isinstance(value, (int, float))  # Python equivalent of typeof === 'number'
        isNotNaN = not (isinstance(value, float) and value != value)  # NaN check
        isValid = not isTimestamp and isNumber and isNotNaN
        
        status = "✓" if isValid else "✗"
        print(f"   {status} {key}: type={type(value).__name__}, value={value}, valid={isValid}")
        
        if isValid:
            numeric_tags.append(key)
    
    print(f"\n5️⃣  RESULT:")
    print(f"   Numeric tags found: {len(numeric_tags)}")
    if numeric_tags:
        print(f"   Tags: {numeric_tags}")
        
        # Smart limit
        smartLimit = len(numeric_tags) if len(numeric_tags) <= 10 else min(6, len(numeric_tags))
        print(f"   Smart limit: {smartLimit} tags to display")
        print(f"   Display: {numeric_tags[:smartLimit]}")
    else:
        print("   ❌ NO NUMERIC TAGS FOUND!")
        print("\n   DIAGNOSIS:")
        print("   This is the EXACT issue happening in the browser!")
        print("   The data structure shows all values but JavaScript sees them as non-numeric.")
        
    print("\n" + "="*80)
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
