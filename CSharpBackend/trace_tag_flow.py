import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

print("\n" + "="*80)
print("COMPLETE TAG FLOW TRACE - FINDING WHERE 9 WELDING TAGS ARE LOST")
print("="*80)

# Step 1: Database query that PlcConfigLoaderService.cs uses
print("\n1. DATABASE QUERY (PlcConfigLoaderService.cs line 248):")
print("-" * 80)

query = """
    SELECT tag_id, tag_name, data_type, eng_unit, enabled, 
           deadband_value, db_logging_interval_ms, 
           plc_ip_address, plc_port, plc_slot, plc_path
    FROM historian_meta.tag_master
    WHERE server_progid = %s
      AND plc_ip_address IS NOT NULL
      AND enabled = true
    ORDER BY tag_id
"""

cur.execute(query, ('Rockwel_PLC_001',))
rows = cur.fetchall()

print(f"Query: WHERE server_progid = 'Rockwel_PLC_001' AND plc_ip_address IS NOT NULL AND enabled = true")
print(f"Result: {len(rows)} tags")
print()

welding_tag_ids = ['Welding_Current_A', 'Welding_Voltage_V', 'Arc', 'Power', 
                   'Pipe_Id', 'Joint_Id', 'Welder_id', 'WPS_ID', 'sim_step']

welding_found = []
for row in rows:
    tag_id = row[0]
    if tag_id in welding_tag_ids:
        welding_found.append(tag_id)
        print(f"   ✅ {tag_id:25s} | IP: {row[7]:15s} | Port: {row[8]}")

missing = set(welding_tag_ids) - set(welding_found)
if missing:
    print(f"\n   ❌ MISSING FROM QUERY RESULTS: {', '.join(missing)}")

# Step 2: Check individual welding tags
print("\n2. INDIVIDUAL WELDING TAG CHECK:")
print("-" * 80)

for tag_id in welding_tag_ids:
    cur.execute("""
        SELECT server_progid, plc_ip_address, plc_port, enabled
        FROM historian_meta.tag_master
        WHERE tag_id = %s
    """, (tag_id,))
    
    result = cur.fetchone()
    if result:
        progid, ip, port, enabled = result
        issues = []
        
        if progid != 'Rockwel_PLC_001':
            issues.append(f"progid={progid}")
        if ip is None:
            issues.append("ip=NULL")
        if not enabled:
            issues.append("enabled=false")
        
        if issues:
            print(f"   ❌ {tag_id:25s} | ISSUES: {', '.join(issues)}")
        else:
            print(f"   ✅ {tag_id:25s} | OK")
    else:
        print(f"   ❌ {tag_id:25s} | NOT IN DATABASE")

# Step 3: Check PlcConnection record
print("\n3. PLC CONNECTION RECORD CHECK:")
print("-" * 80)

cur.execute("""
    SELECT plc_id, plc_name, protocol, ip_address, port, 
           slot, connection_path, enabled, is_connected
    FROM historian_meta.plc_connections
    WHERE plc_id = %s
""", ('Rockwel_PLC_001',))

plc_conn = cur.fetchone()
if plc_conn:
    plc_id, name, protocol, ip, port, slot, path, enabled, connected = plc_conn
    print(f"   PLC ID: {plc_id}")
    print(f"   Name: {name}")
    print(f"   Protocol: {protocol}")
    print(f"   IP: {ip}:{port}")
    print(f"   Slot: {slot}")
    print(f"   Path: {path}")
    print(f"   Enabled: {enabled}")
    print(f"   Connected: {connected}")
    
    if not enabled:
        print("\n   ⚠️  WARNING: PLC connection is DISABLED!")
else:
    print("   ❌ PLC connection record NOT FOUND!")

# Step 4: Summary
print("\n" + "="*80)
print("DIAGNOSIS SUMMARY")
print("="*80)

print(f"\n✓ Database has {len(rows)} tags for Rockwel_PLC_001")
print(f"✓ Welding tags found: {len(welding_found)}/9")

if len(welding_found) < 9:
    print(f"\n❌ PROBLEM: Only {len(welding_found)}/9 welding tags pass the query filter")
    print("\nTO FIX:")
    print("1. All welding tags must have server_progid = 'Rockwel_PLC_001'")
    print("2. All welding tags must have plc_ip_address IS NOT NULL")
    print("3. All welding tags must have enabled = true")
else:
    print("\n✅ All 9 welding tags should load into PlcConfigLoaderService")
    print("\nNext check: Verify tags appear in UI after service restart")

print("="*80)

cur.close()
conn.close()
