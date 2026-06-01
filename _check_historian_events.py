"""
Check historian_events table structure
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

cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_schema='historian_raw' AND table_name='historian_events'
    ORDER BY ordinal_position
""")

print("historian_events columns:")
for row in cur.fetchall():
    print(f"  {row[0]:<30} {row[1]}")

cur.close()
conn.close()
