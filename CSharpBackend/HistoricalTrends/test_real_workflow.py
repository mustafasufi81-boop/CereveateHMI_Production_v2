"""
Direct test: Call actual API endpoints with real browser data
"""
import requests
import json

BASE_URL = "http://127.0.0.1:5002"

print("\n" + "="*80)
print("TESTING ACTUAL BROWSER WORKFLOW")
print("="*80)

# Step 1: Get actual data from parquet like browser does
print("\n1️⃣  Getting real data from API")
print("-" * 80)
response = requests.get(f"{BASE_URL}/api/data", params={
    'start_date': '2025-10-21T20:00:00.000Z',
    'end_date': '2025-11-20T20:00:00.000Z',
    'tags': json.dumps(['TOTAL_COAL_FLOW', 'TURBINE_LOADMW'])
})
print(f"Status: {response.status_code}")
data = response.json()
print(f"Records: {len(data)}")
print(f"Keys: {list(data.keys()) if isinstance(data, dict) else 'List of records'}")
if isinstance(data, dict) and 'data' in data:
    records = data['data']
    print(f"Actual records: {len(records)}")
    print(f"Sample: {records[0] if records else 'No records'}")
elif isinstance(data, list):
    records = data
    print(f"Sample: {data[0] if data else 'No records'}")
else:
    records = []
    print("Unexpected data format")

# Step 2: Call baseline like JavaScript does
print("\n2️⃣  Calling BASELINE endpoint")
print("-" * 80)
response = requests.post(f"{BASE_URL}/api/v1/baseline/calculate", json={
    'data': records,
    'tag': 'TURBINE_LOADMW',
    'config': {
        'baseline_window': 30,
        'top_percentile': 90,
        'outlier_threshold': 3.0,
        'outlier_method': 'sigma',
        'min_data_points': 10
    }
})
print(f"Status: {response.status_code}")
if response.status_code == 200:
    baseline = response.json()
    print(f"✓ Baseline value: {baseline.get('value')}")
    print(f"  std_dev: {baseline.get('std_dev')}")
    print(f"  sample_size: {baseline.get('sample_size')}")
else:
    print(f"❌ Error: {response.text}")
    exit(1)

# Step 3: Extract current conditions like JavaScript does
print("\n3️⃣  Extracting current conditions")
print("-" * 80)
current_conditions = {}
all_keys = set()

# Handle different data formats
if isinstance(records, list) and len(records) > 0:
    for record in records:
        if isinstance(record, dict):
            all_keys.update(record.keys())
elif isinstance(data, dict):
    all_keys = set(data.keys())

for key in all_keys:
    if key not in ['Timestamp', 'RowId', 'TagId']:
        if isinstance(records, list):
            values = []
            for d in records:
                if isinstance(d, dict) and key in d and d[key] is not None:
                    try:
                        values.append(float(d[key]))
                    except (ValueError, TypeError):
                        pass
        elif isinstance(data, dict) and key in data:
            raw_values = data[key] if isinstance(data[key], list) else [data[key]]
            values = []
            for v in raw_values:
                try:
                    values.append(float(v))
                except (ValueError, TypeError):
                    pass
        else:
            values = []
        
        if values:
            current_conditions[key] = sum(values) / len(values)

print(f"Current conditions: {current_conditions}")

# Step 4: Call efficiency like JavaScript does
print("\n4️⃣  Calling EFFICIENCY endpoint")
print("-" * 80)
response = requests.post(f"{BASE_URL}/api/v1/efficiency/calculate", json={
    'baseline_production': baseline['value'],
    'current_conditions': current_conditions,
    'parameters': {}
})
print(f"Status: {response.status_code}")
if response.status_code == 200:
    efficiency = response.json()
    print(f"✓ adjusted_expected: {efficiency.get('adjusted_expected')}")
    print(f"  total_loss_factor: {efficiency.get('total_loss_factor')}")
    print(f"  baseline: {efficiency.get('baseline')}")
    print(f"  Full response: {json.dumps(efficiency, indent=2)}")
    
    # Check if it's actually 0 or if there's data
    if efficiency.get('adjusted_expected') == 0:
        print("\n⚠️  WARNING: adjusted_expected is 0!")
        print(f"   baseline_production sent: {baseline['value']}")
        print(f"   current_conditions sent: {current_conditions}")
else:
    print(f"❌ Error: {response.text}")
    exit(1)

# Step 5: Calculate avgActual like JavaScript does
print("\n5️⃣  Calculating avgActual (JavaScript simulation)")
print("-" * 80)
if isinstance(records, list):
    load_values = []
    for d in records:
        if isinstance(d, dict) and d.get('TURBINE_LOADMW') is not None:
            try:
                load_values.append(float(d.get('TURBINE_LOADMW')))
            except (ValueError, TypeError):
                pass
elif isinstance(data, dict) and 'TURBINE_LOADMW' in data:
    raw_values = data['TURBINE_LOADMW'] if isinstance(data['TURBINE_LOADMW'], list) else [data['TURBINE_LOADMW']]
    load_values = []
    for v in raw_values:
        try:
            load_values.append(float(v))
        except (ValueError, TypeError):
            pass
else:
    load_values = []
if load_values:
    avgActual = sum(load_values) / len(load_values)
    print(f"✓ avgActual: {avgActual}")
    print(f"  Number of values: {len(load_values)}")
    print(f"  Min: {min(load_values)}, Max: {max(load_values)}")
else:
    print(f"❌ No load values found!")
    avgActual = None

# Step 6: Check what would happen in step5
print("\n6️⃣  Checking STEP 5 conditions")
print("-" * 80)
avgExpected = efficiency.get('adjusted_expected')
print(f"avgActual: {avgActual} (type: {type(avgActual)})")
print(f"avgExpected: {avgExpected} (type: {type(avgExpected)})")

if avgActual is None or avgActual == 0:
    print("❌ FAIL: avgActual is None or 0")
elif avgExpected is None or avgExpected == 0:
    print("❌ FAIL: avgExpected is None or 0")
else:
    print("✅ PASS: Both values are valid")
    
    # Step 7: Try delta call
    print("\n7️⃣  Calling DELTA endpoint")
    print("-" * 80)
    timestamp = None
    if isinstance(records, list) and len(records) > 0:
        timestamp = records[len(records)//2].get('Timestamp') if isinstance(records[len(records)//2], dict) else None
    elif isinstance(data, dict) and 'Timestamp' in data:
        timestamps = data['Timestamp']
        timestamp = timestamps[len(timestamps)//2] if isinstance(timestamps, list) and len(timestamps) > 0 else None
    
    response = requests.post(f"{BASE_URL}/api/v1/delta/calculate", json={
        'actual': avgActual,
        'expected': avgExpected,
        'metadata': {'period': 'aggregate'},
        'timestamp': timestamp
    })
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        delta = response.json()
        print(f"✓ weighted_delta: {delta.get('weighted_delta')}")
        print(f"  performance_score: {delta.get('performance_score')}")
        print(f"  condition: {delta.get('condition')}")
    else:
        print(f"❌ Error: {response.text}")

print("\n" + "="*80)
print("TEST COMPLETE")
print("="*80 + "\n")
