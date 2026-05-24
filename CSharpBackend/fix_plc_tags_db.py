import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()

# Disable every Rockwel_PLC_001 tag that is NOT TY1101A
cur.execute("""
    UPDATE historian_meta.tag_master
    SET enabled = false
    WHERE server_progid = 'Rockwel_PLC_001'
      AND tag_id <> 'TY1101A'
""")
print(f'Disabled {cur.rowcount} old tags')

conn.commit()

# Verify
cur.execute("""
    SELECT tag_id, enabled
    FROM historian_meta.tag_master
    WHERE server_progid = 'Rockwel_PLC_001'
    ORDER BY enabled DESC, tag_id
""")
print('\nCurrent state for Rockwel_PLC_001:')
for r in cur.fetchall():
    status = 'ENABLED' if r[1] else 'disabled'
    print(f'  [{status}] {r[0]}')

conn.close()
