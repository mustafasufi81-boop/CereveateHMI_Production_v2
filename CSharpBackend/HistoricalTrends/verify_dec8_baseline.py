"""
Verify Dec 8, 2024 baseline calculation
Expected: 147.41 MW average
"""
import pandas as pd
import numpy as np
from datetime import datetime

# Load data
print("Loading parquet file...")
df = pd.read_parquet("D:/OpcLogs/Data/ALL_SENSORS_COMPLETE_FORWARDFILL.parquet")
print(f"Total rows: {len(df)}")

# Convert timestamp
df['Timestamp'] = pd.to_datetime(df['Timestamp'])

# Filter for Dec 8, 2024 ONLY
start = datetime(2024, 12, 8, 0, 0, 0)
end = datetime(2024, 12, 8, 23, 59, 59)
dec8_data = df[(df['Timestamp'] >= start) & (df['Timestamp'] <= end)].copy()

print(f"\nDec 8, 2024 data: {len(dec8_data)} rows")

if len(dec8_data) == 0:
    print("❌ NO DATA for Dec 8, 2024!")
    print(f"Available date range: {df['Timestamp'].min()} to {df['Timestamp'].max()}")
    exit(1)

# Convert to wide format
wide = dec8_data.pivot_table(index='Timestamp', columns='TagId', values='Value', aggfunc='first')
wide = wide.reset_index()

print(f"Wide format: {len(wide)} timestamps")

# Get TURBINE_LOADMW
if 'TURBINE_LOADMW' not in wide.columns:
    print("❌ TURBINE_LOADMW column not found!")
    print(f"Available columns: {list(wide.columns)}")
    exit(1)

# Convert to numeric
wide['TURBINE_LOADMW'] = pd.to_numeric(wide['TURBINE_LOADMW'], errors='coerce')
wide = wide.dropna(subset=['TURBINE_LOADMW'])

values = wide['TURBINE_LOADMW'].values

print(f"\n{'='*60}")
print(f"DEC 8, 2024 - TURBINE_LOADMW ANALYSIS")
print(f"{'='*60}")
print(f"Data points: {len(values)}")
print(f"Min value: {np.min(values):.2f} MW")
print(f"Max value: {np.max(values):.2f} MW")
print(f"Average (BASELINE): {np.mean(values):.2f} MW")
print(f"Median: {np.median(values):.2f} MW")
print(f"Std Dev: {np.std(values):.2f} MW")
print(f"{'='*60}")

# Expected value
expected = 147.41
actual = np.mean(values)
diff = actual - expected

print(f"\nExpected: {expected:.2f} MW")
print(f"Actual:   {actual:.2f} MW")
print(f"Difference: {diff:+.2f} MW ({(diff/expected)*100:+.2f}%)")

if abs(diff) < 0.1:
    print("\n✅ MATCH! Calculation is correct.")
else:
    print(f"\n⚠️ MISMATCH! Off by {abs(diff):.2f} MW")
