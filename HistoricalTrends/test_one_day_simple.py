"""
Test baseline API with ONE DAY of data
Date range: Jan 15, 2025 to Jan 16, 2025 (24 hours)
"""
import sys
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime
import json

print("Loading parquet file...")
data_file = Path("D:/OpcLogs/Data/ALL_SENSORS_COMPLETE_FORWARDFILL.parquet")

# Load data
df = pd.read_parquet(data_file)
print(f"✓ Loaded {len(df)} rows")

# Convert timestamp
df['Timestamp'] = pd.to_datetime(df['Timestamp'])

# Filter for ONE DAY
start_date = datetime(2025, 1, 15, 0, 0, 0)
end_date = datetime(2025, 1, 16, 23, 59, 59)

mask = (df['Timestamp'] >= start_date) & (df['Timestamp'] <= end_date)
filtered_df = df[mask].copy()

print(f"✓ Filtered to {len(filtered_df)} rows for Jan 15-16, 2025")

if len(filtered_df) == 0:
    print("❌ No data found for this date!")
    sys.exit(1)

# Convert long format to wide
print("✓ Converting to wide format...")
wide_df = filtered_df.pivot_table(index='Timestamp', columns='TagId', values='Value', aggfunc='first')
wide_df = wide_df.reset_index()
print(f"✓ {len(wide_df)} timestamps, {len(wide_df.columns)-1} tags")

# Use TURBINE_LOADMW tag
tag = 'TURBINE_LOADMW'
if tag not in wide_df.columns:
    print(f"❌ Tag {tag} not found!")
    sys.exit(1)

# Convert to numeric
wide_df[tag] = pd.to_numeric(wide_df[tag], errors='coerce')
wide_df = wide_df.dropna(subset=[tag])

print(f"✓ Tag: {tag}")
print(f"✓ Value range: {wide_df[tag].min():.2f} - {wide_df[tag].max():.2f} MW")
print(f"✓ Data points: {len(wide_df)}")

# Convert to JSON
data_json = wide_df[['Timestamp', tag]].to_dict('records')
for row in data_json:
    row['Timestamp'] = row['Timestamp'].isoformat()

# Call API
print(f"\n🚀 Testing baseline API with ONE DAY of data...")
response = requests.post(
    'http://localhost:5002/api/v1/baseline/calculate',
    json={'data': data_json, 'tag': tag},
    timeout=30
)

print(f"✓ Response status: {response.status_code}")

if response.status_code == 200:
    result = response.json()
    print(f"\n✅ SUCCESS with ONE DAY!\n")
    print(json.dumps(result, indent=2))
    
    if 'baseline' in result:
        b = result['baseline']
        print(f"\nBaseline: {b.get('value', 'N/A'):.3f} MW")
        print(f"Sample: {b.get('sample_size', 'N/A')} points")
        print(f"Window: {b.get('window_days', 'N/A')} days")
else:
    print(f"\n❌ FAILED!")
    print(response.text)
