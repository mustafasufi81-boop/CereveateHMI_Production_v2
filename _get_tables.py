import psycopg2
c=psycopg2.connect(host='localhost',database='Automation_DB',user='cereveate',password='cereveate@222')
cur=c.cursor()
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='historian_raw' ORDER BY table_name")
print('\n'.join([r[0] for r in cur.fetchall()]))
