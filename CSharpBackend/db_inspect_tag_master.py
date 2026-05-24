import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, database='Cereveate', user='cereveate', password='cereveate@222')
cur = conn.cursor()
cur.execute("""
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'historian_meta' AND table_name = 'tag_master'
ORDER BY ordinal_position
""")
rows = cur.fetchall()
print('COLUMNS:')
for r in rows:
    print(f"- {r[0]} | {r[1]} | nullable={r[2]} | default={r[3]}")
conn.close()
