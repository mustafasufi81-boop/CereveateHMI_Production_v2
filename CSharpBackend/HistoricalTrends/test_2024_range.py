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

# Test query that might give 43,094 results  
# If 43,094 is the WIDE format, then with 2 tags you'd have ~86K in LONG format
# Let's test a realistic 2024-2025 range

start_date = '2024-01-01T00:00:00Z'
end_date = '2025-11-20T23:59:59Z'
tags = ['TURBINE_LOADMW', 'NOX_PPM']

print("=" * 80)
print("TESTING 2024-2025 DATE RANGE")
print("=" * 80)
print(f"Query: {start_date} to {end_date}")
print(f"Tags: {tags}")
print()

df = service.read_parquet_data(start_date, end_date, tags)

print(f"\nRESULT:")
print(f"  WIDE format rows: {len(df)}")
print(f"  Columns: {df.columns.tolist()}")

if 'Timestamp' in df.columns:
    print(f"  Unique timestamps: {df['Timestamp'].nunique()}")
    non_null_turbine = df['TURBINE_LOADMW'].notna().sum() if 'TURBINE_LOADMW' in df.columns else 0
    non_null_nox = df['NOX_PPM'].notna().sum() if 'NOX_PPM' in df.columns else 0
    
    print(f"  TURBINE_LOADMW: {non_null_turbine} non-null ({(non_null_turbine/len(df)*100):.1f}%)")
    print(f"  NOX_PPM: {non_null_nox} non-null ({(non_null_nox/len(df)*100):.1f}%)")
    
    # Calculate what LONG format would be
    total_non_null = non_null_turbine + non_null_nox
    print(f"\n  LONG format equivalent: {total_non_null} rows (sum of all non-null values)")
    print(f"  Formula: {non_null_turbine} (TURBINE) + {non_null_nox} (NOX) = {total_non_null}")

# Check if this matches the 43,094 you mentioned
if abs(len(df) - 43094) < 100:
    print(f"\n  ⚠️ FOUND IT! This query returns {len(df)} rows, close to your 43,094!")
    print(f"  This is WIDE format - one row per timestamp with all tag columns")
