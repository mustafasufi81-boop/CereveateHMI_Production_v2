import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

print("\n" + "="*80)
print("1. PLC CONNECTIONS STATUS")
print("="*80)

cur.execute("""
    SELECT connection_name, protocol, ip_address, is_connected, last_connected 
    FROM plc_meta.plc_connections 
    ORDER BY connection_name
""")

connections = cur.fetchall()
if connections:
    for row in connections:
        conn_name, protocol, ip, connected, last_conn = row
        status = "✅ CONNECTED" if connected else "❌ DISCONNECTED"
        print(f"{status} | {conn_name:20s} | {protocol:12s} | {ip:15s} | Last: {last_conn}")
else:
    print("❌ No PLC connections configured")

print("\n" + "="*80)
print("2. CHECKING WELDING TAGS IN plc_meta.plc_tags")
print("="*80)

welding_tags = [
    'Welding_Current_A',
    'Welding_Voltage_V',
    'Arc',
    'Power',
    'Pipe_Id',
    'Joint_Id',
    'Welder_id',
    'WPS_ID',
    'sim_step'
]

for tag in welding_tags:
    cur.execute("""
        SELECT connection_name, tag_address, data_type, enabled
        FROM plc_meta.plc_tags
        WHERE tag_name = %s
    """, (tag,))
    
    result = cur.fetchone()
    if result:
        conn_name, address, dtype, enabled = result
        status = "✅" if enabled else "❌"
        print(f"{status} {tag:25s} | Conn: {conn_name:15s} | Addr: {address:20s} | Type: {dtype}")
    else:
        print(f"❌ {tag:25s} | NOT CONFIGURED IN PLC TAGS")

print("\n" + "="*80)
print("3. RECENT PLC DATA (plc_raw.plc_timeseries)")
print("="*80)

cur.execute("""
    SELECT DISTINCT tag_name 
    FROM plc_raw.plc_timeseries 
    WHERE timestamp > NOW() - INTERVAL '5 minutes'
    ORDER BY tag_name
    LIMIT 20
""")

recent_tags = cur.fetchall()
if recent_tags:
    print(f"Found {len(recent_tags)} tags with recent data:")
    for row in recent_tags:
        print(f"  - {row[0]}")
else:
    print("❌ No recent PLC data in last 5 minutes")

cur.close()
conn.close()
