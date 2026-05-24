import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='historian_meta' AND table_name='tag_master' ORDER BY column_name")
print([r[0] for r in cur.fetchall()])
conn.close()
