"""
Script to update plc_slot to 0 for welding tags and other Rockwell PLC tags
This fixes the "Path destination unknown" error by setting correct slot number
"""

import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

# Tags to update (from your list + sim_step)
welding_tags = [
    'Blastfurnace_Tuyer1_Pressure',
    'Power',
    'Pipe_Id',
    'Joint_Id',
    'Welder_id',
    'WPS_ID',
    'Arc',
    'Welding_Current_A',
    'Welding_Voltage_V',
    'sim_step'  # Also included based on earlier checks
]

print("\n" + "="*80)
print("UPDATING PLC SLOT FOR WELDING TAGS")
print("="*80)

# First, show current configuration
print("\nCurrent configuration:")
print("-" * 80)
cur.execute("""
    SELECT tag_id, plc_slot, plc_path, plc_ip_address, server_progid
    FROM historian_meta.tag_master
    WHERE tag_id = ANY(%s)
    ORDER BY tag_id
""", (welding_tags,))

print(f"{'Tag ID':<30} {'Slot':<8} {'Path':<10} {'IP Address':<15} {'Server':<20}")
print("-" * 80)
for row in cur.fetchall():
    tag_id, slot, path, ip, server = row
    print(f"{tag_id:<30} {str(slot):<8} {path:<10} {ip:<15} {server:<20}")

# Update plc_slot to 0 for all these tags
print("\n" + "="*80)
print("UPDATING plc_slot to 0...")
print("="*80)

cur.execute("""
    UPDATE historian_meta.tag_master
    SET plc_slot = 0,
        config_updated_at = NOW()
    WHERE tag_id = ANY(%s)
    RETURNING tag_id, plc_slot, plc_path
""", (welding_tags,))

updated_rows = cur.fetchall()
conn.commit()

print(f"\n✅ Updated {len(updated_rows)} tags")
print("\nUpdated configuration:")
print("-" * 80)
print(f"{'Tag ID':<30} {'Slot':<8} {'Path':<10}")
print("-" * 80)
for tag_id, slot, path in updated_rows:
    print(f"{tag_id:<30} {slot:<8} {path:<10}")

# Also update ALL Rockwell PLC tags to slot 0 for consistency
print("\n" + "="*80)
print("CHECKING OTHER ROCKWELL PLC TAGS")
print("="*80)

cur.execute("""
    SELECT COUNT(*)
    FROM historian_meta.tag_master
    WHERE server_progid = 'Rockwel_PLC_001'
    AND plc_ip_address = '192.168.0.20'
    AND (plc_slot IS NULL OR plc_slot != 0)
    AND enabled = true
""")

other_count = cur.fetchone()[0]

if other_count > 0:
    print(f"\nFound {other_count} other Rockwell PLC tags with incorrect slot")
    response = input("Update ALL Rockwell PLC tags to slot 0? (y/n): ")
    
    if response.lower() == 'y':
        cur.execute("""
            UPDATE historian_meta.tag_master
            SET plc_slot = 0,
                config_updated_at = NOW()
            WHERE server_progid = 'Rockwel_PLC_001'
            AND plc_ip_address = '192.168.0.20'
            AND (plc_slot IS NULL OR plc_slot != 0)
            AND enabled = true
            RETURNING tag_id
        """)
        
        all_updated = cur.fetchall()
        conn.commit()
        print(f"✅ Updated {len(all_updated)} additional tags to slot 0")
    else:
        print("Skipped updating other tags")
else:
    print("✅ All other Rockwell PLC tags already have slot 0")

cur.close()
conn.close()

print("\n" + "="*80)
print("NEXT STEPS:")
print("="*80)
print("""
1. Restart the C# backend to reload configuration:
   Get-Process | Where-Object {$_.ProcessName -like "*OpcDa*" -or $_.ProcessName -like "*PlcGateway*"} | Stop-Process -Force
   dotnet run --project OpcDaWebService.csproj

2. Check if welding tags are now being read:
   python check_tag_pool.py

3. Verify database writes:
   python check_welding_db_writes.py

The PLC slot 0 should match the actual slot number of the ControlLogix processor.
If tags still don't work, verify the slot number in RSLinx or Studio 5000.
""")
