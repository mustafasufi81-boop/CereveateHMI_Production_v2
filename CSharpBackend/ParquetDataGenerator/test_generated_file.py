import pandas as pd
import glob
import sys

# Find the most recent parquet file
files = sorted(glob.glob('D:/OpcLogs/Data/*.parquet'))
if not files:
    print("No parquet files found in D:/OpcLogs/Data/")
    sys.exit(1)

# Use the most recent file
latest_file = files[-1]
print(f"Reading file: {latest_file}")

# Read the generated file
df = pd.read_parquet(latest_file)

print("=" * 70)
print("GENERATED FILE ANALYSIS")
print("=" * 70)

print("\n1. FILE STRUCTURE:")
print(f"   Columns: {df.columns.tolist()}")
print(f"   Shape: {df.shape} (rows x columns)")
print(f"   Data types:\n{df.dtypes}")

print("\n2. DATE RANGE:")
print(f"   Start: {df['Timestamp'].min()}")
print(f"   End: {df['Timestamp'].max()}")

print("\n3. TAGS FOUND:")
unique_tags = df['TagId'].unique()
print(f"   Total unique tags: {len(unique_tags)}")
for tag in sorted(unique_tags):
    count = len(df[df['TagId'] == tag])
    print(f"   - {tag}: {count} records")

print("\n4. NULL/DOWNTIME CHECK:")
null_counts = df.isnull().sum()
print(f"   Null Timestamps: {null_counts['Timestamp']}")
print(f"   Null TagIds: {null_counts['TagId']}")
print(f"   Null Values: {null_counts['Value']}")

if null_counts['Value'] > 0:
    print(f"\n   ⚠️ DOWNTIME DETECTED: {null_counts['Value']} null values found")
    downtime_data = df[df['Value'].isnull()]
    print(f"   Downtime periods: {len(downtime_data)} records")
    print(f"   Tags affected:\n{downtime_data['TagId'].value_counts()}")

print("\n5. SAMPLE DATA (First 20 records):")
print(df.head(20))

print("\n6. GENERATOR_LOAD_MW SAMPLE:")
load_data = df[df['TagId'] == 'GENERATOR_LOAD_MW']
if len(load_data) > 0:
    print(load_data.head(10))
    print(f"\n   Stats: Mean={load_data['Value'].mean():.2f}, Min={load_data['Value'].min():.2f}, Max={load_data['Value'].max():.2f}")
else:
    print("   No GENERATOR_LOAD_MW data found")

print("\n7. COMPARISON WITH EXPECTED FORMAT:")
expected_cols = ['Timestamp', 'TagId', 'Value']
if df.columns.tolist() == expected_cols:
    print("   ✅ Format matches expected: Timestamp, TagId, Value")
else:
    print(f"   ❌ Format mismatch! Expected: {expected_cols}, Got: {df.columns.tolist()}")
