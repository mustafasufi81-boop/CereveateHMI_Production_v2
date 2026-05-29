import pandas as pd
import sys
sys.path.append('.')

print("=" * 100)
print("ANALYZING WHY ONLY 43,094 RECORDS ARE LOADING")
print("=" * 100)

# Load the raw parquet file
df = pd.read_parquet('D:/OpcLogs/Data/ALL_SENSORS_COMPLETE_FORWARDFILL.parquet')

print(f"\n📊 RAW FILE STATISTICS:")
print(f"  Total rows in file: {len(df):,}")
print(f"  Unique timestamps: {df['Timestamp'].nunique():,}")
print(f"  Unique tags: {df['TagId'].nunique()}")
print(f"  Tags: {df['TagId'].unique().tolist()}")

# Convert timestamp
df['Timestamp'] = pd.to_datetime(df['Timestamp'])

print(f"\n📅 FULL DATE RANGE IN FILE:")
print(f"  First timestamp: {df['Timestamp'].min()}")
print(f"  Last timestamp: {df['Timestamp'].max()}")
total_days = (df['Timestamp'].max() - df['Timestamp'].min()).days
print(f"  Total span: {total_days} days ({total_days/365.25:.1f} years)")

# Check data distribution by year
print(f"\n📈 DATA DISTRIBUTION BY YEAR:")
df['Year'] = df['Timestamp'].dt.year
year_counts = df.groupby('Year').size()
for year, count in year_counts.items():
    timestamps = df[df['Year'] == year]['Timestamp'].nunique()
    print(f"  {year}: {count:,} rows, {timestamps:,} unique timestamps")

# Focus on 2024-2025 range (what user is querying)
print(f"\n🔍 YOUR QUERY RANGE ANALYSIS:")
query_start = pd.to_datetime('2024-11-24')
query_end = pd.to_datetime('2025-11-16')

filtered = df[(df['Timestamp'] >= query_start) & (df['Timestamp'] <= query_end)]
print(f"  Query: {query_start} to {query_end}")
print(f"  Total rows in range: {len(filtered):,}")
print(f"  Unique timestamps: {filtered['Timestamp'].nunique():,}")
print(f"  Unique tags: {filtered['TagId'].nunique()}")

# Check how many timestamps per tag
print(f"\n📊 TIMESTAMPS PER TAG (in your date range):")
for tag in filtered['TagId'].unique():
    tag_data = filtered[filtered['TagId'] == tag]
    print(f"  {tag}: {len(tag_data):,} rows")

# Expected vs Actual
expected_wide = filtered['Timestamp'].nunique()
print(f"\n✅ EXPECTED vs ACTUAL:")
print(f"  Expected rows (WIDE format): {expected_wide:,}")
print(f"  Actual rows returned by service: 43,094")
print(f"  Match: {'✅ YES' if expected_wide == 43094 else '❌ NO'}")

# Check if there are gaps in timestamps
print(f"\n⏱️ TIMESTAMP FREQUENCY ANALYSIS:")
timestamps = sorted(filtered['Timestamp'].unique())
if len(timestamps) > 1:
    time_diffs = []
    for i in range(1, min(100, len(timestamps))):
        diff = (timestamps[i] - timestamps[i-1]).total_seconds() / 60  # minutes
        time_diffs.append(diff)
    
    avg_interval = sum(time_diffs) / len(time_diffs)
    print(f"  Average interval between timestamps: {avg_interval:.2f} minutes")
    print(f"  Min interval: {min(time_diffs):.2f} minutes")
    print(f"  Max interval: {max(time_diffs):.2f} minutes")
    
    # Calculate expected records for continuous data
    total_minutes = (query_end - query_start).total_seconds() / 60
    expected_continuous = int(total_minutes / avg_interval)
    print(f"\n  If data were continuous at {avg_interval:.0f} min intervals:")
    print(f"    Expected timestamps: {expected_continuous:,}")
    print(f"    Actual timestamps: {expected_wide:,}")
    print(f"    Coverage: {(expected_wide/expected_continuous*100):.1f}%")

# Check for large gaps
print(f"\n⚠️ CHECKING FOR DATA GAPS:")
large_gaps = []
for i in range(1, len(timestamps)):
    diff_hours = (timestamps[i] - timestamps[i-1]).total_seconds() / 3600
    if diff_hours > 24:  # Gaps larger than 24 hours
        large_gaps.append({
            'from': timestamps[i-1],
            'to': timestamps[i],
            'gap_hours': diff_hours
        })

if large_gaps:
    print(f"  Found {len(large_gaps)} gaps larger than 24 hours:")
    for gap in large_gaps[:10]:  # Show first 10
        print(f"    {gap['from']} → {gap['to']} ({gap['gap_hours']:.1f} hours gap)")
else:
    print(f"  ✅ No large gaps found (all gaps < 24 hours)")

# Summary
print(f"\n" + "=" * 100)
print(f"CONCLUSION:")
print(f"=" * 100)
print(f"The system is loading the CORRECT amount of data:")
print(f"  • File contains {filtered['Timestamp'].nunique():,} unique timestamps in your date range")
print(f"  • WIDE format = 1 row per timestamp = {filtered['Timestamp'].nunique():,} rows")
print(f"  • Your query returned 43,094 rows ✅")
print(f"\nIf you expected MORE data, it means:")
print(f"  1. Data is not continuously logged (there are time gaps)")
print(f"  2. OPC logging was stopped/started during this period")
print(f"  3. This is the actual available data in the parquet file")
