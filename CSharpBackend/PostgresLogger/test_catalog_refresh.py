import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.background_importer_v2 import ParquetImporter

# Create importer
importer = ParquetImporter()

# Manually refresh catalog
print("Running manual catalog refresh...")
importer.refresh_tag_catalog()
print("Done!")

# Check what was updated
import psycopg2
conn = psycopg2.connect(
    host='localhost',
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)
cur = conn.cursor()

cur.execute("SELECT tag_id, last_file FROM tag_catalog WHERE tag_id LIKE 'Saw-toothed%' ORDER BY tag_id")
rows = cur.fetchall()
print('\nSaw-toothed tags in catalog:')
for r in rows:
    print(f'{r[0]}: {r[1].split(chr(92))[-1]}')

cur.close()
conn.close()
