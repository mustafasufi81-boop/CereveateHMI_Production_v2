import psycopg2

conn = psycopg2.connect(
    host='127.0.0.1', port=5432,
    dbname='Automation_DB',
    user='cereveate',
    password='cereveate@222'
)
cur = conn.cursor()

cur.execute("""
    UPDATE historian_meta.tag_master
    SET tag_name = 'CV1101B_AUTO'
    WHERE tag_id = 'CV1101B_AUTO'
""")
print("Rows updated:", cur.rowcount)
conn.commit()

cur.execute("SELECT tag_id, tag_name, server_progid FROM historian_meta.tag_master WHERE tag_id = 'CV1101B_AUTO'")
row = cur.fetchone()
print("tag_id      :", row[0])
print("tag_name    :", row[1])
print("server_progid:", row[2])
conn.close()
print("Done.")
