import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)
cur = conn.cursor()

# Delete import records
cur.execute('DELETE FROM file_imports')
deleted = cur.rowcount
conn.commit()
print(f'✅ Deleted {deleted} import records')

# Check both tags
cur.execute("SELECT COUNT(*) FROM sensor_data WHERE tag_code = 'SHAFT_VIB._IP_REAR-X'")
count1 = cur.fetchone()[0]
print(f'SHAFT_VIB._IP_REAR-X: {count1:,} records')

cur.execute("SELECT COUNT(*) FROM sensor_data WHERE tag_code = 'BEARING_VIB_HP_FRONT-Y'")
count2 = cur.fetchone()[0]
print(f'BEARING_VIB_HP_FRONT-Y: {count2:,} records')

cur.close()
conn.close()

print('\n🔄 Import history cleared. Importer will re-process the file with BOTH tags.')
