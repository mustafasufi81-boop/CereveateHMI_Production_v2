import psycopg2

c = psycopg2.connect(host='localhost', database='Automation_DB',
                     user='cereveate', password='cereveate@222')
cur = c.cursor()

cur.execute("""
    SELECT tag_id, tag_name, data_type, server_progid,
           plc_ip_address, plc_port, plc_slot, plc_protocol, plc_type
    FROM historian_meta.tag_master
    WHERE tag_name = 'CV1101B_AUTO'
""")
print("=== CV1101B_AUTO (PLC_002 tag) ===")
for r in cur.fetchall():
    print(f"  tag_id      = {r[0]}")
    print(f"  tag_name    = {r[1]}")
    print(f"  data_type   = {r[2]}")
    print(f"  progid      = {r[3]}")
    print(f"  plc_ip      = {r[4]}")
    print(f"  plc_port    = {r[5]}")
    print(f"  plc_slot    = {r[6]}")
    print(f"  plc_protocol= {r[7]}")
    print(f"  plc_type    = {r[8]}")

cur.execute("""
    SELECT server_progid, plc_ip_address, plc_slot, COUNT(*)
    FROM historian_meta.tag_master
    WHERE server_progid ILIKE 'Rockwel%%'
    GROUP BY server_progid, plc_ip_address, plc_slot
    ORDER BY server_progid
""")
print("\n=== Rockwell PLC connection groups ===")
for r in cur.fetchall():
    print(f"  progid={r[0]:20} ip={r[1]:15} slot={r[2]}  tags={r[3]}")

c.close()
