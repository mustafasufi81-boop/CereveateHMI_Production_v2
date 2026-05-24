import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)

cur = conn.cursor()

print("\n" + "="*80)
print("COMPLETE DIAGNOSIS: WHY WELDING TAGS NOT WRITING TO DATABASE")
print("="*80)

# 1. Check ALL PLC tags that ARE writing
print("\n1. PLC tags that ARE writing to database (last 2 minutes):")
cur.execute("""
    SELECT tag_id, COUNT(*), MAX(opc_timestamp) 
    FROM historian_raw.historian_timeseries 
    WHERE opc_timestamp > NOW() - INTERVAL '2 minutes'
      AND tag_id NOT LIKE 'Random%'
    GROUP BY tag_id 
    ORDER BY COUNT(*) DESC
""")

plc_writing = cur.fetchall()
if plc_writing:
    for row in plc_writing:
        print(f"   ✅ {row[0]:30s} | Records: {row[1]:4d} | Last: {row[2]}")
else:
    print("   ❌ NO PLC TAGS WRITING")

# 2. Check welding tags configuration in tag_master
print("\n2. Welding tags configuration in tag_master:")
welding_tags = ['Welding_Current_A', 'Welding_Voltage_V', 'Arc', 'Power', 'Pipe_Id', 'Joint_Id', 'Welder_id', 'WPS_ID', 'sim_step']

cur.execute("""
    SELECT tag_id, enabled, server_progid, plc_ip_address, data_type,
           deadband_value, db_logging_interval_ms
    FROM historian_meta.tag_master 
    WHERE tag_id = ANY(%s)
    ORDER BY tag_id
""", (welding_tags,))

for row in cur.fetchall():
    tag_id, enabled, progid, ip, dtype, deadband, interval = row
    status = "✅" if enabled else "❌"
    print(f"   {status} {tag_id:25s} | {progid:20s} | IP:{ip:15s} | Type:{dtype:10s} | Deadband:{deadband} | Interval:{interval}ms")

# 3. Check if historian is reading from OPC or PLC source
print("\n3. Checking source field in recent data:")
cur.execute("""
    SELECT DISTINCT server_progid
    FROM historian_raw.historian_timeseries 
    WHERE opc_timestamp > NOW() - INTERVAL '1 minute'
""")

sources = cur.fetchall()
print(f"   Data sources writing to DB: {[s[0] for s in sources]}")

# 4. Check if there's a mapping table issue
print("\n4. Checking if welding tags exist in any other mapping tables:")
cur.execute("""
    SELECT schemaname, tablename 
    FROM pg_tables 
    WHERE schemaname LIKE '%historian%' OR schemaname LIKE '%plc%'
    ORDER BY schemaname, tablename
""")

tables = cur.fetchall()
print(f"   Found {len(tables)} historian/plc tables:")
for schema, table in tables[:10]:
    print(f"      - {schema}.{table}")

cur.close()
conn.close()

print("\n" + "="*80)
print("KEY FINDING:")
print("="*80)
print("""
If section 1 shows ONLY OPC tags (Random.*, Bucket.*, etc.) writing:
→ Historian is ONLY processing OPC tags, NOT PLC tags

If section 1 shows some PLC tags (Pump_RPM, Motor_Current, etc.):
→ Historian CAN process PLC tags, but welding tags have a different issue

The welding tags need to be:
1. In appsettings.json PLC configuration (so PlcGateway reads them)
2. In tag_master with server_progid='Rockwel_PLC_001' (for historian mapping)
3. Backend restarted to load new configuration
""")
print("="*80)
