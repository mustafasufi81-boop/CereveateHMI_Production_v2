import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

print("\n" + "="*80)
print("CHECKING WHY ONLY 32 TAGS SHOWING")
print("="*80)

# 1. Check total enabled tags in tag_master
print("\n1. Total enabled tags in historian_meta.tag_master:")
cur.execute("SELECT COUNT(*) FROM historian_meta.tag_master WHERE enabled = true")
total = cur.fetchone()[0]
print(f"   Total: {total} tags")

# 2. Check welding tags specifically
print("\n2. Welding tags configuration:")
welding_tags = ['Welding_Current_A', 'Welding_Voltage_V', 'Arc', 'Power', 'Pipe_Id', 'Joint_Id', 'Welder_id', 'WPS_ID', 'sim_step']

cur.execute("""
    SELECT tag_id, server_progid, plc_ip_address, plc_protocol, enabled
    FROM historian_meta.tag_master
    WHERE tag_id IN %s
    ORDER BY tag_id
""", (tuple(welding_tags),))

print(f"{'Tag ID':<25} | {'Server ProgID':<30} | {'PLC IP':<15} | {'Protocol':<15} | Enabled")
print("-" * 110)

welding_found = 0
for row in cur.fetchall():
    tag_id, progid, ip, protocol, enabled = row
    progid_str = progid if progid else "❌ NULL (NOT ASSIGNED TO PLC!)"
    ip_str = ip if ip else "NULL"
    protocol_str = protocol if protocol else "NULL"
    status = "✅" if enabled else "❌"
    print(f"{tag_id:<25} | {progid_str:<30} | {ip_str:<15} | {protocol_str:<15} | {status}")
    welding_found += 1

print(f"\n   Found: {welding_found}/9 welding tags")

# 3. Check all tags grouped by server_progid
print("\n3. Tags grouped by PLC (server_progid):")
cur.execute("""
    SELECT 
        COALESCE(server_progid, '(NULL - No PLC assigned)') as plc,
        plc_ip_address,
        COUNT(*) as tag_count,
        COUNT(*) FILTER (WHERE enabled = true) as enabled_count
    FROM historian_meta.tag_master
    GROUP BY server_progid, plc_ip_address
    ORDER BY tag_count DESC
""")

print(f"\n{'PLC / Server ProgID':<40} | {'IP Address':<15} | {'Total Tags':<12} | {'Enabled Tags'}")
print("-" * 90)

for row in cur.fetchall():
    plc, ip, total_tags, enabled_tags = row
    ip_str = ip if ip else "N/A"
    print(f"{plc:<40} | {ip_str:<15} | {total_tags:<12} | {enabled_tags}")

print("\n" + "="*80)
print("DIAGNOSIS:")
print("="*80)
print("""
If welding tags show NULL for server_progid:
  ❌ Tags are NOT assigned to any PLC connection
  ❌ PlcConfigLoaderService won't load them (filters by server_progid)
  
SOLUTION:
  UPDATE historian_meta.tag_master
  SET 
    server_progid = 'Matrikon.OPC.Simulation.1',  -- OR your PLC ProgID
    plc_protocol = 'Rockwell',
    plc_ip_address = '192.168.0.20',
    plc_port = 44818
  WHERE tag_id IN ('Welding_Current_A', 'Welding_Voltage_V', 'Arc', 'Power', 
                   'Pipe_Id', 'Joint_Id', 'Welder_id', 'WPS_ID', 'sim_step');
""")
print("="*80)

cur.close()
conn.close()
