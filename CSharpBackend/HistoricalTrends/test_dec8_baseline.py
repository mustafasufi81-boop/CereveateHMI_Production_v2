"""
Test baseline calculation for Dec 8, 2024
Expected average: 147.41 MW
"""
import pandas as pd
from datetime import datetime
import numpy as np

# Load parquet file
print("Loading data...")
df = pd.read_parquet("D:/OpcLogs/Data/ALL_SENSORS_COMPLETE_FORWARDFILL.parquet")
print(f"Total rows: {len(df)}")

# Convert timestamp
df['Timestamp'] = pd.to_datetime(df['Timestamp'])

# Filter for Dec 8, 2024 ONLY
start = datetime(2024, 12, 8, 0, 0, 0)
end = datetime(2024, 12, 8, 23, 59, 59)

filtered = df[(df['Timestamp'] >= start) & (df['Timestamp'] <= end)]
print(f"\nDec 8, 2024 data: {len(filtered)} rows")

if len(filtered) == 0:
    print("❌ NO DATA FOUND for Dec 8, 2024!")
    print(f"Available date range: {df['Timestamp'].min()} to {df['Timestamp'].max()}")
    exit()

# Convert to wide format
wide = filtered.pivot_table(index='Timestamp', columns='TagId', values='Value', aggfunc='first').reset_index()
print(f"Wide format: {len(wide)} timestamps")

# Get TURBINE_LOADMW
if 'TURBINE_LOADMW' not in wide.columns:
    print(f"❌ TURBINE_LOADMW not found! Available columns: {list(wide.columns)}")
    exit()

wide['TURBINE_LOADMW'] = pd.to_numeric(wide['TURBINE_LOADMW'], errors='coerce')
wide = wide.dropna(subset=['TURBINE_LOADMW'])

values = wide['TURBINE_LOADMW'].values

print(f"\n{'='*60}")
print(f"TURBINE_LOADMW STATISTICS - Dec 8, 2024")
print(f"{'='*60}")
print(f"Data points: {len(values)}")
print(f"Min: {np.min(values):.2f} MW")
print(f"Max: {np.max(values):.2f} MW")
print(f"Average (Baseline): {np.mean(values):.2f} MW")
print(f"Median: {np.median(values):.2f} MW")
print(f"Std Dev: {np.std(values):.2f} MW")
print(f"\nExpected Average: 147.41 MW")
print(f"Actual Average: {np.mean(values):.2f} MW")
print(f"Difference: {abs(147.41 - np.mean(values)):.2f} MW")

if abs(147.41 - np.mean(values)) < 1.0:
    print(f"\n✅ CALCULATION CORRECT!")
else:
    print(f"\n❌ CALCULATION WRONG!")
    print(f"\nFirst 10 values:")
    print(values[:10])
    print(f"\nLast 10 values:")
    print(values[-10:])
