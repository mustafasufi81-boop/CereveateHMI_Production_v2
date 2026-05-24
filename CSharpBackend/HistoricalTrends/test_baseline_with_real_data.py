"""
Test baseline API with real data from parquet files
Date range: Dec 8, 2024 to Feb 9, 2025
"""
import sys
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime
import json

# Load real data from parquet files
data_dir = Path("D:/OpcLogs/Data")
parquet_files = sorted(data_dir.glob("*.parquet"))

print(f"Found {len(parquet_files)} parquet files")

# Load data for the date range
start_date = datetime(2024, 12, 8)
end_date = datetime(2025, 2, 9)

all_data = []
for file in parquet_files:
    try:
        df = pd.read_parquet(file)
        if 'Timestamp' in df.columns:
            df['Timestamp'] = pd.to_datetime(df['Timestamp'])
            # Filter by date range
            mask = (df['Timestamp'] >= start_date) & (df['Timestamp'] <= end_date)
            filtered = df[mask]
            if len(filtered) > 0:
                all_data.append(filtered)
                print(f"  ✓ {file.name}: {len(filtered)} rows")
    except Exception as e:
        print(f"  ✗ {file.name}: {e}")

if not all_data:
    print("❌ No data found for date range!")
    sys.exit(1)

# Combine all data
combined_df = pd.concat(all_data, ignore_index=True)
combined_df = combined_df.sort_values('Timestamp').reset_index(drop=True)

print(f"\n✓ Total data points: {len(combined_df)}")
print(f"✓ Date range: {combined_df['Timestamp'].min()} to {combined_df['Timestamp'].max()}")
print(f"✓ Columns: {list(combined_df.columns)}")

# Check if data is in long format (TagId, Value) or wide format (multiple columns)
if 'TagId' in combined_df.columns and 'Value' in combined_df.columns:
    print("\n✓ Data in long format, converting to wide format...")
    # Pivot to wide format
    wide_df = combined_df.pivot_table(index='Timestamp', columns='TagId', values='Value', aggfunc='first')
    wide_df = wide_df.reset_index()
    combined_df = wide_df
    print(f"✓ Converted to wide format with {len(combined_df.columns)} columns")
    print(f"✓ Tags: {list(combined_df.columns[1:])[:5]}...")  # Show first 5 tags

# Select a production tag
tag = None
for col in combined_df.columns:
    if 'TURBINE' in str(col).upper() and 'LOAD' in str(col).upper():
        tag = col
        break
    elif 'LOAD' in str(col).upper() and 'MW' in str(col).upper():
        tag = col
        break

if tag is None:
    # Just use first numeric column
    for col in combined_df.columns:
        if col != 'Timestamp' and combined_df[col].dtype in ['float64', 'int64']:
            tag = col
            break

print(f"\n✓ Testing with tag: {tag}")

# Convert tag column to numeric, handling any string values
combined_df[tag] = pd.to_numeric(combined_df[tag], errors='coerce')
combined_df = combined_df.dropna(subset=[tag])

print(f"✓ Value range: {combined_df[tag].min():.2f} - {combined_df[tag].max():.2f}")

# Convert to JSON format for API
data_json = combined_df.to_dict('records')

# Convert timestamps to ISO format
for row in data_json:
    if isinstance(row['Timestamp'], pd.Timestamp):
        row['Timestamp'] = row['Timestamp'].isoformat()

print(f"\n🚀 Testing baseline API...")
print(f"   API: http://localhost:5002/api/v1/baseline/calculate")
print(f"   Data points: {len(data_json)}")
print(f"   Tag: {tag}")

# Test API
try:
    response = requests.post(
        'http://localhost:5002/api/v1/baseline/calculate',
        json={
            'data': data_json,
            'tag': tag
        },
        timeout=30
    )
    
    print(f"\n✓ Response status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"\n✅ SUCCESS!")
        print(f"\nFull Response:")
        print(json.dumps(result, indent=2))
        
        # Try different response structures
        if 'baseline' in result:
            baseline = result['baseline']
        elif 'value' in result:
            baseline = result
        else:
            print(f"\n❌ Unexpected response structure")
            baseline = None
        
        if baseline:
            print(f"\nBaseline Results:")
            print(f"  Value: {baseline.get('value', 'N/A'):.3f} MW" if isinstance(baseline.get('value'), (int, float)) else f"  Value: {baseline.get('value', 'N/A')}")
            print(f"  Min: {baseline.get('min', 'N/A')}")
            print(f"  Max: {baseline.get('max', 'N/A')}")
            print(f"  Sample Size: {baseline.get('sample_size', 'N/A')}")
            print(f"  Confidence: {baseline.get('confidence', 'N/A')}")
    else:
        print(f"\n❌ FAILED!")
        print(f"Response: {response.text}")
        
except Exception as e:
    print(f"\n❌ ERROR: {e}")
