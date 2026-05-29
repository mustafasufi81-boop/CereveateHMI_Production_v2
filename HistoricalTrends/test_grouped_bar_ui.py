#!/usr/bin/env python3
"""
Test Grouped Bar Chart with actual UI tag selection
Simulates exact browser behavior to diagnose the issue
"""

import requests
import json

print("=" * 70)
print("GROUPED BAR UI SIMULATION TEST")
print("=" * 70)

# Step 1: Load data from API
print("\n1️⃣  Loading data from /api/data...")
try:
    response = requests.get('http://127.0.0.1:5002/api/data', params={
        'start_date': '2025-03-02',
        'end_date': '2025-03-02',
        'tags': 'BEARING_VIB_HP_FRONT-Y,BEARING_VIB_HP_REAR-X,BEARING_VIB_HP_REAR-Y'
    })
    data = response.json()
    print(f"✓ Loaded {len(data)} rows")
    print(f"✓ First row keys: {list(data[0].keys())}")
    print(f"✓ First row sample: {data[0]}")
except Exception as e:
    print(f"❌ Error loading data: {e}")
    exit(1)

# Step 2: Show available columns
print("\n2️⃣  Available columns in data:")
if data:
    columns = list(data[0].keys())
    for i, col in enumerate(columns, 1):
        sample_value = data[0][col]
        value_type = type(sample_value).__name__
        print(f"   {i}. {col:50s} = {sample_value} ({value_type})")

# Step 3: User selected tags (from Y-axis checkboxes)
selected_tags = ['BEARING_VIB_HP_FRONT-Y', 'BEARING_VIB_HP_REAR-X', 'BEARING_VIB_HP_REAR-Y']
print(f"\n3️⃣  User selected Y-axis tags: {selected_tags}")

# Step 4: Check if selected tags exist in data
print("\n4️⃣  Tag match check:")
for tag in selected_tags:
    exists = tag in data[0]
    if exists:
        sample_val = data[0][tag]
        val_type = type(sample_val).__name__
        print(f"   ✓ {tag:50s} EXISTS (type={val_type}, value={sample_val})")
    else:
        print(f"   ✗ {tag:50s} NOT FOUND IN DATA")
        # Try to find similar names
        similar = [col for col in data[0].keys() if tag.replace('-', '_') in col or tag.replace('_', '-') in col]
        if similar:
            print(f"      💡 Similar columns: {similar}")

# Step 5: Process each tag (JavaScript simulation)
print("\n5️⃣  Processing tags (JavaScript filter simulation):")
stats = {'current': [], 'design': [], 'lastPeriod': []}
labels = []

for tag in selected_tags:
    print(f"\n   🔍 Processing: {tag}")
    
    # Check if tag exists
    if tag not in data[0]:
        print(f"      ❌ Tag not found in data, skipping")
        continue
    
    # Extract values (JavaScript: this.currentData.map(row => row[tag]))
    values = []
    for row in data:
        val = row.get(tag)
        # JavaScript filter: v !== null && v !== undefined && !isNaN(v) && typeof v === 'number'
        if val is not None and isinstance(val, (int, float)) and not (isinstance(val, float) and val != val):  # NaN check
            values.append(val)
    
    print(f"      Found {len(values)} valid numeric values")
    
    if len(values) == 0:
        print(f"      ⚠️  Skipping - no valid numeric data")
        continue
    
    # Calculate stats
    sorted_values = sorted(values)
    current_value = values[-1]  # Latest
    last_period_value = values[int(len(values) * 0.75)] if len(values) > 1 else current_value
    design_value = sorted_values[-1] * 1.05  # 5% above max
    
    print(f"      ✓ Current: {current_value:.2f}")
    print(f"      ✓ Last Period (75th): {last_period_value:.2f}")
    print(f"      ✓ Design (max*1.05): {design_value:.2f}")
    
    labels.append(tag.replace('_', ' '))
    stats['current'].append(current_value)
    stats['lastPeriod'].append(last_period_value)
    stats['design'].append(design_value)

# Step 6: Final result
print("\n6️⃣  FINAL RESULT:")
if len(labels) == 0:
    print("   ❌ No valid data to display!")
    print("   📊 Final stats: {labels: 0, current: 0}")
else:
    print(f"   ✅ SUCCESS! Generated chart with {len(labels)} metrics")
    print(f"   📊 Labels: {labels}")
    print(f"   📊 Current: {stats['current']}")
    print(f"   📊 Last Period: {stats['lastPeriod']}")
    print(f"   📊 Design: {stats['design']}")

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)
