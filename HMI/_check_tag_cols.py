import psycopg2
c = psycopg2.connect(dbname='Automation_DB', user='cereveate', password='cereveate@222', host='localhost')
cur = c.cursor()
cur.execute("SELECT COUNT(*) FROM historian_meta.tag_master WHERE server_progid IS NOT NULL AND server_progid != '' AND enabled = true")
print("Enabled tags with server_progid:", cur.fetchone()[0])
cur.execute("SELECT DISTINCT server_progid FROM historian_meta.tag_master WHERE server_progid IS NOT NULL AND server_progid != '' LIMIT 10")
print("Distinct server_progids:", [r[0] for r in cur.fetchall()])
cur.close(); c.close()
