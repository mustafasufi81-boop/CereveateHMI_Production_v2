import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)
cur = conn.cursor()

# First check schema
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='tag_catalog'")
cols = cur.fetchall()
print('tag_catalog columns:')
for c in cols:
    print(f'  - {c[0]}')

# Check all data
print('\nAll tags in catalog:')
cur.execute('SELECT * FROM tag_catalog LIMIT 10')
rows = cur.fetchall()
for row in rows:
    print(row)

# Check total unique tags
cur.execute('SELECT COUNT(*) FROM tag_catalog')
total_tags = cur.fetchone()[0]
print(f'\nTotal records in tag_catalog: {total_tags}')

cur.close()
conn.close()
