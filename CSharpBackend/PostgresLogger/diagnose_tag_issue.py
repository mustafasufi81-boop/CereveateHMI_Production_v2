"""
COMPREHENSIVE TAG DIAGNOSTIC TOOL
Analyzes the complete tag flow from parquet → config → database
"""

import json
import psycopg2
import pyarrow.parquet as pq
import glob
from pathlib import Path

print("=" * 80)
print("CEREVEATE TAG DIAGNOSTIC REPORT")
print("=" * 80)
print()

# 1. CHECK PARQUET FILES
print("1. PARQUET FILES")
print("-" * 80)
parquet_files = glob.glob('D:/OpcLogs/Data/*.parquet')
print(f"Found {len(parquet_files)} parquet files")

if parquet_files:
    sample_file = parquet_files[0]
    df = pq.read_table(sample_file).to_pandas()
    print(f"Sample file: {Path(sample_file).name}")
    print(f"Format: LONG (TagId, Timestamp, Value, Quality)")
    print(f"Total rows: {len(df)}")
    
    unique_tags = df['TagId'].unique()
    print(f"\nUnique TagIds in parquet: {len(unique_tags)}")
    print("\nFirst 30 TagIds:")
    for i, tag in enumerate(sorted(unique_tags)[:30], 1):
        print(f"  {i:2d}. {tag}")
    
    if len(unique_tags) > 30:
        print(f"  ... and {len(unique_tags) - 30} more")
else:
    print("ERROR: No parquet files found!")
    unique_tags = []

print()

# 2. CHECK TAG_MAPPINGS CONFIG
print("2. TAG MAPPINGS CONFIGURATION (app_config.json)")
print("-" * 80)
try:
    with open('config/app_config.json', 'r') as f:
        config = json.load(f)
    
    tag_mappings = config.get('tag_mappings', [])
    print(f"Total mapped tags: {len(tag_mappings)}")
    print(f"Enabled tags: {sum(1 for m in tag_mappings if m.get('enabled', True))}")
    
    print("\nConfigured mappings:")
    for i, mapping in enumerate(tag_mappings, 1):
        status = "✓ ENABLED" if mapping.get('enabled', True) else "✗ DISABLED"
        print(f"  {i}. {mapping['parquet_column']:<50} {status}")
    
    mapped_columns = set(m['parquet_column'] for m in tag_mappings if m.get('enabled', True))
    
except Exception as e:
    print(f"ERROR reading config: {e}")
    mapped_columns = set()

print()

# 3. COMPARE PARQUET vs CONFIG
print("3. PARQUET vs CONFIG COMPARISON")
print("-" * 80)
if unique_tags:
    tags_in_parquet = set(unique_tags)
    tags_mapped = mapped_columns
    tags_unmapped = tags_in_parquet - tags_mapped
    tags_mapped_but_not_in_parquet = tags_mapped - tags_in_parquet
    
    print(f"Tags in parquet files:           {len(tags_in_parquet)}")
    print(f"Tags mapped in config:           {len(tags_mapped)}")
    print(f"Tags UNMAPPED (won't import):    {len(tags_unmapped)}")
    print(f"Tags mapped but missing in file: {len(tags_mapped_but_not_in_parquet)}")
    
    if tags_unmapped:
        print(f"\n⚠ UNMAPPED TAGS (first 20):")
        for i, tag in enumerate(sorted(tags_unmapped)[:20], 1):
            print(f"  {i:2d}. {tag}")
        if len(tags_unmapped) > 20:
            print(f"  ... and {len(tags_unmapped) - 20} more")
    
    if tags_mapped_but_not_in_parquet:
        print(f"\n⚠ MAPPED BUT NOT IN PARQUET:")
        for i, tag in enumerate(sorted(tags_mapped_but_not_in_parquet), 1):
            print(f"  {i}. {tag}")

print()

