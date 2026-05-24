import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from datetime import datetime
import os

# Input CSV file
input_file = r"D:\OpcLogs\Data\ALL_SENSORS_COMPLETE_FORWARDFILL.csv"
# Output parquet file
output_file = r"D:\OpcLogs\Data\ALL_SENSORS_COMPLETE_FORWARDFILL.parquet"

print(f"Converting: {input_file}")
print(f"Output: {output_file}")
print()

# Read the CSV file
print("Reading CSV file...")
df = pd.read_csv(input_file)

print(f"Parquet has {len(df)} rows and {len(df.columns)} columns")
print(f"Columns: {list(df.columns)}")
print()

# Convert from wide format to long format
print("Converting to long format...")
records = []
row_id = 1

# Identify datetime column (usually first column or 'DateTime')
datetime_col = None
for col in df.columns:
    if 'datetime' in col.lower() or 'time' in col.lower() or 'date' in col.lower():
        datetime_col = col
        break

if datetime_col is None:
    # Assume first column is datetime
    datetime_col = df.columns[0]

print(f"DateTime column: {datetime_col}")

# Get tag columns (all columns except DateTime)
tag_columns = [col for col in df.columns if col != datetime_col]

print(f"Found {len(tag_columns)} tag columns")
print()

# Process each row
for idx, row in df.iterrows():
    # Get timestamp
    timestamp = row[datetime_col]
    
    # Ensure it's a datetime object
    if not pd.isna(timestamp):
        if not isinstance(timestamp, pd.Timestamp):
            try:
                timestamp = pd.to_datetime(timestamp)
            except:
                print(f"Warning: Could not parse timestamp at row {idx}: {timestamp}")
                continue
        
        # Create a record for each tag in this row
        for tag_name in tag_columns:
            value = row[tag_name]
            
            # Determine quality based on value
            if pd.isna(value):
                value_str = 'NULL'
                quality = 'BAD'
            else:
                value_str = str(value)
                quality = 'GOOD'
            
            records.append({
                'RowId': row_id,
                'TagId': tag_name,
                'Timestamp': timestamp,
                'Value': value_str,
                'Quality': quality
            })
            row_id += 1
    
    # Progress indicator
    if (idx + 1) % 10000 == 0:
        print(f"  Processed {idx + 1}/{len(df)} rows...")

print(f"\nCreated {len(records)} records")

# Create DataFrame in the correct format
print("Creating DataFrame...")
result_df = pd.DataFrame(records)

# Ensure correct data types
result_df['RowId'] = result_df['RowId'].astype('int64')
result_df['TagId'] = result_df['TagId'].astype('string')
result_df['Timestamp'] = pd.to_datetime(result_df['Timestamp'])
result_df['Value'] = result_df['Value'].astype('string')
result_df['Quality'] = result_df['Quality'].astype('string')

print(f"Final DataFrame: {len(result_df)} rows")
print(f"Columns: {list(result_df.columns)}")
print(f"Date range: {result_df['Timestamp'].min()} to {result_df['Timestamp'].max()}")
print(f"Tags: {result_df['TagId'].nunique()} unique tags")
print()

# Save to parquet
print("Saving to parquet format...")

# Define schema to match your standard format
schema = pa.schema([
    ('RowId', pa.int64()),
    ('TagId', pa.string()),
    ('Timestamp', pa.timestamp('us')),
    ('Value', pa.string()),
    ('Quality', pa.string())
])

# Convert to PyArrow table
table = pa.Table.from_pandas(result_df, schema=schema)

# Write parquet file
pq.write_table(table, output_file)

print(f"✓ Conversion complete!")
print(f"✓ Output file: {output_file}")
print(f"✓ File size: {os.path.getsize(output_file) / 1024 / 1024:.2f} MB")
print()

print("Summary:")
print(f"  - Original rows: {len(df)}")
print(f"  - Converted records: {len(result_df)}")
print(f"  - Tags: {result_df['TagId'].nunique()}")
print()
print("First few records:")
print(result_df.head(10))
