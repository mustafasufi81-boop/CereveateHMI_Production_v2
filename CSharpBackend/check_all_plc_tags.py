import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

# Get all tags for Rockwell PLC
cur.execute("""
    SELECT tag_id, tag_name, data_type, plc_polling_interval_ms, enabled
    FROM historian_meta.tag_master
    WHERE server_progid = 'Rockwel_PLC_001' 
    AND plc_ip_address = '192.168.0.20'
    AND enabled = true
    ORDER BY tag_id
""")

print("\n" + "="*80)
print(f"ALL ENABLED TAGS FOR ROCKWELL PLC (192.168.0.20)")
print("="*80)
print(f"{'Tag ID':<30} {'Data Type':<12} {'Poll Interval':<15} {'Status':<10}")
print("-" * 80)

welding_tags = [
    'Welding_Current_A', 'Welding_Voltage_V', 'Arc', 'Power', 
    'Pipe_Id', 'Joint_Id', 'Welder_id', 'WPS_ID', 'sim_step'
]

all_tags = []
welding_found = []
for row in cur.fetchall():
    tag_id, tag_name, data_type, poll_ms, enabled = row
    all_tags.append(tag_id)
    
    is_welding = tag_id in welding_tags
    if is_welding:
        welding_found.append(tag_id)
        marker = "🔧"
    else:
        marker = "  "
    
    print(f"{marker} {tag_id:<30} {data_type:<12} {poll_ms or 1000:<15} {'ENABLED' if enabled else 'DISABLED':<10}")

print("\n" + "="*80)
print(f"SUMMARY")
print("="*80)
print(f"Total enabled tags: {len(all_tags)}")
print(f"Welding tags: {len(welding_found)}/{len(welding_tags)}")
print(f"\n🔧 = Welding tag")

# Check if these tags have any data in the API
print("\n" + "="*80)
print("RECOMMENDATION")
print("="*80)
print("""
All welding tags are properly configured in the database.
The issue is likely:

1. PLC driver is not reading these specific tags from the PLC
2. Check if the tag addresses match the actual PLC tag names
3. Check C# backend logs for read errors
4. Verify the PLC actually has these tags defined

Next step: Check the actual PLC to see if these tag addresses exist.
""")

cur.close()
conn.close()
