"""
Read current tag_master and prepare new tags for insertion
"""
import psycopg2
from psycopg2.extras import RealDictCursor

# Connect to database
conn = psycopg2.connect(
    host='localhost',
    port=5432,
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)

print("=" * 80)
print("STEP 1: Reading current tag_master table")
print("=" * 80)

cur = conn.cursor(cursor_factory=RealDictCursor)
cur.execute("""
    SELECT tag_id, tag_name, data_type, enabled 
    FROM historian_meta.tag_master 
    ORDER BY tag_id
""")

existing_tags = cur.fetchall()
print(f"\nCurrent tags in database: {len(existing_tags)}")
print("\nFirst 10 existing tags:")
for i, tag in enumerate(existing_tags[:10], 1):
    print(f"  {i:2d}. {tag['tag_id']:40s} | {tag['data_type']:10s} | Enabled: {tag['enabled']}")

# Extract existing tag IDs
existing_tag_ids = {tag['tag_id'] for tag in existing_tags}

print("\n" + "=" * 80)
print("STEP 2: Preparing NEW tags from your image")
print("=" * 80)

# New tags from the image you showed
new_tags = [
    {"tag_id": "Welding_Current_A", "tag_name": "Welding Current A", "data_type": "double", "eng_unit": "A"},
    {"tag_id": "Welding_Voltage_V", "tag_name": "Welding Voltage V", "data_type": "double", "eng_unit": "V"},
    {"tag_id": "Arc", "tag_name": "Arc", "data_type": "bool", "eng_unit": ""},
    {"tag_id": "Power", "tag_name": "Power", "data_type": "double", "eng_unit": "kW"},
    {"tag_id": "Pipe_Id", "tag_name": "Pipe ID", "data_type": "double", "eng_unit": ""},
    {"tag_id": "Joint_Id", "tag_name": "Joint ID", "data_type": "double", "eng_unit": ""},
    {"tag_id": "Welder_id", "tag_name": "Welder ID", "data_type": "double", "eng_unit": ""},
    {"tag_id": "WPS_ID", "tag_name": "WPS ID", "data_type": "double", "eng_unit": ""},
    {"tag_id": "sim_step", "tag_name": "Simulation Step", "data_type": "double", "eng_unit": ""}
]

# Check which tags are new
tags_to_insert = []
for tag in new_tags:
    if tag['tag_id'] not in existing_tag_ids:
        tags_to_insert.append(tag)
        print(f"✅ NEW: {tag['tag_id']:30s} | {tag['data_type']:10s} | {tag['tag_name']}")
    else:
        print(f"⚠️  EXISTS: {tag['tag_id']:30s} (already in database)")

print("\n" + "=" * 80)
print("STEP 3: Summary")
print("=" * 80)
print(f"Total new tags to insert: {len(tags_to_insert)}")
print(f"Tags already exist: {len(new_tags) - len(tags_to_insert)}")

if tags_to_insert:
    print("\n" + "=" * 80)
    print("PREPARED SQL INSERT STATEMENTS:")
    print("=" * 80)
    
    for tag in tags_to_insert:
        sql = f"""INSERT INTO historian_meta.tag_master 
    (tag_id, tag_name, data_type, eng_unit, enabled, deadband_value, db_logging_interval_ms, created_by)
VALUES 
    ('{tag['tag_id']}', '{tag['tag_name']}', '{tag['data_type']}', '{tag['eng_unit']}', true, 0, 1000, 'admin');"""
        print(sql)
        print()
    
    print("=" * 80)
    print("⚠️  APPROVAL REQUIRED")
    print("=" * 80)
    print(f"Ready to insert {len(tags_to_insert)} new tags into historian_meta.tag_master")
    print("\nSettings:")
    print("  - enabled = true")
    print("  - deadband_value = 0 (log all changes)")
    print("  - db_logging_interval_ms = 1000 (1 second)")
    print("  - created_by = 'admin'")
    print("\n⚠️  PLEASE REVIEW AND APPROVE BEFORE EXECUTION")
else:
    print("\n✅ All tags already exist in database. No action needed.")

conn.close()
