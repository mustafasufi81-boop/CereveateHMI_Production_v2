"""
Simple check: What welding tag names are ACTUALLY in the database RIGHT NOW?
"""
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

cur.execute("""
    SELECT tag_id, enabled
    FROM historian_meta.tag_master
    WHERE tag_id IN (
        'Welding_Current_A', 'Welding_Voltage_V', 'Pipe_Id', 'Joint_Id', 
        'Welder_id', 'WPS_ID', 'sim_step', 'Arc', 'Power',
        'Welding Current A', 'Welding Voltage V', 'Pipe ID', 'Joint ID',
        'Welder ID', 'WPS ID', 'Simulation Step'
    )
    ORDER BY tag_id
""")

print("\nCURRENT TAG NAMES IN DATABASE:")
print("="*60)
for row in cur.fetchall():
    tag_id, enabled = row
    status = "✅" if enabled else "❌"
    print(f"{status} {tag_id}")

cur.close()
conn.close()
