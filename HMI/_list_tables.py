import psycopg2
conn = psycopg2.connect(host='localhost',port=5432,database='Automation_DB',user='cereveate',password='cereveate@222')
cur = conn.cursor()
cur.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema') ORDER BY table_schema, table_name")
for r in cur.fetchall():
    print(r[0] + '.' + r[1])
conn.close()
