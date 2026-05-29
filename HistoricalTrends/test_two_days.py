"""
Test baseline API with 2 days of data (Nov 22-23, 2024)
Testing: What happens with short date range?
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

# Load data for 2 DAYS
start_date = datetime(2024, 11, 22, 0, 0, 0)  # Nov 22, 2024
end_date = datetime(2024, 11, 23, 23, 59, 59)  # Nov 23, 2024

print(f"\n📅 Testing with 2 DAYS: Nov 22-23, 2024")

all_data = []
for file in parquet_files:
    try:
        df = pd.read_parquet(file)
        if 'Timestamp' in df.columns:
            df['Timestamp'] = pd.to_datetime(df['Timestamp'])
            mask = (df['Timestamp'] >= start_date) & (df['Timestamp'] <= end_date)
            filtered = df[mask]
            if len(filtered) > 0:
                all_data.append(filtered)
                print(f"  ✓ {file.name}: {len(filtered)} rows")
    except Exception as e:
        print(f"  ✗ {file.name}: {e}")

if not all_data:
    print("❌ No data found for this date range!")
    sys.exit(1)

# Combine all data
combined_df = pd.concat(all_data, ignore_index=True)
combined_df = combined_df.sort_values('Timestamp').reset_index(drop=True)

print(f"\n✓ Total data points: {len(combined_df)}")
print(f"✓ Time range: {combined_df['Timestamp'].min()} to {combined_df['Timestamp'].max()}")

# Convert to wide format
if 'TagId' in combined_df.columns and 'Value' in combined_df.columns:
    wide_df = combined_df.pivot_table(index='Timestamp', columns='TagId', values='Value', aggfunc='first')
    wide_df = wide_df.reset_index()
    combined_df = wide_df

# Select TURBINE_LOADMW
tag = 'TURBINE_LOADMW'
combined_df[tag] = pd.to_numeric(combined_df[tag], errors='coerce')
combined_df = combined_df.dropna(subset=[tag])

print(f"\n✓ Tag: {tag}")
print(f"✓ Data points for tag: {len(combined_df)}")
print(f"✓ Value range: {combined_df[tag].min():.2f} - {combined_df[tag].max():.2f} MW")

# Convert to JSON
data_json = combined_df.to_dict('records')
for row in data_json:
    if isinstance(row['Timestamp'], pd.Timestamp):
        row['Timestamp'] = row['Timestamp'].isoformat()

print(f"\n🚀 Testing baseline API with {len(data_json)} data points (2 days)")
print(f"   Question: How does 30-day rolling window handle 2 days of data?")

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
        print(f"\n✅ SUCCESS - System accepts 2 days of data!")
        print(f"\n📊 How it works:")
        print(f"   - Your selection: 2 days (Nov 22-23, 2024)")
        print(f"   - Data points: {len(data_json)}")
        print(f"   - Latest timestamp: {combined_df['Timestamp'].max()}")
        print(f"   - Rolling window: {result['window_days']} days from latest timestamp")
        print(f"   - Actual data used: ALL {len(data_json)} points (since only 2 days available)")
        print(f"\n✓ Baseline calculated:")
        print(f"   Value: {result['value']:.3f} MW")
        print(f"   Min: {result['min']:.3f} MW")
        print(f"   Max: {result['max']:.3f} MW")
        print(f"   Sample Size: {result['sample_size']} (top 10% of data)")
        print(f"   Confidence: {result['confidence']:.1f}%")
        print(f"\n💡 Conclusion:")
        print(f"   System uses whatever data you provide within the rolling window.")
        print(f"   For 2 days: Uses all data from those 2 days")
        print(f"   For 30 days: Uses all 30 days")
        print(f"   For 90 days: Uses only last 30 days from the end date")
        
    else:
        result = response.json()
        print(f"\n❌ FAILED!")
        print(f"Response: {json.dumps(result, indent=2)}")
        print(f"\n💡 This means:")
        print(f"   - 2 days of data is NOT enough for baseline calculation")
        print(f"   - Minimum required: {result.get('detail', 'Unknown requirement')}")
        
except Exception as e:
    print(f"\n❌ ERROR: {e}")
