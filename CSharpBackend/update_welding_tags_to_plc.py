import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

welding_tags = [
    'Welding_Current_A',
    'Welding_Voltage_V',
    'Arc',
    'Power',
    'Pipe_Id',
    'Joint_Id',
    'Welder_id',
    'WPS_ID',
    'sim_step'
]

print("\n" + "="*80)
print("UPDATING WELDING TAGS TO USE Rockwel_PLC_001")
print("="*80)

for tag in welding_tags:
    try:
        cur.execute("""
            UPDATE historian_meta.tag_master 
            SET server_progid = 'Rockwel_PLC_001'
            WHERE tag_id = %s
        """, (tag,))
        
        conn.commit()
        print(f"✅ Updated: {tag:30s} → server_progid = 'Rockwel_PLC_001'")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Failed: {tag:30s} - {str(e)}")

print("\n" + "="*80)

# Verify the update
cur.execute("""
    SELECT server_progid, COUNT(*) 
    FROM historian_meta.tag_master 
    WHERE enabled = true
    GROUP BY server_progid
    ORDER BY server_progid
""")

print("TAG COUNT BY SERVER:")
print("="*80)
for row in cur.fetchall():
    progid, count = row
    print(f"{progid:40s} | {count:3d} tags")

print("\n" + "="*80)
print("✅ DONE! Restart the C# backend to load the new tags from PLC")
print("="*80)

cur.close()
conn.close()
