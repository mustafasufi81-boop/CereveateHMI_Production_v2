"""
Insert approved tags into historian_meta.tag_master
"""
import psycopg2

# Connect to database
conn = psycopg2.connect(
    host='localhost',
    port=5432,
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)

print("=" * 80)
print("INSERTING 9 NEW TAGS INTO historian_meta.tag_master")
print("=" * 80)

# New tags to insert
new_tags = [
    {"tag_id": "Arc", "tag_name": "Arc", "data_type": "string", "eng_unit": ""},
    {"tag_id": "Power", "tag_name": "Power", "data_type": "double", "eng_unit": "kW"},
    {"tag_id": "Pipe_Id", "tag_name": "Pipe ID", "data_type": "double", "eng_unit": ""},
    {"tag_id": "Joint_Id", "tag_name": "Joint ID", "data_type": "double", "eng_unit": ""},
    {"tag_id": "Welder_id", "tag_name": "Welder ID", "data_type": "double", "eng_unit": ""},
    {"tag_id": "WPS_ID", "tag_name": "WPS ID", "data_type": "double", "eng_unit": ""},
    {"tag_id": "sim_step", "tag_name": "Simulation Step", "data_type": "double", "eng_unit": ""}
]

cur = conn.cursor()
inserted = 0
failed = 0

for tag in new_tags:
    try:
        cur.execute("""
            INSERT INTO historian_meta.tag_master 
            (tag_id, tag_name, plant, area, equipment, data_type, eng_unit, enabled, deadband_value, db_logging_interval_ms, created_by)
            VALUES 
            (%s, %s, 'Plant1', 'Production', 'Welding Station', %s, %s, true, 0, 1000, 'admin')
        """, (tag['tag_id'], tag['tag_name'], tag['data_type'], tag['eng_unit']))
        
        conn.commit()  # Commit each tag individually
        print(f"✅ Inserted: {tag['tag_id']:30s} | {tag['data_type']:10s} | {tag['tag_name']}")
        inserted += 1
        
    except Exception as e:
        conn.rollback()  # Rollback failed transaction
        print(f"❌ Failed: {tag['tag_id']:30s} | Error: {str(e)[:100]}")
        failed += 1

# Commit the transaction
conn.commit()

print("\n" + "=" * 80)
print("INSERTION COMPLETE")
print("=" * 80)
print(f"Successfully inserted: {inserted}")
print(f"Failed: {failed}")
print(f"Total: {len(new_tags)}")

# Verify insertion
cur.execute("SELECT COUNT(*) FROM historian_meta.tag_master WHERE enabled = true")
total_enabled = cur.fetchone()[0]
print(f"\nTotal enabled tags in database: {total_enabled}")

conn.close()

print("\n✅ DONE! These tags will now appear in the realtime trends page.")
