import pandas as pd
import glob
import os

print("=" * 100)
print("READING ALL PARQUET FILES - DATA AVAILABILITY FOR YOUR 3 TAGS")
print("=" * 100)

target_tags = ['TURBINE_LOADMW', 'BEARING_VIB_HP_REAR-X', 'TOTAL_COAL_FLOW']
data_dir = 'D:/OpcLogs/Data'

# Get all parquet files
files = glob.glob(os.path.join(data_dir, '*.parquet'))
print(f"\nFound {len(files)} parquet files in {data_dir}\n")

total_data = {tag: {'timestamps': set(), 'rows': 0, 'files': 0} for tag in target_tags}
file_details = []

for idx, file_path in enumerate(files, 1):
    filename = os.path.basename(file_path)
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    
    try:
        # Read file
        df = pd.read_parquet(file_path)
        
        # Check if it has the tags we want
        available_tags = df['TagId'].unique().tolist() if 'TagId' in df.columns else []
        matching_tags = [tag for tag in target_tags if tag in available_tags]
        
        if not matching_tags:
            continue  # Skip files without our tags
        
        file_info = {
            'filename': filename,
            'size_mb': file_size_mb,
            'total_rows': len(df),
            'timestamps': df['Timestamp'].nunique() if 'Timestamp' in df.columns else 0,
            'date_range': f"{df['Timestamp'].min()} to {df['Timestamp'].max()}" if 'Timestamp' in df.columns else 'N/A',
            'tags': {}
        }
        
        # Check each target tag
        for tag in target_tags:
            if tag in available_tags:
                tag_data = df[df['TagId'] == tag]
                timestamps = set(tag_data['Timestamp'].unique())
                
                file_info['tags'][tag] = {
                    'rows': len(tag_data),
                    'timestamps': len(timestamps)
                }
                
                # Add to totals
                total_data[tag]['timestamps'].update(timestamps)
                total_data[tag]['rows'] += len(tag_data)
                total_data[tag]['files'] += 1
        
        file_details.append(file_info)
        
        # Print progress every 10 files
        if idx % 10 == 0:
            print(f"  Processed {idx}/{len(files)} files...")
            
    except Exception as e:
        print(f"  ❌ Error reading {filename}: {e}")
        continue

print(f"\n✅ Processing complete!")

# Sort by most recent first (if date in filename)
file_details.sort(key=lambda x: x['filename'], reverse=True)

# Print detailed results
print("\n" + "=" * 100)
print("FILES WITH YOUR 3 TAGS:")
print("=" * 100)

for file_info in file_details[:20]:  # Show first 20 files
    print(f"\n📁 {file_info['filename']} ({file_info['size_mb']:.2f} MB)")
    print(f"   Total rows: {file_info['total_rows']:,}")
    print(f"   Timestamps: {file_info['timestamps']:,}")
    print(f"   Date range: {file_info['date_range']}")
    
    for tag, data in file_info['tags'].items():
        print(f"   ✓ {tag}: {data['rows']:,} rows, {data['timestamps']:,} timestamps")

if len(file_details) > 20:
    print(f"\n... and {len(file_details) - 20} more files")

# Print totals
print("\n" + "=" * 100)
print("TOTAL DATA AVAILABLE (ALL FILES COMBINED):")
print("=" * 100)

for tag in target_tags:
    data = total_data[tag]
    print(f"\n{tag}:")
    print(f"  Total unique timestamps: {len(data['timestamps']):,}")
    print(f"  Total rows: {data['rows']:,}")
    print(f"  Files containing this tag: {data['files']}")
    
    if len(data['timestamps']) > 0:
        timestamps = sorted(list(data['timestamps']))
        print(f"  Date range: {timestamps[0]} to {timestamps[-1]}")
        
        # Calculate span
        first_date = pd.to_datetime(timestamps[0])
        last_date = pd.to_datetime(timestamps[-1])
        days = (last_date - first_date).days
        print(f"  Time span: {days} days ({days/365.25:.1f} years)")

print("\n" + "=" * 100)
print("WHAT THIS MEANS:")
print("=" * 100)
print("When you query for these 3 tags, the system will:")
print(f"1. Load data from {max(total_data[tag]['files'] for tag in target_tags)} files")
print(f"2. Give you up to {max(len(total_data[tag]['timestamps']) for tag in target_tags):,} unique timestamps")
print(f"3. In WIDE format: 1 row per timestamp with all 3 tag columns")
print(f"4. The exact number depends on your date range filter")
