import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)

cur = conn.cursor()

print("\n" + "="*80)
print("FIXING WELDING TAG DATA TYPES IN DATABASE")
print("="*80)

# Update Arc to boolean (database uses 'boolean', not 'bool')
# Update all REAL tags to 'double' (database uses 'double', not 'REAL')
updates = [
    ("Arc", "boolean"),  # Use 'boolean' (not 'bool' or 'string')
    ("Welding_Current_A", "double"),  # Use 'double' (not 'REAL')
    ("Welding_Voltage_V", "double"),
    ("Power", "double"),
    ("Pipe_Id", "double"),
    ("Joint_Id", "double"),
    ("Welder_id", "double"),
    ("WPS_ID", "double"),
    ("sim_step", "double")
]

for tag_id, data_type in updates:
    cur.execute("""
        UPDATE historian_meta.tag_master 
        SET data_type = %s
        WHERE tag_id = %s
    """, (data_type, tag_id))
    
    print(f"✅ Updated {tag_id:25s} → data_type = {data_type}")

conn.commit()

print("\n" + "="*80)
print("VERIFYING UPDATES")
print("="*80)

cur.execute("""
    SELECT tag_id, data_type, enabled, server_progid
    FROM historian_meta.tag_master 
    WHERE tag_id IN ('Arc','Welding_Current_A','Welding_Voltage_V','Power','Pipe_Id','Joint_Id','Welder_id','WPS_ID','sim_step')
    ORDER BY tag_id
""")

for row in cur.fetchall():
    status = "✅" if row[2] else "❌"
    print(f"{status} {row[0]:25s} | Type: {row[1]:10s} | Server: {row[3]}")

cur.close()
conn.close()

print("\n" + "="*80)
print("✅ DONE! Historian ingest service will now process welding tags.")
print("Wait 5-10 seconds for next poll cycle to see database writes.")
print("="*80)
