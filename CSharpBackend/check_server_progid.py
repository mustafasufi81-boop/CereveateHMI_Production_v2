import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

print("\n" + "="*80)
print("CHECKING server_progid FOR WELDING TAGS")
print("="*80)

cur.execute("""
    SELECT tag_id, server_progid, enabled, plc_ip_address
    FROM historian_meta.tag_master
    WHERE tag_id IN (
        'Welding_Current_A', 'Welding_Voltage_V', 'Arc', 'Power',
        'Pipe_Id', 'Joint_Id', 'Welder_id', 'WPS_ID', 'sim_step'
    )
    ORDER BY tag_id
""")

for row in cur.fetchall():
    tag_id, server_progid, enabled, ip = row
    status = "✅" if enabled else "❌"
    progid_str = server_progid if server_progid else "NULL ❌"
    ip_str = ip if ip else "NULL"
    print(f"{status} {tag_id:25s} | server_progid: {progid_str:25s} | IP: {ip_str}")

print("\n" + "="*80)
print("ALL ROCKWELL PLC TAGS (should include welding tags)")
print("="*80)

cur.execute("""
    SELECT COUNT(*), server_progid
    FROM historian_meta.tag_master
    WHERE server_progid = 'Rockwel_PLC_001' AND enabled = true
    GROUP BY server_progid
""")

result = cur.fetchone()
if result:
    count, progid = result
    print(f"✅ {progid}: {count} enabled tags")
else:
    print("❌ No tags found for Rockwel_PLC_001")

cur.close()
conn.close()
