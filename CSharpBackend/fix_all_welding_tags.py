"""
Fix ALL welding tag names based on earlier compare_tag_names.py output
PLC has spaces, DB has underscores - need to update DB to match PLC
"""
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

# From compare_tag_names.py output - these are the actual PLC names (WITH SPACES)
updates = [
    ('Welding_Current_A', 'Welding Current A'),
    ('Welding_Voltage_V', 'Welding Voltage V'),  
    ('Pipe_Id', 'Pipe ID'),
    ('Joint_Id', 'Joint ID'),
    ('Welder_id', 'Welder ID'),
    ('WPS_ID', 'WPS ID'),
    ('sim_step', 'Simulation Step'),
]

print("\nUpdating tag names to match PLC (with spaces):\n")

for old_name, new_name in updates:
    cur.execute("""
        UPDATE historian_meta.tag_master
        SET tag_id = %s,
            config_updated_at = NOW()
        WHERE tag_id = %s
        RETURNING tag_id
    """, (new_name, old_name))
    
    if cur.fetchone():
        print(f"✅ {old_name:30} → {new_name}")

conn.commit()
cur.close()
conn.close()

print("\n✅ Done! Restart C# backend now.")
