import psycopg2
c=psycopg2.connect(host='localhost',database='Automation_DB',user='cereveate',password='cereveate@222')
cur=c.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='tag_master' AND table_schema='historian_meta' ORDER BY ordinal_position")
print('\n'.join([r[0] for r in cur.fetchall()]))
