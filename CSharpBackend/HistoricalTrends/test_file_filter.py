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

print("=" * 100)
print("FILE FILTER TESTING")
print("=" * 100)

# Test 1: Last 1 year (Nov 2024 to Nov 2025)
print("\n1️⃣ TEST: Last 1 Year (2024-11-20 to 2025-11-20)")
print("-" * 100)
start_date1 = '2024-11-20T00:00:00Z'
end_date1 = '2025-11-20T23:59:59Z'
tags = ['TURBINE_LOADMW', 'NOX_PPM']

# Get relevant files
files1 = service._get_relevant_files(start_date1, end_date1, tags)
print(f"Query: {start_date1} to {end_date1}")
print(f"Tags: {tags}")
print(f"Files selected by filter: {len(files1)}")
for f in files1:
    import os
    print(f"  - {os.path.basename(f)}")

# Now actually load data
df1 = service.read_parquet_data(start_date1, end_date1, tags)
print(f"\nData loaded:")
print(f"  Total rows: {len(df1)}")
print(f"  Date range in data: {df1['Timestamp'].min()} to {df1['Timestamp'].max()}")

# Test 2: 2024 Nov to 2025 Nov (same as above)
print("\n\n2️⃣ TEST: Nov 2024 to Nov 2025 (Same as Test 1)")
print("-" * 100)
start_date2 = '2024-11-01T00:00:00Z'
end_date2 = '2025-11-30T23:59:59Z'

files2 = service._get_relevant_files(start_date2, end_date2, tags)
print(f"Query: {start_date2} to {end_date2}")
print(f"Tags: {tags}")
print(f"Files selected by filter: {len(files2)}")
for f in files2:
    import os
    print(f"  - {os.path.basename(f)}")

df2 = service.read_parquet_data(start_date2, end_date2, tags)
print(f"\nData loaded:")
print(f"  Total rows: {len(df2)}")
print(f"  Date range in data: {df2['Timestamp'].min()} to {df2['Timestamp'].max()}")

# Test 3: Check the file index cache to see what files are available
print("\n\n3️⃣ FILE INDEX CACHE ANALYSIS")
print("-" * 100)
print(f"Total files in cache: {len(service.file_index)}")
print(f"\nFiles containing TURBINE_LOADMW and NOX_PPM:")

for filename, meta in service.file_index.items():
    if 'TURBINE_LOADMW' in meta['tags'] and 'NOX_PPM' in meta['tags']:
        print(f"\n  📁 {filename}")
        print(f"     Time range: {meta['start']} to {meta['end']}")
        print(f"     Tags: {len(meta['tags'])} tags")
        
        # Parse dates
        file_start = pd.to_datetime(meta['start'])
        file_end = pd.to_datetime(meta['end'])
        query_start = pd.to_datetime(start_date1.replace('Z', ''))
        query_end = pd.to_datetime(end_date1.replace('Z', ''))
        
        # Check overlap
        overlaps = file_start <= query_end and file_end >= query_start
        print(f"     Overlaps with query (2024-11-20 to 2025-11-20): {'✅ YES' if overlaps else '❌ NO'}")

# Test 4: Show the actual filter logic
print("\n\n4️⃣ FILTER LOGIC EXPLANATION")
print("-" * 100)
print("The filter uses TIME OVERLAP check:")
print("  - File is selected if: file_start <= query_end AND file_end >= query_start")
print("  - This means any file that has data touching your date range gets selected")
print(f"\nFor query: {start_date1} to {end_date1}")
print("  Step 1: Find all files containing tags: TURBINE_LOADMW, NOX_PPM")
print("  Step 2: Check each file's time range")
print("  Step 3: Select files where time ranges overlap")
print("  Step 4: Load only those files")
print("  Step 5: Filter loaded data to exact query date range")
