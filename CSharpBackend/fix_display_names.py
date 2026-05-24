"""
Update tag_name column (display names) to have proper friendly names with spaces
"""
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

# Update display names - tag_id stays as is (matches PLC address)
# tag_name is what shows in UI
updates = [
    ('Welding_Current_A', 'Welding Current A'),
    ('Welding_Voltage_V', 'Welding Voltage V'),
    ('Pipe_Id', 'Pipe ID'),
    ('Joint_Id', 'Joint ID'),
    ('Welder_id', 'Welder ID'),
    ('WPS_ID', 'WPS ID'),
    ('sim_step', 'Simulation Step'),
]

print("\nUpdating tag_name (display names) to have proper spaces:")
print("="*80)

for tag_id, display_name in updates:
    cur.execute("""
        UPDATE historian_meta.tag_master
        SET tag_name = %s,
            config_updated_at = NOW()
        WHERE tag_id = %s
        RETURNING tag_id, tag_name
    """, (display_name, tag_id))
    
    result = cur.fetchone()
    if result:
        print(f"✅ {result[0]:<30} → tag_name: '{result[1]}'")
    else:
        print(f"⚠️  Tag not found: {tag_id}")

conn.commit()
cur.close()
conn.close()

print("\n✅ Done! Restart C# backend to reload configuration.")
print("   The UI will now show friendly names with spaces.")
