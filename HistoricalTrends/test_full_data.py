import pandas as pd
import sys
sys.path.append('.')

from parquet_service import ParquetDataService
from config_reader import ConfigReader

# Initialize
config = ConfigReader()
service = ParquetDataService(
    config.get_data_directory(),
    config.get_backup_directory()
)

# Test with FULL date range from the big file
start_date = '2015-08-30T00:00:00Z'
end_date = '2016-12-31T23:59:59Z'  # Extended range
tags = ['TURBINE_LOADMW', 'NOX_PPM']

print("=" * 80)
print("TESTING FULL DATE RANGE")
print("=" * 80)
print(f"Query: {start_date} to {end_date}")
print(f"Tags: {tags}")
print()

# Read data using service
df = service.read_parquet_data(start_date, end_date, tags)

print(f"\nRESULT:")
print(f"  Total rows returned (WIDE format): {len(df)}")
print(f"  Columns: {df.columns.tolist()}")

if 'Timestamp' in df.columns:
    print(f"  Unique timestamps: {df['Timestamp'].nunique()}")
    print(f"  Date range: {df['Timestamp'].min()} to {df['Timestamp'].max()}")

for tag in tags:
    if tag in df.columns:
        non_null = df[tag].notna().sum()
        print(f"  {tag}: {non_null} non-null values ({(non_null/len(df)*100):.1f}%)")

# Check what the LONG format would be
print("\n" + "=" * 80)
print("LONG FORMAT ANALYSIS (What you might expect)")
print("=" * 80)

import glob
files = glob.glob('D:/OpcLogs/Data/ALL_SENSORS_COMPLETE*.parquet')
if files:
    raw_df = pd.read_parquet(files[0])
    raw_df['Timestamp'] = pd.to_datetime(raw_df['Timestamp'])
    start_dt = pd.to_datetime(start_date.replace('Z', ''))
    end_dt = pd.to_datetime(end_date.replace('Z', ''))
    
    filtered = raw_df[
        (raw_df['Timestamp'] >= start_dt) &
        (raw_df['Timestamp'] <= end_dt) &
        (raw_df['TagId'].isin(tags))
    ]
    
    print(f"  LONG format total rows: {len(filtered)} (2 tags × timestamps)")
    print(f"  Unique timestamps: {filtered['Timestamp'].nunique()}")
    print(f"  WIDE format rows: {filtered['Timestamp'].nunique()}")
    print()
    print(f"  Formula: {len(tags)} tags × {filtered['Timestamp'].nunique()} timestamps = {len(tags) * filtered['Timestamp'].nunique()} rows in LONG format")
    print(f"  But WIDE format = {filtered['Timestamp'].nunique()} rows (one row per timestamp)")
    print()
    print(f"  ✅ Service returned: {len(df)} rows")
    print(f"  ✅ Expected (wide): {filtered['Timestamp'].nunique()} rows")
    print(f"  ✅ Match: {'YES' if len(df) == filtered['Timestamp'].nunique() else 'NO'}")

# Now test with 21 tags to see the multiplication effect
print("\n" + "=" * 80)
print("TESTING WITH ALL 21 TAGS (Like the full sensor file)")
print("=" * 80)

all_tags = raw_df['TagId'].unique().tolist()
print(f"All tags in file: {len(all_tags)} tags")

df_all = service.read_parquet_data(start_date, end_date, all_tags)
print(f"\nRESULT with {len(all_tags)} tags:")
print(f"  WIDE format rows: {len(df_all)}")

filtered_all = raw_df[
    (raw_df['Timestamp'] >= start_dt) &
    (raw_df['Timestamp'] <= end_dt)
]
print(f"  LONG format would be: {len(filtered_all)} rows")
print(f"  Unique timestamps: {filtered_all['Timestamp'].nunique()}")
print(f"  Calculation: {len(all_tags)} tags × {filtered_all['Timestamp'].nunique()} timestamps = {len(all_tags) * filtered_all['Timestamp'].nunique()}")
