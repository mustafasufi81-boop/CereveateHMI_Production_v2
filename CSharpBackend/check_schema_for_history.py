import psycopg2
conn = psycopg2.connect(dbname='Automation_DB', user='cereveate', password='cereveate@222', host='localhost', port=5432)
cur = conn.cursor()

cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='historian_raw' AND table_name='historian_events' ORDER BY ordinal_position")
print('historian_events:', [r[0] for r in cur.fetchall()])

cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='historian_raw' AND table_name='alarm_audit_trail' ORDER BY ordinal_position")
print('alarm_audit_trail:', [r[0] for r in cur.fetchall()])

cur.execute("SELECT * FROM historian_raw.historian_events ORDER BY occurred_at DESC LIMIT 2")
cols = [d[0] for d in cur.description]
rows = cur.fetchall()
print('historian_events cols:', cols)
for r in rows:
    print(dict(zip(cols, r)))

cur.execute("SELECT * FROM historian_raw.alarm_audit_trail ORDER BY action_timestamp DESC LIMIT 2")
cols2 = [d[0] for d in cur.description]
rows2 = cur.fetchall()
print('audit_trail cols:', cols2)
for r in rows2:
    print(dict(zip(cols2, r)))

conn.close()
