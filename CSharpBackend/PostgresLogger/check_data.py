import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)
cur = conn.cursor()

# Check data count
cur.execute("SELECT COUNT(*) FROM sensor_data WHERE tag_code = 'SHAFT_VIB._IP_REAR-X'")
count = cur.fetchone()[0]
print(f'✅ Data imported successfully!')
print(f'Records for SHAFT_VIB._IP_REAR-X: {count}')

# Show sample data
cur.execute("""
    SELECT timestamp, tag_name, plant, asset, value, quality_code, status_flag, data_source 
    FROM sensor_data 
    WHERE tag_code = 'SHAFT_VIB._IP_REAR-X' 
    ORDER BY timestamp DESC 
    LIMIT 3
""")
rows = cur.fetchall()
print('\nSample data:')
for row in rows:
    print(f'  {row[0]} | {row[1]} | {row[2]} | {row[3]} | Value: {row[4]} | Quality: {row[5]} | Status: {row[6]} | Source: {row[7]}')

conn.close()
