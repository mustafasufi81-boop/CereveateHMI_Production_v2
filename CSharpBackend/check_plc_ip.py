import psycopg2
import psycopg2.extras

conn = psycopg2.connect(host='localhost', port=5432, database='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# Check PLC-related columns in tag_master for Rockwel_PLC_001
cur.execute("""
    SELECT DISTINCT server_progid, plc_protocol, plc_ip_address, plc_port,
           plc_type, plc_path, plc_timeout_ms, plc_polling_interval_ms
    FROM historian_meta.tag_master
    WHERE server_progid IS NOT NULL AND enabled = true
    AND plc_ip_address IS NOT NULL
    ORDER BY server_progid
""")
print('=== PLCs with plc_ip_address SET (what C# sees) ===')
rows = cur.fetchall()
if rows:
    for r in rows:
        print(dict(r))
else:
    print('  NO ROWS — plc_ip_address is NULL for all tags!')

# Also check what Rockwel_PLC_001 has
cur.execute("""
    SELECT server_progid, plc_ip_address, plc_protocol, plc_port,
           count(*) as tag_count
    FROM historian_meta.tag_master
    WHERE server_progid = 'Rockwel_PLC_001' AND enabled = true
    GROUP BY server_progid, plc_ip_address, plc_protocol, plc_port
""")
print('\n=== Rockwel_PLC_001 tag_master details ===')
for r in cur.fetchall():
    print(dict(r))

# Check appsettings PlcGateway section
print('\n=== Checking appsettings.json for PlcGateway:Connections ===')
conn.close()
