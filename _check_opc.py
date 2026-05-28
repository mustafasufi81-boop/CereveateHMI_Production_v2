import psycopg2
conn = psycopg2.connect(dbname='Automation_DB', user='cereveate', password='cereveate@222', host='localhost')
cur = conn.cursor()

# Get actual column names
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='historian_meta' AND table_name='tag_master' ORDER BY ordinal_position")
cols = [r[0] for r in cur.fetchall()]
print("=== tag_master columns ===")
print(cols)

# server_progid breakdown
print("\n=== server_progid breakdown ===")
cur.execute("SELECT server_progid, enabled, COUNT(*) FROM historian_meta.tag_master GROUP BY server_progid, enabled ORDER BY server_progid")
for r in cur.fetchall():
    print(f"  server_progid={str(r[0]):50}  enabled={r[1]}  count={r[2]}")

# Check logging_config for OPC ProgID
print("\n=== logging_config OPC progid ===")
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='historian_meta' AND table_name='logging_config'")
lc_cols = [r[0] for r in cur.fetchall()]
print("logging_config columns:", lc_cols)
cur.execute("SELECT * FROM historian_meta.logging_config LIMIT 5")
for r in cur.fetchall():
    print(" ", r)

conn.close()
