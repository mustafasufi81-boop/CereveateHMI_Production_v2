import psycopg2
c=psycopg2.connect(host='localhost',database='Automation_DB',user='cereveate',password='cereveate@222')
cur=c.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='historian_events' AND table_schema='historian_raw' ORDER BY ordinal_position")
print('\n'.join([r[0] for r in cur.fetchall()]))
