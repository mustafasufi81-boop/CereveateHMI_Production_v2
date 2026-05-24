"""
Fix tag_id in database to match actual PLC tag names (with spaces)
"""
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

# Mapping: OLD tag_id (in DB) -> NEW tag_id (actual PLC name)
tag_name_fixes = {
    'Welding_Current_A': 'Welding Current A',
    'Welding_Voltage_V': 'Welding Voltage V',
    'Pipe_Id': 'Pipe ID',
    'Joint_Id': 'Joint ID',
    'Welder_id': 'Welder ID',
    'WPS_ID': 'WPS ID',
    'sim_step': 'Simulation Step'
}

print("\n" + "="*100)
print("FIXING TAG NAMES TO MATCH ACTUAL PLC TAG NAMES")
print("="*100)

print("\nTag name corrections:")
print("-" * 100)
print(f"{'OLD (Database)':<30} → {'NEW (Actual PLC)':<30}")
print("-" * 100)

for old_name, new_name in tag_name_fixes.items():
    print(f"{old_name:<30} → {new_name:<30}")

print("\n" + "="*100)
response = input("Apply these changes? (y/n): ")

if response.lower() != 'y':
    print("❌ Cancelled")
    cur.close()
    conn.close()
    exit()

print("\nApplying changes...")
print("-" * 100)

success_count = 0
for old_tag_id, new_tag_id in tag_name_fixes.items():
    try:
        # Update tag_id in tag_master
        cur.execute("""
            UPDATE historian_meta.tag_master
            SET tag_id = %s,
                config_updated_at = NOW()
            WHERE tag_id = %s
            RETURNING tag_id, tag_name
        """, (new_tag_id, old_tag_id))
        
        result = cur.fetchone()
        if result:
            print(f"✅ Updated: {old_tag_id:<30} → {new_tag_id:<30}")
            success_count += 1
        else:
            print(f"⚠️  Not found: {old_tag_id}")
            
    except Exception as e:
        print(f"❌ Error updating {old_tag_id}: {e}")

conn.commit()

print("\n" + "="*100)
print(f"✅ Successfully updated {success_count}/{len(tag_name_fixes)} tag names")
print("="*100)

# Now update historian_timeseries table if it has the old tag_ids
print("\n🔄 Checking historian_timeseries table...")

for old_tag_id, new_tag_id in tag_name_fixes.items():
    cur.execute("""
        SELECT COUNT(*) 
        FROM historian_raw.historian_timeseries 
        WHERE tag_id = %s
    """, (old_tag_id,))
    
    old_count = cur.fetchone()[0]
    if old_count > 0:
        print(f"Found {old_count} records with old tag_id: {old_tag_id}")
        update_hist = input(f"  Update these to '{new_tag_id}'? (y/n): ")
        
        if update_hist.lower() == 'y':
            cur.execute("""
                UPDATE historian_raw.historian_timeseries
                SET tag_id = %s
                WHERE tag_id = %s
            """, (new_tag_id, old_tag_id))
            print(f"  ✅ Updated {cur.rowcount} records")

conn.commit()
cur.close()
conn.close()

print("\n" + "="*100)
print("NEXT STEPS:")
print("="*100)
print("""
1. Restart C# backend to reload configuration:
   Get-Process | Where-Object {$_.ProcessName -like "*OpcDa*"} | Stop-Process -Force
   dotnet run --project OpcDaWebService.csproj

2. Verify tags are now in API:
   python check_tag_pool.py

3. Check database writes:
   python check_welding_db_writes.py

The historian will now match PLC tags correctly and write to database!
""")
