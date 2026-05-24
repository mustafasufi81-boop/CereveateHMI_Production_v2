"""
FINAL FIX: Ensure database tag_id matches PLC tag address EXACTLY
PLC has underscores: Welding_Current_A, Pipe_Id, etc.
Database tag_id must match exactly for historian to write data
"""
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

print("\n" + "="*100)
print("FINAL CHECK: Database tag_id vs PLC tag names")
print("="*100)

# These are the EXACT PLC tag names (with underscores)
correct_mappings = {
    # If DB has spaces, fix to underscores
    'Welding Current A': 'Welding_Current_A',
    'Welding Voltage V': 'Welding_Voltage_V',
    'Pipe ID': 'Pipe_Id',
    'Joint ID': 'Joint_Id',
    'Welder ID': 'Welder_id',
    'WPS ID': 'WPS_ID',
    'Simulation Step': 'sim_step',
}

# Check current database state
cur.execute("""
    SELECT tag_id, tag_name, enabled
    FROM historian_meta.tag_master
    WHERE server_progid = 'Rockwel_PLC_001'
    AND (tag_id LIKE '%Weld%' OR tag_id LIKE '%Pipe%' OR tag_id LIKE '%Joint%' 
         OR tag_id LIKE '%WPS%' OR tag_id LIKE '%Welder%' OR tag_id LIKE '%Sim%'
         OR tag_id = 'Arc' OR tag_id = 'Power')
    ORDER BY tag_id
""")

print("\nCurrent database state:")
print(f"{'tag_id (must match PLC)':<30} {'tag_name (display)':<30} {'Status':<10}")
print("-" * 100)

needs_fix = []
for row in cur.fetchall():
    tag_id, tag_name, enabled = row
    status = "✅" if enabled else "❌"
    print(f"{tag_id:<30} {tag_name:<30} {status:<10}")
    
    # Check if tag_id needs to be fixed (has spaces instead of underscores)
    if tag_id in correct_mappings:
        needs_fix.append((tag_id, correct_mappings[tag_id], tag_name))

if needs_fix:
    print("\n" + "="*100)
    print("FIXING TAG IDs TO MATCH PLC (changing spaces to underscores):")
    print("="*100)
    
    for old_id, new_id, display_name in needs_fix:
        cur.execute("""
            UPDATE historian_meta.tag_master
            SET tag_id = %s,
                tag_name = %s,
                config_updated_at = NOW()
            WHERE tag_id = %s
            RETURNING tag_id, tag_name
        """, (new_id, display_name, old_id))
        
        result = cur.fetchone()
        if result:
            print(f"✅ Fixed: '{old_id}' → '{result[0]}' (display: '{result[1]}')")
        
    conn.commit()
    print(f"\n✅ Fixed {len(needs_fix)} tags")
else:
    print("\n✅ All tag_ids already correct (with underscores)")

cur.close()
conn.close()

print("\n" + "="*100)
print("SUMMARY:")
print("="*100)
print("""
Database tag_id now matches PLC tag address exactly (with underscores).
Historian will now be able to match tags and write to database.

RESTART C# BACKEND NOW to reload configuration!
""")
