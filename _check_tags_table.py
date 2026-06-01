"""
Check for tags table in database
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

# Find tables with 'tag' in name
cur.execute("""
    SELECT table_schema, table_name
    FROM information_schema.tables
    WHERE table_name LIKE '%tag%'
    ORDER BY table_schema, table_name
""")

print("Tables with 'tag' in name:")
for row in cur.fetchall():
    print(f"  {row[0]}.{row[1]}")

# Check current view definition
cur.execute("""
    SELECT definition
    FROM pg_views
    WHERE schemaname = 'historian_raw'
    AND viewname = 'v_alarm_audit_trail'
""")
result = cur.fetchone()
if result:
    print("\nCurrent view definition:")
    print(result[0][:500])

cur.close()
conn.close()
