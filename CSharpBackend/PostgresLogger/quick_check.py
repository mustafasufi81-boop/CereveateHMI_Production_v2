import psycopg2

conn = psycopg2.connect(host='localhost', database='Cereveate', user='cereveate', password='cereveate@222')
cur = conn.cursor()

# All tags in database
cur.execute("SELECT tag_code, COUNT(*) FROM sensor_data WHERE tag_code IS NOT NULL GROUP BY tag_code ORDER BY tag_code")
rows = cur.fetchall()

print('\n=== TAGS IN DATABASE ===')
for row in rows:
    print(f'  {row[0]}: {row[1]:,} records')
print(f'\nTotal: {len(rows)} tags')

# Tag imports
cur.execute("SELECT tag_id, records_imported FROM tag_imports ORDER BY tag_id")
imports = cur.fetchall()

print('\n=== TAG_IMPORTS TABLE ===')
for row in imports:
    print(f'  {row[0]}: {row[1]:,} records logged')
print(f'\nTotal: {len(imports)} tags logged')

cur.close()
conn.close()
