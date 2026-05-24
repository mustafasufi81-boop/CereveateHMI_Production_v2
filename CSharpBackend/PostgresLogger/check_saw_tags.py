import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)
cur = conn.cursor()

# Check Saw-toothed tags
cur.execute("SELECT tag_id, last_file FROM tag_catalog WHERE tag_id LIKE 'Saw-toothed%' ORDER BY tag_id")
rows = cur.fetchall()
print('Saw-toothed tags in catalog:')
for r in rows:
    print(f'{r[0]}: {r[1].split(chr(92))[-1]}')

print('\nExpected: OpcData_20251117_212532.parquet (newest file)')

cur.close()
conn.close()
