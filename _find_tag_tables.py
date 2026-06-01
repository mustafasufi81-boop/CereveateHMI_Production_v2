import psycopg2
c=psycopg2.connect(host='localhost',database='Automation_DB',user='cereveate',password='cereveate@222')
cur=c.cursor()
cur.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_name LIKE '%alarm%' OR table_name LIKE '%tag%' ORDER BY table_schema, table_name")
for r in cur.fetchall():
    print(f"{r[0]}.{r[1]}")
