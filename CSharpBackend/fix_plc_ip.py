import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, database='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()

# Fix wrong IP for Rockwel_PLC_001
cur.execute("UPDATE historian_meta.tag_master SET plc_ip_address = '192.168.0.20' WHERE server_progid = 'Rockwel_PLC_001' AND plc_ip_address = '192.168.1.11'")
print(f'Updated {cur.rowcount} rows: 192.168.1.11 -> 192.168.0.20')
conn.commit()

# Verify
cur.execute("SELECT plc_ip_address, count(*) FROM historian_meta.tag_master WHERE server_progid='Rockwel_PLC_001' AND enabled=true GROUP BY plc_ip_address")
print('Final state:')
for r in cur.fetchall():
    print(f'  IP={r[0]}  tags={r[1]}')

conn.close()
print('Done.')
