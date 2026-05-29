"""
Test exact browser flow to identify the issue
"""
import requests
import json

print("=" * 60)
print("BROWSER FLOW TEST - Step by Step")
print("=" * 60)

base_url = "http://127.0.0.1:5002"

# Step 1: Load data (like browser does)
print("\n1️⃣  STEP 1: Load data from /api/data")
print("-" * 60)
params = {
    'startDate': '2025-03-01',
    'endDate': '2025-03-02',
    'tags': 'BEARING_VIB_HP_FRONT-XMICRO_METER-UM,BEARING_VIB_HP_FRONT-Y,BEARING_VIB_HP_REAR-X,BEARING_VIB_HP_REAR-Y,BEARING_VIB_LP_FRONT-X,BEARING_VIB_LP_FRONT-Y,BEARING_VIB_LP_REAR-X,BEARING_VIB_LP_REAR-Y,THRUST_POSITION_HP_COUPLING,THRUST_POSITION_LP_COUPLING'
}

response = requests.get(f"{base_url}/api/data", params=params)
data = response.json()

print(f"✓ Response status: {response.status_code}")
print(f"✓ Data rows: {len(data)}")
print(f"✓ First row keys: {list(data[0].keys())}")
print(f"✓ First row sample: {data[0]}")

# Step 2: Check data types (like JavaScript does)
print("\n2️⃣  STEP 2: Check data types (JavaScript typeof simulation)")
print("-" * 60)
first_row = data[0]
for key, value in first_row.items():
    python_type = type(value).__name__
    # Simulate JavaScript typeof
    if isinstance(value, bool):
        js_type = "boolean"
    elif isinstance(value, (int, float)):
        js_type = "number"
    elif isinstance(value, str):
        js_type = "string"
    elif value is None:
        js_type = "undefined"
    else:
        js_type = "object"
    
    print(f"  {key}: python={python_type}, js_typeof={js_type}, value={value}")

# Step 3: Filter numeric tags (like bi_analytics.js does)
print("\n3️⃣  STEP 3: Filter numeric tags (JavaScript logic)")
print("-" * 60)
numeric_tags = []
for key, value in first_row.items():
    is_timestamp = key.lower() == 'timestamp'
    is_numeric = isinstance(value, (int, float))
    is_not_nan = value == value  # NaN check
    
    if not is_timestamp and is_numeric and is_not_nan:
        numeric_tags.append(key)
        print(f"  ✓ {key}: VALID (type={type(value).__name__}, value={value})")
    else:
        print(f"  ✗ {key}: SKIP (timestamp={is_timestamp}, numeric={is_numeric}, value={value})")

print(f"\n✓ RESULT: {len(numeric_tags)} numeric tags found")
print(f"✓ Tags: {numeric_tags}")

# Step 4: Check what renderVisualization would see
print("\n4️⃣  STEP 4: Simulate renderVisualization() checks")
print("-" * 60)
current_data = data  # This is what should be in this.currentData
has_current_data = current_data is not None and len(current_data) > 0
backup_data = data  # This is what should be in window._biDataBackup
has_backup = backup_data is not None and len(backup_data) > 0

print(f"  hasCurrentData: {has_current_data}")
print(f"  currentDataLength: {len(current_data) if current_data else 0}")
print(f"  hasBackup: {has_backup}")
print(f"  backupLength: {len(backup_data) if backup_data else 0}")

if not has_current_data:
    print("\n❌ ERROR: No data would be available!")
    print("   This is why 'No data loaded' error appears")
else:
    print("\n✓ Data is available, should proceed to chart rendering")

# Step 5: Check what renderGroupedBarChart would receive
print("\n5️⃣  STEP 5: Simulate renderGroupedBarChart() field detection")
print("-" * 60)
available_tags = [key for key, value in first_row.items() 
                  if key.lower() != 'timestamp' 
                  and isinstance(value, (int, float)) 
                  and value == value]

print(f"  Available tags: {len(available_tags)}")
print(f"  Tags: {available_tags}")

if len(available_tags) == 0:
    print("\n❌ ERROR: No numeric tags found!")
    print("   This is the exact error you're seeing!")
else:
    smart_limit = available_tags[:10] if len(available_tags) <= 10 else available_tags[:6]
    print(f"\n✓ Smart limit: {len(smart_limit)} tags to display")
    print(f"✓ Display tags: {smart_limit}")

print("\n" + "=" * 60)
print("DIAGNOSIS COMPLETE")
print("=" * 60)
