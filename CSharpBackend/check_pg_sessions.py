import psycopg2
conn = psycopg2.connect(host='localhost', dbname='Automation_DB', user='cereveate', password='cereveate@222')
conn.autocommit = True
cur = conn.cursor()

print("=== All non-idle sessions ===")
cur.execute("""
    SELECT pid, state, now() - query_start AS duration, left(query, 120) as query
    FROM pg_stat_activity
    WHERE state != 'idle' AND pid != pg_backend_pid()
    ORDER BY duration DESC NULLS LAST
""")
for row in cur.fetchall():
    print(row)

print("\n=== idle in transaction sessions ===")
cur.execute("""
    SELECT pid, state, now() - query_start AS duration, left(query,100) as query
    FROM pg_stat_activity
    WHERE state = 'idle in transaction'
""")
for row in cur.fetchall():
    print(row)

conn.close()
