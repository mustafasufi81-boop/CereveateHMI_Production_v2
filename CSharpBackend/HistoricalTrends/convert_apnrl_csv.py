import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from datetime import datetime
import os

# Input CSV file
csv_file = r"D:\Adhunik\Adhunik_Data\APNRL-1 DATA.csv"
# Output parquet file
output_file = r"D:\Adhunik\Adhunik_Data\APNRL-1_DATA_converted.parquet"

print(f"Converting: {csv_file}")
print(f"Output: {output_file}")
print()

# Read the CSV file
print("Reading CSV file...")
df = pd.read_csv(csv_file)

print(f"CSV has {len(df)} rows and {len(df.columns)} columns")
print(f"Columns: {list(df.columns)}")
print()

# Convert from wide format to long format
print("Converting to long format...")
records = []
row_id = 1

# Identify date/time columns (usually first 2 columns)
date_col = df.columns[0]
time_col = df.columns[1]

# Get tag columns (all columns except Date and Time)
tag_columns = [col for col in df.columns if col not in [date_col, time_col]]

print(f"Date column: {date_col}")
print(f"Time column: {time_col}")
print(f"Found {len(tag_columns)} tag columns")
print()

# Process each row
for idx, row in df.iterrows():
    # Combine date and time to create timestamp
    date_str = str(row[date_col])
    time_str = str(row[time_col])
    
    try:
        # Try different datetime formats
        timestamp_str = f"{date_str} {time_str}"
        
        # Attempt to parse - adjust format as needed
        try:
            timestamp = pd.to_datetime(timestamp_str, format='%d-%m-%Y %H:%M:%S')
        except:
            try:
                timestamp = pd.to_datetime(timestamp_str, format='%m/%d/%Y %H:%M:%S')
            except:
                try:
                    timestamp = pd.to_datetime(timestamp_str)
                except:
                    print(f"Warning: Could not parse timestamp at row {idx}: {timestamp_str}")
                    continue
        
        # Create a record for each tag in this row
        for tag_name in tag_columns:
            value = str(row[tag_name])
            
            records.append({
                'RowId': row_id,
                'TagId': tag_name,
                'Timestamp': timestamp,
                'Value': value if pd.notna(row[tag_name]) else 'NULL',
                'Quality': 'GOOD' if pd.notna(row[tag_name]) and value != '' else 'BAD'
            })
            row_id += 1
    
    except Exception as e:
        print(f"Error processing row {idx}: {e}")
        continue
    
    # Progress indicator
    if (idx + 1) % 1000 == 0:
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
print("First few records:")
print(result_df.head(10))
