import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

welding_tags = [
    'Welding_Current_A', 'Welding_Voltage_V', 'Arc', 'Power', 
    'Pipe_Id', 'Joint_Id', 'Welder_id', 'WPS_ID', 'sim_step'
]

print("\n" + "="*100)
print("CHECKING PLC CONFIGURATION FOR WELDING TAGS IN DATABASE")
print("="*100)

cur.execute("""
    SELECT tag_id, server_progid, plc_ip_address, plc_port, 
           plc_protocol, enabled, data_type, plc_polling_interval_ms
    FROM historian_meta.tag_master
    WHERE tag_id = ANY(%s)
    ORDER BY tag_id
""", (welding_tags,))

print("\nTag configurations in historian_meta.tag_master:")
print("-" * 100)
print(f"{'Tag ID':<25} {'Server':<20} {'IP Address':<15} {'Port':<6} {'Protocol':<15} {'Enabled':<8} {'Poll(ms)':<10}")
print("-" * 100)

found = []
for row in cur.fetchall():
    tag_id, progid, ip, port, protocol, enabled, dtype, poll_ms = row
    found.append(tag_id)
    status = "✅" if enabled else "❌"
    print(f"{tag_id:<25} {progid:<20} {ip:<15} {port:<6} {protocol:<15} {status:<8} {poll_ms or 1000:<10}")

print("\nMissing tags:")
print("-" * 100)
missing = set(welding_tags) - set(found)
for tag_id in sorted(missing):
    print(f"❌ {tag_id} - NOT IN tag_master table")

# Check if PLC is configured
print("\n" + "="*100)
print("UNIQUE PLC CONFIGURATIONS IN DATABASE")
print("="*100)
cur.execute("""
    SELECT DISTINCT server_progid, plc_ip_address, plc_port, plc_protocol,
           COUNT(*) as tag_count
    FROM historian_meta.tag_master
    WHERE enabled = true AND plc_ip_address IS NOT NULL
    GROUP BY server_progid, plc_ip_address, plc_port, plc_protocol
    ORDER BY server_progid
""")

for row in cur.fetchall():
    progid, ip, port, protocol, count = row
    print(f"PLC: {progid:<25} @ {ip}:{port} ({protocol}) - {count} enabled tags")

cur.close()
conn.close()
