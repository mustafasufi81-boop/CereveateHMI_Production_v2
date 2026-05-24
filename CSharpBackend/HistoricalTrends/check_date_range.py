import pandas as pd
df = pd.read_parquet('D:/OpcLogs/Data/ALL_SENSORS_COMPLETE_FORWARDFILL.parquet')
df['Timestamp'] = pd.to_datetime(df['Timestamp'])
print(f"Data range in file: {df['Timestamp'].min()} to {df['Timestamp'].max()}")
print(f"Total rows: {len(df):,}")

# Check if Jan 1 to Mar 28, 2025 is in range
jan1 = pd.to_datetime('2025-01-01')
mar28 = pd.to_datetime('2025-03-28')
filtered = df[(df['Timestamp'] >= jan1) & (df['Timestamp'] <= mar28)]
print(f"\nData for Jan 1 - Mar 28, 2025: {len(filtered):,} rows")
if len(filtered) > 0:
    print(f"  ✓ Date range: {filtered['Timestamp'].min()} to {filtered['Timestamp'].max()}")
else:
    print("  ✗ NO DATA for this range")
