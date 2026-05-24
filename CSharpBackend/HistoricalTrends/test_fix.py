import sys
sys.stdout = open('test_fix_output.txt', 'w', buffering=1)
sys.stderr = sys.stdout

print("TEST START")

import pandas as pd
from datetime import datetime
import requests
import json

print("Loading parquet...")
df = pd.read_parquet("D:/OpcLogs/Data/ALL_SENSORS_COMPLETE_FORWARDFILL.parquet")
print(f"Loaded: {len(df)} rows")

df['Timestamp'] = pd.to_datetime(df['Timestamp'])

# ONE DAY: Jan 15, 2025
start = datetime(2025, 1, 15, 0, 0, 0)
end = datetime(2025, 1, 15, 23, 59, 59)
filtered = df[(df['Timestamp'] >= start) & (df['Timestamp'] <= end)]
print(f"Jan 15 data: {len(filtered)} rows")

# Convert to wide
wide = filtered.pivot_table(index='Timestamp', columns='TagId', values='Value', aggfunc='first').reset_index()
print(f"Wide format: {len(wide)} rows, {len(wide.columns)} columns")

# Get TURBINE_LOADMW
tag = 'TURBINE_LOADMW'
wide[tag] = pd.to_numeric(wide[tag], errors='coerce')
wide = wide.dropna(subset=[tag])
print(f"Tag {tag}: {len(wide)} points, range {wide[tag].min():.2f}-{wide[tag].max():.2f} MW")

# Prepare API call
data_json = wide[['Timestamp', tag]].to_dict('records')
for row in data_json:
    row['Timestamp'] = row['Timestamp'].isoformat()

print(f"\nCalling API with {len(data_json)} points...")
response = requests.post(
    'http://localhost:5002/api/v1/baseline/calculate',
    json={'data': data_json, 'tag': tag},
    timeout=30
)

print(f"Status: {response.status_code}")
if response.status_code == 200:
    result = response.json()
    print("\nRESULT:")
    print(json.dumps(result, indent=2))
else:
    print(f"ERROR: {response.text}")

print("\nTEST COMPLETE")
sys.stdout.close()
