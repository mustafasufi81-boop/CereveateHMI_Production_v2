"""
Analyze actual vibration data ranges to set realistic alarm/trip limits
"""
import pandas as pd
import glob
import os

print("=" * 80)
print("ANALYZING ACTUAL VIBRATION RANGES FOR ALARM LIMIT CONFIGURATION")
print("=" * 80)

# Find parquet files
data_dir = r"D:\OpcLogs\Data"
if not os.path.exists(data_dir):
    print(f"❌ Data directory not found: {data_dir}")
    print("Please update the path to your actual parquet files location")
    exit(1)

parquet_files = glob.glob(os.path.join(data_dir, "*.parquet"))
if not parquet_files:
    print(f"❌ No parquet files found in {data_dir}")
    exit(1)

print(f"✅ Found {len(parquet_files)} parquet files\n")

# Read all data
all_data = []
for file in parquet_files[:10]:  # Limit to first 10 files for speed
    try:
        df = pd.read_parquet(file)
        all_data.append(df)
    except Exception as e:
        print(f"⚠️ Error reading {file}: {e}")

if not all_data:
    print("❌ No data loaded!")
    exit(1)

df = pd.concat(all_data, ignore_index=True)
print(f"✅ Loaded {len(df)} data points")
print(f"   Columns: {df.columns.tolist()}\n")

# Check data structure - it might be in TagId/Value format
if 'TagId' in df.columns and 'Value' in df.columns:
    print("📊 Data is in TagId/Value format - pivoting to wide format...")
    df_pivot = df.pivot_table(index='Timestamp', columns='TagId', values='Value', aggfunc='first')
    print(f"   Pivoted to {len(df_pivot.columns)} unique tags\n")
    df = df_pivot
else:
    print("📊 Data is already in wide format\n")

# Analyze vibration parameters
vibration_tags = [col for col in df.columns if 'VIB' in str(col).upper() or 'BEARING' in str(col).upper() or 'SHAFT' in str(col).upper()]

if not vibration_tags:
    print("❌ No vibration tags found in data!")
    print("Available columns:", df.columns.tolist())
    exit(1)

print(f"📊 Found {len(vibration_tags)} vibration parameters\n")
print("=" * 80)

results = {}

for tag in vibration_tags:
    try:
        # Convert to numeric, handle strings
        values = pd.to_numeric(df[tag], errors='coerce').dropna()
        
        if len(values) == 0:
            continue
        
        mean_val = values.mean()
        std_val = values.std()
        max_val = values.max()
        p95 = values.quantile(0.95)
        p99 = values.quantile(0.99)
        p999 = values.quantile(0.999)
        
        # Calculate recommended limits based on actual data
        # Industry standard approach (ISO 10816 / ISO 7919):
        # Warning = 95th percentile (normal operational variation)
        # Alarm = 99th percentile (unusual but not critical)
        # Trip = 99.9th percentile or Mean + 4*StdDev (protect against damage)
        # 
        # NOT using Max × 1.2 because max could be a transient spike/outlier
        
        statistical_trip = mean_val + (4 * std_val)  # 4-sigma covers 99.99%
        
        warning_limit = p95
        alarm_limit = p99
        trip_limit = max(p999, statistical_trip)  # Use whichever is higher for safety
        
        # Round to reasonable values
        warning_limit = round(warning_limit / 5) * 5  # Round to nearest 5
        alarm_limit = round(alarm_limit / 5) * 5
        trip_limit = round(trip_limit / 10) * 10  # Round to nearest 10
        
        results[tag] = {
            'mean': mean_val,
            'std': std_val,
            'max': max_val,
            'p95': p95,
            'p99': p99,
            'p999': p999,
            'warning': warning_limit,
            'alarm': alarm_limit,
            'trip': trip_limit
        }
        
        print(f"📈 {tag}")
        print(f"   Actual Data Range:")
        print(f"      Mean: {mean_val:.2f} µm")
        print(f"      Std Dev: {std_val:.2f} µm")
        print(f"      Max: {max_val:.2f} µm  (could be spike!)")
        print(f"      95th percentile: {p95:.2f} µm")
        print(f"      99th percentile: {p99:.2f} µm")
        print(f"      99.9th percentile: {p999:.2f} µm")
        print(f"   📊 RECOMMENDED LIMITS (ISO 10816/7919):")
        print(f"      ⚠️  Warning: {warning_limit} µm  (95th percentile)")
        print(f"      🔶 Alarm:   {alarm_limit} µm  (99th percentile)")
        print(f"      🔴 Trip:    {trip_limit} µm  (99.9th percentile or Mean+4×Std)")
        print()
        
    except Exception as e:
        print(f"⚠️ Error analyzing {tag}: {e}\n")

# Generate configuration JSON
print("=" * 80)
print("GENERATED CONFIGURATION FOR trends-config.json")
print("=" * 80)
print()
print('"AlarmLimits": {')

for i, (tag, limits) in enumerate(results.items()):
    comma = "," if i < len(results) - 1 else ""
    print(f'  "{tag}": {{ "Warning": {limits["warning"]}, "Alarm": {limits["alarm"]}, "Trip": {limits["trip"]} }}{comma}')

print('}')
print()

# Group by type
print("=" * 80)
print("DEFAULT LIMITS BY TYPE (for fallback)")
print("=" * 80)

bearing_tags = {k: v for k, v in results.items() if 'BEARING' in k.upper()}
shaft_tags = {k: v for k, v in results.items() if 'SHAFT' in k.upper() and 'BEARING' not in k.upper()}

if bearing_tags:
    avg_bearing_warning = round(sum(v['warning'] for v in bearing_tags.values()) / len(bearing_tags) / 5) * 5
    avg_bearing_alarm = round(sum(v['alarm'] for v in bearing_tags.values()) / len(bearing_tags) / 5) * 5
    avg_bearing_trip = round(sum(v['trip'] for v in bearing_tags.values()) / len(bearing_tags) / 10) * 10
    
    print(f"\n🔩 BEARING VIBRATION (avg of {len(bearing_tags)} tags):")
    print(f'   "BearingVibration": {{ "Warning": {avg_bearing_warning}, "Alarm": {avg_bearing_alarm}, "Trip": {avg_bearing_trip} }}')

if shaft_tags:
    avg_shaft_warning = round(sum(v['warning'] for v in shaft_tags.values()) / len(shaft_tags) / 5) * 5
    avg_shaft_alarm = round(sum(v['alarm'] for v in shaft_tags.values()) / len(shaft_tags) / 5) * 5
    avg_shaft_trip = round(sum(v['trip'] for v in shaft_tags.values()) / len(shaft_tags) / 10) * 10
    
    print(f"\n⚙️ SHAFT VIBRATION (avg of {len(shaft_tags)} tags):")
    print(f'   "ShaftVibration": {{ "Warning": {avg_shaft_warning}, "Alarm": {avg_shaft_alarm}, "Trip": {avg_shaft_trip} }}')

print("\n" + "=" * 80)
print("✅ Analysis complete - Use these values in trends-config.json")
print("=" * 80)
