import psycopg2

conn = psycopg2.connect(
    host='127.0.0.1', port=5432,
    dbname='Automation_DB',
    user='cereveate',
    password='cereveate@222'
)
cur = conn.cursor()

# Fix: server_progid must match the PLC name so all tags group under Rockwel_PLC_002
cur.execute("""
    UPDATE historian_meta.tag_master
    SET server_progid = 'Rockwel_PLC_002',
        plc_slot = 2,
        plc_path = '1,2'
    WHERE tag_id = 'CV1101B_AUTO'
""")
print("Rows updated:", cur.rowcount)
conn.commit()

# Verify
cur.execute("SELECT tag_id, tag_name, server_progid, plc_slot, plc_path FROM historian_meta.tag_master WHERE tag_id = 'CV1101B_AUTO'")
row = cur.fetchone()
print("tag_id:", row[0])
print("tag_name:", row[1])
print("server_progid:", row[2])
print("plc_slot:", row[3])
print("plc_path:", row[4])

# Check how many tags are now under each server_progid
print("\n--- Tags per server_progid ---")
cur.execute("SELECT server_progid, COUNT(*) FROM historian_meta.tag_master GROUP BY server_progid ORDER BY server_progid")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]} tags")

conn.close()
print("\nDone.")