# 4. CHECK TAG_CATALOG TABLE
print("4. TAG_CATALOG TABLE (Discovered by Importer)")
print("-" * 80)
try:
    conn = psycopg2.connect(
        host='localhost', 
        port=5432, 
        database='Cereveate', 
        user='cereveate', 
        password='cereveate@222'
    )
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM tag_catalog")
    catalog_count = cur.fetchone()[0]
    print(f"Total tags in catalog: {catalog_count}")
    
    cur.execute("""
        SELECT tag_id, last_seen 
        FROM tag_catalog 
        ORDER BY last_seen DESC 
        LIMIT 30
    """)
    catalog_tags = cur.fetchall()
    
    print("\nLatest tags in catalog:")
    for i, (tag_id, last_seen) in enumerate(catalog_tags, 1):
        in_config = "✓ MAPPED" if tag_id in mapped_columns else "✗ NOT MAPPED"
        print(f"  {i:2d}. {tag_id:<50} {in_config}")
    
    catalog_tag_set = set(row[0] for row in catalog_tags)
    
except Exception as e:
    print(f"ERROR querying tag_catalog: {e}")
    catalog_tag_set = set()
    cur = None

print()

# 5. CHECK SENSOR_DATA TABLE
print("5. SENSOR_DATA TABLE (Actually Imported)")
print("-" * 80)
if cur:
    try:
        cur.execute("""
            SELECT DISTINCT tag_name, COUNT(*) as record_count
            FROM sensor_data
            GROUP BY tag_name
            ORDER BY tag_name
        """)
        data_tags = cur.fetchall()
        
        print(f"Total unique tags imported: {len(data_tags)}")
        print("\nImported tags with record counts:")
        for i, (tag_name, count) in enumerate(data_tags, 1):
            print(f"  {i:2d}. {tag_name:<50} {count:,} records")
        
        data_tag_set = set(row[0] for row in data_tags)
        
    except Exception as e:
        print(f"ERROR querying sensor_data: {e}")
        data_tag_set = set()
    
    cur.close()
    conn.close()
else:
    data_tag_set = set()

print()

# 6. FINAL ANALYSIS
print("6. ROOT CAUSE ANALYSIS")
print("=" * 80)

if unique_tags:
    tags_in_parquet = set(unique_tags)
    
    print("\n✓ WORKING CORRECTLY:")
    working_tags = data_tag_set
    if working_tags:
        print(f"  {len(working_tags)} tags are successfully flowing: parquet → config → database")
        for tag in sorted(working_tags):
            print(f"    - {tag}")
    else:
        print("  NONE! No data is being imported.")
    
    print("\n✗ PROBLEM TAGS:")
    problem_tags = tags_in_parquet - data_tag_set
    if problem_tags:
        print(f"  {len(problem_tags)} tags exist in parquet but NOT in database")
        print("\n  Reason: These tags are NOT mapped in app_config.json")
        print("\n  First 15 unmapped tags:")
        for i, tag in enumerate(sorted(problem_tags)[:15], 1):
            print(f"    {i:2d}. {tag}")
        if len(problem_tags) > 15:
            print(f"    ... and {len(problem_tags) - 15} more")
    
    print("\n" + "=" * 80)
    print("SOLUTION:")
    print("=" * 80)
    print("""
To import tags, you MUST add them to app_config.json > tag_mappings array.

For LONG FORMAT parquet (TagId, Timestamp, Value):
- The 'parquet_column' field MUST EXACTLY match the TagId value

Example:
{
  "parquet_column": "BEARING_VIB_HP_REAR-X",   ← MUST match TagId exactly
  "tag_name": "BEARING_VIB_HP_REAR-X",
  "plant": "PowerPlant1",
  "asset": "Turbine",
  "subsystem": "HP",
  "unit": "mm/sec",
  "sampling_frequency_seconds": 1,
  "enabled": true
}

HOW TO ADD TAGS:
1. Via Web UI (RECOMMENDED):
   - Start server: .\\start_server.bat
   - Open: http://localhost:6001
   - Go to "Tag Configuration" tab
   - Click "Discover Tags" button
   - Manually add each tag using the "Add New Tag" form

2. Via Manual Edit (app_config.json):
   - Edit: PostgresLogger\\config\\app_config.json
   - Add entries to "tag_mappings" array
   - Restart importer service
    """)
    
    if problem_tags:
        print(f"\nYou need to map {len(problem_tags)} tags to start importing their data.\n")

print("=" * 80)
print("END OF DIAGNOSTIC REPORT")
print("=" * 80)
