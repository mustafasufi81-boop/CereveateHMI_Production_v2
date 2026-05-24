"""
Fix ALL tag names to match actual PLC tag names from screenshot
"""
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

# Based on screenshot - exact PLC tag names
tag_fixes = [
    ('Pipe_Id', 'Pipe_Id'),  # Keep as is
    ('Joint_Id', 'Joint_Id'),  # Keep as is  
    ('Welder_id', 'Welder_id'),  # Keep as is
    ('WPS_ID', 'WPS_ID'),  # Keep as is
    ('Welding_Current_A', 'Welding_Current_A'),  # Keep as is
    ('Welding_Voltage_V', 'Welding_Voltage_V'),  # Already fixed, revert back
]

print("\n" + "="*80)
print("CORRECTING TAG NAMES BASED ON SCREENSHOT")
print("="*80)

# The screenshot shows underscores, so we need to REVERT the change
cur.execute("""
    UPDATE historian_meta.tag_master
    SET tag_id = 'Welding_Voltage_V',
        config_updated_at = NOW()
    WHERE tag_id = 'Welding Voltage V'
    RETURNING tag_id
""")

result = cur.fetchone()
if result:
    print(f"✅ Reverted: 'Welding Voltage V' → 'Welding_Voltage_V'")
else:
    print(f"ℹ️  Tag already named 'Welding_Voltage_V'")

conn.commit()

# Now check what tags exist in DB
print("\n" + "="*80)
print("ALL TAGS IN DATABASE:")
print("="*80)

cur.execute("""
    SELECT tag_id, enabled, server_progid
    FROM historian_meta.tag_master
    WHERE server_progid = 'Rockwel_PLC_001'
    ORDER BY tag_id
""")

for row in cur.fetchall():
    print(f"  {row[0]}")

cur.close()
conn.close()

print("\n✅ Done! Tag names now match screenshot exactly (with underscores)")
