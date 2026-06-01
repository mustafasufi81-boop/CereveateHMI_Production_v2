import psycopg2

c = psycopg2.connect(host='localhost', database='Automation_DB',
                     user='cereveate', password='cereveate@222')
cur = c.cursor()

cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_schema='historian_meta' AND table_name='tag_master'
    ORDER BY ordinal_position
""")
print("=== tag_master columns ===")
for r in cur.fetchall():
    print(f"  {r[0]:30} {r[1]}")

c.close()
