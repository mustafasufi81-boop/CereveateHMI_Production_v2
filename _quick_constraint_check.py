"""
Quick check for constraints and locks on alarm_audit_trail
"""
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    database='Automation_DB',
    user='cereveate',
    password='cereveate@222'
)

cur = conn.cursor()

print("=== FOREIGN KEYS ===")
cur.execute("""
    SELECT conname, contype 
    FROM pg_constraint 
    WHERE conrelid = 'historian_raw.alarm_audit_trail'::regclass
""")
for row in cur.fetchall():
    print(f"{row[0]} - Type: {row[1]}")

print("\n=== ACTIVE LOCKS ===")
cur.execute("""
    SELECT pid, mode, granted 
    FROM pg_locks 
    WHERE relation = 'historian_raw.alarm_audit_trail'::regclass
    AND pid != pg_backend_pid()
""")
locks = cur.fetchall()
if locks:
    for row in locks:
        print(f"PID {row[0]}: {row[1]} (Granted: {row[2]})")
else:
    print("No locks found - table is free")

print("\n=== DEPENDENT VIEWS ===")
cur.execute("""
    SELECT DISTINCT dependent_view.relname
    FROM pg_depend 
    JOIN pg_rewrite ON pg_depend.objid = pg_rewrite.oid 
    JOIN pg_class dependent_view ON pg_rewrite.ev_class = dependent_view.oid 
    JOIN pg_class source_table ON pg_depend.refobjid = source_table.oid 
    WHERE source_table.relname = 'alarm_audit_trail'
    AND dependent_view.relname != 'alarm_audit_trail'
""")
for row in cur.fetchall():
    print(f"View: {row[0]}")

cur.close()
conn.close()
print("\n✓ Check complete")
