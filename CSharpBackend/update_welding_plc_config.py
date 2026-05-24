import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

print("\n" + "="*80)
print("UPDATING WELDING TAGS WITH PLC CONNECTION DETAILS")
print("="*80)

welding_tags = [
    'Welding_Current_A', 'Welding_Voltage_V', 'Arc', 'Power',
    'Pipe_Id', 'Joint_Id', 'Welder_id', 'WPS_ID', 'sim_step'
]

cur.execute("""
    UPDATE historian_meta.tag_master
    SET 
        plc_ip_address = '192.168.0.20',
        plc_port = 44818,
        plc_protocol = 'Rockwell',
        plc_type = 'ControlLogix',
        plc_path = '1,0',
        plc_timeout_ms = 3000,
        plc_polling_interval_ms = 1000,
        use_connected_messaging = true
    WHERE tag_id IN %s
""", (tuple(welding_tags),))

affected = cur.rowcount
conn.commit()

print(f"✅ Updated {affected} welding tags")
print("   PLC IP: 192.168.0.20:44818")
print("   Protocol: Rockwell ControlLogix")
print("   Path: 1,0")
print("   Polling: 1000ms")

print("\n" + "="*80)
print("VERIFICATION - All Rockwell PLC tags with IP address:")
print("="*80)

cur.execute("""
    SELECT COUNT(*)
    FROM historian_meta.tag_master
    WHERE server_progid = 'Rockwel_PLC_001' 
    AND plc_ip_address IS NOT NULL 
    AND enabled = true
""")

count = cur.fetchone()[0]
print(f"✅ {count} enabled tags ready for PLC Gateway")

cur.close()
conn.close()
