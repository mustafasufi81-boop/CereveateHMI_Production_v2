import psycopg2
conn = psycopg2.connect(host='localhost', dbname='Automation_DB', user='cereveate', password='cereveate@222')
conn.autocommit = True
cur = conn.cursor()

print("Terminating PID 37416 (idle in transaction)...")
cur.execute("SELECT pg_terminate_backend(37416)")
print("Result:", cur.fetchone())

# Also terminate any other idle-in-transaction sessions older than 5 minutes
cur.execute("""
    SELECT pg_terminate_backend(pid)
    FROM pg_stat_activity
    WHERE state = 'idle in transaction'
      AND now() - query_start > interval '5 minutes'
      AND pid != pg_backend_pid()
""")
terminated = cur.fetchall()
print(f"Terminated {len(terminated)} stale idle-in-transaction sessions")

conn.close()
print("Done.")
