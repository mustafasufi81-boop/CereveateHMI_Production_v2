import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)
cur = conn.cursor()

# Clear import history
cur.execute("DELETE FROM file_imports WHERE file_path LIKE '%ALL_SENSORS_COMPLETE_FORWARDFILL%'")
conn.commit()
print(f'Cleared {cur.rowcount} import records')

# Check current data
cur.execute("SELECT COUNT(*) FROM sensor_data WHERE tag_code = 'SHAFT_VIB._IP_REAR-X'")
count = cur.fetchone()[0]
print(f'Current data count for SHAFT_VIB._IP_REAR-X: {count}')

conn.close()
print('Done!')
