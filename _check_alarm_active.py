"""Check alarm_active table columns"""
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    database='Automation_DB',
    user='cereveate',
    password='cereveate@222'
)

cur = conn.cursor()
cur.execute("""
    SELECT column_name
    FROM information_schema.columns
    WHERE table_schema='historian_raw' AND table_name='alarm_active'
    ORDER BY ordinal_position
""")

print("alarm_active columns:")
for row in cur.fetchall():
    print(f"  {row[0]}")

cur.close()
conn.close()
