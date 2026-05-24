import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()

# Check all enabled Rockwel_PLC_001 tags
cur.execute("""
    SELECT tag_id, server_progid, plc_protocol, plc_ip_address, plc_port, plc_path, plc_type, plc_polling_interval_ms, enabled
    FROM historian_meta.tag_master
    WHERE server_progid='Rockwel_PLC_001' AND enabled=true
""")
rows = cur.fetchall()
print(f"Enabled Rockwel_PLC_001 tags ({len(rows)}):")
for r in rows:
    print(r)

# Check columns available
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_schema='historian_meta' AND table_name='tag_master'
    AND column_name LIKE 'plc%'
    ORDER BY column_name
""")
cols = cur.fetchall()
print("\nPLC columns in tag_master:")
for c in cols:
    print(c[0])

conn.close()
