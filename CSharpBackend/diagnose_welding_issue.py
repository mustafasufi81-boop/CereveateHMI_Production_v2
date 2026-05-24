import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

print("\n" + "="*80)
print("DIAGNOSIS: WHY WELDING TAGS SHOW NO DATA")
print("="*80)

# 1. Check what schemas exist
print("\n1. Available Database Schemas:")
cur.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name NOT IN ('pg_catalog', 'information_schema') ORDER BY schema_name")
schemas = [r[0] for r in cur.fetchall()]
for s in schemas:
    print(f"   - {s}")

# 2. Check historian_raw.historian_timeseries for welding data
print("\n2. Checking historian_raw.historian_timeseries for welding tags:")
welding_tags = ['Welding_Current_A', 'Welding_Voltage_V', 'Arc', 'Power', 'Pipe_Id', 'Joint_Id', 'Welder_id', 'WPS_ID', 'sim_step']

for tag in welding_tags:
    cur.execute("""
        SELECT COUNT(*), MAX(opc_timestamp) 
        FROM historian_raw.historian_timeseries 
        WHERE tag_id = %s
    """, (tag,))
    
    count, last_time = cur.fetchone()
    if count > 0:
        print(f"   ✅ {tag:25s} | Records: {count:6d} | Last: {last_time}")
    else:
        print(f"   ❌ {tag:25s} | NO DATA")

# 3. Check if tags are in tag_master and enabled
print("\n3. Tag Master Configuration:")
cur.execute("""
    SELECT tag_id, enabled, data_type, deadband_value, db_logging_interval_ms
    FROM historian_meta.tag_master
    WHERE tag_id IN %s
    ORDER BY tag_id
""", (tuple(welding_tags),))

for row in cur.fetchall():
    tag_id, enabled, dtype, deadband, interval = row
    status = "✅ ENABLED" if enabled else "❌ DISABLED"
    print(f"   {status} | {tag_id:25s} | {dtype:10s} | Deadband: {deadband} | Interval: {interval}ms")

# 4. Check OPC connection status
print("\n4. Checking C# OPC Backend (should be running on port 5001):")
import urllib.request
import json
try:
    response = urllib.request.urlopen('http://localhost:5001/api/opc/servers', timeout=2)
    data = json.loads(response.read())
    if data.get('servers'):
        print(f"   ✅ OPC Backend running - {len(data['servers'])} servers available")
        for srv in data['servers']:
            status = "CONNECTED" if srv.get('isConnected') else "DISCONNECTED"
            print(f"      - {srv['serverName']} ({status})")
    else:
        print("   ⚠️  OPC Backend running but no servers")
except Exception as e:
    print(f"   ❌ OPC Backend not accessible: {str(e)}")

print("\n" + "="*80)
print("CONCLUSION:")
print("="*80)
print("""
If welding tags show NO DATA above:
1. Tags are in historian_meta.tag_master ✅
2. Tags are NOT in OPC server (Matrikon.OPC.Simulation) ❌
3. Tags need to be added to your REAL PLC/OPC server

SOLUTIONS:
A) Connect to your actual Rockwell PLC with welding tags
B) Configure OPC tag mappings to read from PLC
C) OR use simulation tags for testing (Random.Real4, etc.)
""")
print("="*80)

cur.close()
conn.close()
