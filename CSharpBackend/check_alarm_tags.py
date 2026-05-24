import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()
cur.execute("""
    SELECT tag_id, enabled, alarm_enabled, server_progid
    FROM historian_meta.tag_master
    WHERE tag_id IN ('Random.Real4', 'Triangle Waves.Real4', 'Bucket Brigade.Real4')
""")
for r in cur.fetchall():
    print(r)
conn.close()
