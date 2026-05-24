"""
Verify that all database-mapped tags are available from the OPC server
Checks both server ProgID and tag names
"""
import psycopg2
import requests
import json
from collections import defaultdict
import os

# Load config
script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, 'config.json')
with open(config_path, 'r') as f:
    config = json.load(f)

# Database connection (use correct credentials)
db_config = {
    'host': 'localhost',
    'port': 5432,
    'database': 'Cereveate',
    'user': 'cereveate',
    'password': 'cereveate@222'
}
conn = psycopg2.connect(
    host=db_config['host'],
    port=db_config['port'],
    database=db_config['database'],
    user=db_config['user'],
    password=db_config['password']
)

print("\n" + "="*80)
print("VERIFYING OPC TAGS FROM DATABASE")
print("="*80)

# Step 1: Get all mapped tags from database
cur = conn.cursor()
cur.execute("""
    SELECT 
        tag_id, 
        tag_name, 
        enabled,
        plant,
        area,
        equipment
    FROM historian_meta.tag_master 
    WHERE enabled = true
    ORDER BY tag_id
""")
db_tags = cur.fetchall()
cur.close()
conn.close()

print(f"\n✓ Found {len(db_tags)} enabled tags in database")
print("\nDatabase Tags List:")
print("-" * 80)

db_tag_list = []
for tag_id, tag_name, enabled, plant, area, equipment in db_tags:
    db_tag_list.append(tag_id)
    
# Show first 10 and last 5
print("\nFirst 10 tags:")
for i, tag_id in enumerate(db_tag_list[:10], 1):
    print(f"  {i}. {tag_id}")

if len(db_tag_list) > 15:
    print(f"\n  ... ({len(db_tag_list) - 15} tags omitted) ...\n")
    print("Last 5 tags:")
    for i, tag_id in enumerate(db_tag_list[-5:], len(db_tag_list)-4):
        print(f"  {i}. {tag_id}")

# Step 2: Check what's available from OPC server via C# API
print("\n" + "="*80)
print("CHECKING C# OPC SERVER API")
print("="*80)

base_url = "http://127.0.0.1:5001"

try:
    # Check /api/historian/mapping endpoint
    print(f"\n🔍 Fetching from: {base_url}/api/historian/mapping")
    response = requests.get(f"{base_url}/api/historian/mapping", timeout=5)
    
    if response.status_code == 200:
        data = response.json()
        api_mappings = data.get('mappings', [])
        print(f"✓ API returned {len(api_mappings)} mappings")
        print(f"  Mapping version: {data.get('mapping_version', 'N/A')}")
        
        # Show sample
        if api_mappings:
            print("\n📋 Sample API mappings:")
            for i, mapping in enumerate(api_mappings[:10], 1):
                tag_id = mapping.get('tagId') or mapping.get('tag_id', 'Unknown')
                print(f"  {i}. {tag_id}")
            if len(api_mappings) > 10:
                print(f"  ... and {len(api_mappings) - 10} more")
                
            # Create a set of API tag IDs for comparison
            api_tag_ids = {mapping.get('tagId') or mapping.get('tag_id') for mapping in api_mappings if mapping.get('tagId') or mapping.get('tag_id')}
            print(f"\n✓ API has {len(api_tag_ids)} unique tag IDs")
            
            # Compare with database
            db_tag_ids_set = set(db_tag_list)
            matched = db_tag_ids_set.intersection(api_tag_ids)
            print(f"  ✓ Matched with DB: {len(matched)}/{len(db_tag_ids_set)} tags")
            
            if len(matched) < len(db_tag_ids_set):
                missing_in_api = db_tag_ids_set - api_tag_ids
                print(f"  ❌ Missing in API: {len(missing_in_api)} tags")
                for tag in list(missing_in_api)[:5]:
                    print(f"     • {tag}")
    else:
        print(f"❌ API error: {response.status_code}")
        print(f"   Response: {response.text[:200]}")
        
except Exception as e:
    print(f"❌ Failed to connect to C# API: {e}")

# Step 3: Try to get live OPC tags
print("\n" + "="*80)
print("CHECKING LIVE OPC TAGS")
print("="*80)

try:
    print(f"\n🔍 Fetching from: {base_url}/api/historian/monitor")
    response = requests.get(f"{base_url}/api/historian/monitor", timeout=5)
    
    if response.status_code == 200:
        monitor_data = response.json()
        live_tags = monitor_data.get('tags', [])
        print(f"✓ Found {len(live_tags)} tags from OPC monitor")
        
        # Show which tags are mapped
        mapped_count = sum(1 for tag in live_tags if tag.get('mapped', False))
        print(f"  Mapped tags: {mapped_count}")
        print(f"  Unmapped tags: {len(live_tags) - mapped_count}")
        
        # Check if our DB tags are in the live data
        print("\n🔎 Checking if DB tags are available in OPC server:")
        db_tag_ids = set(db_tag_list)
        live_tag_ids = {tag.get('tag_id') for tag in live_tags}
        
        found_tags = db_tag_ids.intersection(live_tag_ids)
        missing_tags = db_tag_ids - live_tag_ids
        
        print(f"  ✓ Found in OPC: {len(found_tags)}/{len(db_tag_ids)} tags")
        
        if found_tags:
            print("\n  ✓ Available tags (sample):")
            for tag_id in list(found_tags)[:10]:
                print(f"    • {tag_id}")
        
        if missing_tags:
            print(f"\n  ❌ Missing from OPC: {len(missing_tags)} tags")
            print("  Tags not found in OPC server:")
            for tag_id in list(missing_tags)[:10]:
                print(f"    • {tag_id}")
            if len(missing_tags) > 10:
                print(f"    ... and {len(missing_tags) - 10} more")
    else:
        print(f"❌ Monitor API error: {response.status_code}")
        
except Exception as e:
    print(f"❌ Failed to get live tags: {e}")

# Step 4: Summary
print("\n" + "="*80)
print("SUMMARY")
print("="*80)
print(f"Database mapped tags: {len(db_tags)}")

print("\n" + "="*80)
