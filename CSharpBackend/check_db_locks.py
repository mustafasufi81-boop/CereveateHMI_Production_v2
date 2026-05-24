import psycopg2
conn = psycopg2.connect(host='localhost', dbname='Automation_DB', user='cereveate', password='cereveate@222')
conn.autocommit = True
cur = conn.cursor()

print("=== Blocking queries on historian_events ===")
cur.execute("""
    SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state
    FROM pg_stat_activity
    WHERE (query ILIKE '%historian_events%' OR query ILIKE '%alarm%')
      AND state != 'idle'
    ORDER BY duration DESC
    LIMIT 10
""")
for row in cur.fetchall():
    print(row)

print("\n=== Locks on historian_events ===")
cur.execute("""
    SELECT l.pid, l.mode, l.granted, a.query, a.state
    FROM pg_locks l
    JOIN pg_stat_activity a ON a.pid = l.pid
    JOIN pg_class c ON c.oid = l.relation
    WHERE c.relname = 'historian_events'
    LIMIT 10
""")
for row in cur.fetchall():
    print(row)

conn.close()
