import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()

# Fix TY1101A with all required PLC columns
cur.execute("""
    UPDATE historian_meta.tag_master
    SET 
        plc_port = 44818,
        plc_path = '1,0',
        plc_protocol = 'Rockwell',
        plc_polling_interval_ms = 200,
        plc_timeout_ms = 3000,
        plc_type = 'ControlLogix',
        data_type = 'double',
        enabled = true
    WHERE tag_id = 'TY1101A' AND server_progid = 'Rockwel_PLC_001'
""")

# Disable all OTHER Rockwel_PLC_001 tags (only TY1101A is currently enabled, but be safe)
cur.execute("""
    UPDATE historian_meta.tag_master
    SET enabled = false
    WHERE server_progid = 'Rockwel_PLC_001' AND tag_id != 'TY1101A'
""")

conn.commit()

# Verify
cur.execute("""
    SELECT tag_id, plc_protocol, plc_ip_address, plc_port, plc_path, plc_polling_interval_ms, enabled
    FROM historian_meta.tag_master
    WHERE server_progid = 'Rockwel_PLC_001' AND enabled = true
""")
rows = cur.fetchall()
print(f"Enabled Rockwel_PLC_001 tags after fix ({len(rows)}):")
for r in rows:
    print(r)

conn.close()
print("Done!")
