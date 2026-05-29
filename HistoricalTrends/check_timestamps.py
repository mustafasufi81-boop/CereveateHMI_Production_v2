import pandas as pd

df = pd.read_parquet('D:/OpcLogs/Data/ALL_SENSORS_COMPLETE_FORWARDFILL.parquet')

print(f'Total rows: {len(df)}')
print(f'Unique timestamps: {df["Timestamp"].nunique()}')
print(f'Unique tags: {df["TagId"].nunique()}')
print(f'Date range: {df["Timestamp"].min()} to {df["Timestamp"].max()}')
print(f'\nSample timestamps (first 30):')
print(df["Timestamp"].unique()[:30])
print(f'\nTimestamp frequency:')
print(df.groupby('Timestamp').size().head(10))
