import pandas as pd
from datetime import datetime

print("START")
df = pd.read_parquet("D:/OpcLogs/Data/ALL_SENSORS_COMPLETE_FORWARDFILL.parquet")
print(f"Loaded: {len(df)} rows")
df['Timestamp'] = pd.to_datetime(df['Timestamp'])
print(f"Date range: {df['Timestamp'].min()} to {df['Timestamp'].max()}")

# Filter Jan 15
start = datetime(2025, 1, 15)
end = datetime(2025, 1, 16)
filtered = df[(df['Timestamp'] >= start) & (df['Timestamp'] < end)]
print(f"Jan 15: {len(filtered)} rows")
print("DONE")
