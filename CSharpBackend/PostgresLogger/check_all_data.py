import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)
cur = conn.cursor()

# Check all tags
cur.execute("SELECT tag_code, COUNT(*) FROM sensor_data GROUP BY tag_code ORDER BY COUNT(*) DESC")
rows = cur.fetchall()

print('\n=== ALL TAGS IN DATABASE ===')
for row in rows:
    tag = row[0] if row[0] else "NULL"
    count = row[1]
    print(f'  {tag}: {count:,} records')

print(f'\nTotal unique tags: {len(rows)}')

# Check tag_imports
cur.execute("SELECT tag_id, records_imported FROM tag_imports")
tag_imports = cur.fetchall()

print(f'\n=== TAG_IMPORTS TABLE ===')
if tag_imports:
    for row in tag_imports:
        print(f'  {row[0]}: {row[1]} records logged')
else:
    print('  (empty - no imports logged yet)')

cur.close()
conn.close()
