import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

# Insert the 2 missing tags
tags = [
    {
        "tag_id": "Welding_Current_A",
        "tag_name": "Welding Current A",
        "data_type": "double",
        "eng_unit": "A"
    },
    {
        "tag_id": "Welding_Voltage_V",
        "tag_name": "Welding Voltage V",
        "data_type": "double",
        "eng_unit": "V"
    }
]

print("\n" + "="*60)
print("INSERTING 2 MISSING WELDING TAGS")
print("="*60)

for tag in tags:
    try:
        cur.execute("""
            INSERT INTO historian_meta.tag_master 
            (tag_id, tag_name, plant, area, equipment, data_type, eng_unit, 
             enabled, deadband_value, db_logging_interval_ms, created_by)
            VALUES 
            (%s, %s, 'Plant1', 'Production', 'Welding Station', %s, %s, 
             true, 0, 1000, 'admin')
        """, (tag['tag_id'], tag['tag_name'], tag['data_type'], tag['eng_unit']))
        
        conn.commit()
        print(f"✅ Inserted: {tag['tag_id']}")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Failed: {tag['tag_id']} - {str(e)}")

print("\n" + "="*60)

# Verify total count
cur.execute("SELECT COUNT(*) FROM historian_meta.tag_master WHERE enabled = true")
total = cur.fetchone()[0]
print(f"Total enabled tags: {total}")
print("="*60)

cur.close()
conn.close()
