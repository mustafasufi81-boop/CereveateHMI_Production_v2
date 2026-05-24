import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
conn.autocommit = True
cur = conn.cursor()

cur.execute("""
    SELECT table_schema, table_name
    FROM information_schema.tables
    WHERE table_name = 'tag_dim';
""")
row = cur.fetchone()
if row:
    print(f"EXISTS: {row[0]}.{row[1]}")
    cur.execute(f"SELECT COUNT(*) FROM {row[0]}.{row[1]};")
    print(f"Rows: {cur.fetchone()[0]}")
else:
    print("tag_dim does NOT exist in the database — was never created.")

cur.close()
conn.close()
