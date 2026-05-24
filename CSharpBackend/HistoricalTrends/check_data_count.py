import pandas as pd
import glob

files = glob.glob('D:/OpcLogs/Data/*.parquet')
print(f"Total files: {len(files)}")
print("\nChecking first 5 files:")

total_rows = 0
for f in files[:5]:
    df = pd.read_parquet(f)
    print(f"  {f}: {len(df)} rows, Tags: {df['TagId'].unique().tolist()}")
    total_rows += len(df)

print(f"\nTotal rows (first 5 files): {total_rows}")

# Check a single file structure
if files:
    df = pd.read_parquet(files[0])
    print(f"\nSample file structure:")
    print(df.head(20))
    print(f"\nColumns: {df.columns.tolist()}")
    print(f"Unique timestamps: {df['Timestamp'].nunique()}")
    print(f"Unique tags: {df['TagId'].nunique()}")
    print(f"Total rows: {len(df)}")
