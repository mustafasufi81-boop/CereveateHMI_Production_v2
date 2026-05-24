import pyarrow.parquet as pq
import pandas as pd

# Read the other parquet file
file_path = r"D:\OpcLogs\Data\OpcData_20251117_025420.parquet"

print(f"Reading: {file_path}\n")

# Read parquet file
table = pq.read_table(file_path)
df = table.to_pandas()

print(f"File size: {len(df)} rows")
print(f"Columns: {list(df.columns)}")
print()

# Check format
if 'TagId' in df.columns:
    print("Format: LONG format (TagId, Timestamp, Value, Quality)")
    unique_tags = df['TagId'].unique()
    print(f"\nUnique tags in file: {len(unique_tags)}")
    print("\nTags found:")
    for i, tag in enumerate(sorted(unique_tags), 1):
        count = len(df[df['TagId'] == tag])
        print(f"  {i}. {tag} ({count} records)")
else:
    print("Format: WIDE format (columns are tag names)")
    tag_columns = [col for col in df.columns if col not in ['Timestamp', 'RowId']]
    print(f"\nUnique tags in file: {len(tag_columns)}")
    print("\nTags found:")
    for i, tag in enumerate(sorted(tag_columns), 1):
        print(f"  {i}. {tag}")

print("\n" + "="*60)
print("Sample data (first 5 rows):")
print(df.head())
