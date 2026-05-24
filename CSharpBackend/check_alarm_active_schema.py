import psycopg2
conn = psycopg2.connect(host='localhost', dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_schema='historian_raw' AND table_name='alarm_active'
    ORDER BY ordinal_position
""")
cols = [r[0] for r in cur.fetchall()]
print("alarm_active columns:", cols)
cur.execute("SELECT COUNT(*) FROM historian_raw.alarm_active")
print("total rows:", cur.fetchone()[0])
cur.execute("SELECT alarm_state, COUNT(*) FROM historian_raw.alarm_active GROUP BY alarm_state")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")
conn.close()
