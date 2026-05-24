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

# Test query
start_date = '2015-08-30T00:00:00Z'
end_date = '2015-12-31T23:59:59Z'
tags = ['TURBINE_LOADMW', 'NOX_PPM']

print("=" * 80)
print("TESTING DATA RETRIEVAL")
print("=" * 80)
print(f"Query: {start_date} to {end_date}")
print(f"Tags: {tags}")
print()

# Read data using service
df = service.read_parquet_data(start_date, end_date, tags)

print(f"\nRESULT:")
print(f"  Total rows returned: {len(df)}")
print(f"  Columns: {df.columns.tolist()}")
print(f"\nFirst 10 rows:")
print(df.head(10))
print(f"\nLast 10 rows:")
print(df.tail(10))

# Check data structure
print(f"\nDATA ANALYSIS:")
if 'Timestamp' in df.columns:
    print(f"  Unique timestamps: {df['Timestamp'].nunique()}")
    print(f"  Date range: {df['Timestamp'].min()} to {df['Timestamp'].max()}")

for tag in tags:
    if tag in df.columns:
        non_null = df[tag].notna().sum()
        print(f"  {tag}: {non_null} non-null values out of {len(df)} rows")
        print(f"    - Null count: {df[tag].isna().sum()}")
        print(f"    - Min: {df[tag].min()}, Max: {df[tag].max()}")

# Now check the RAW parquet file to compare
print("\n" + "=" * 80)
print("CHECKING RAW PARQUET FILE")
print("=" * 80)

import glob
files = glob.glob('D:/OpcLogs/Data/ALL_SENSORS_COMPLETE*.parquet')
if files:
    raw_df = pd.read_parquet(files[0])
    print(f"\nRaw file: {files[0]}")
    print(f"  Total rows in file: {len(raw_df)}")
    print(f"  Unique timestamps: {raw_df['Timestamp'].nunique()}")
    print(f"  Tags in file: {raw_df['TagId'].unique().tolist()}")
    
    # Filter by our query
    raw_df['Timestamp'] = pd.to_datetime(raw_df['Timestamp'])
    start_dt = pd.to_datetime(start_date.replace('Z', ''))
    end_dt = pd.to_datetime(end_date.replace('Z', ''))
    
    filtered = raw_df[
        (raw_df['Timestamp'] >= start_dt) &
        (raw_df['Timestamp'] <= end_dt) &
        (raw_df['TagId'].isin(tags))
    ]
    
    print(f"\nFiltered raw data (matching query):")
    print(f"  Total rows: {len(filtered)}")
    print(f"  Unique timestamps: {filtered['Timestamp'].nunique()}")
    
    for tag in tags:
        tag_data = filtered[filtered['TagId'] == tag]
        print(f"  {tag}: {len(tag_data)} rows")
    
    print(f"\n EXPECTED WIDE FORMAT ROWS: {filtered['Timestamp'].nunique()}")
    print(f" ACTUAL RETURNED ROWS: {len(df)}")
    print(f" MATCH: {'✅ YES' if filtered['Timestamp'].nunique() == len(df) else '❌ NO'}")
