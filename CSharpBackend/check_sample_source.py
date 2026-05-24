import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, database='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()

# Check distinct sample_source values
cur.execute("SELECT DISTINCT sample_source, count(*) FROM historian_raw.historian_timeseries GROUP BY sample_source ORDER BY count(*) DESC LIMIT 10")
print('=== sample_source values in DB ===')
for r in cur.fetchall():
    print(f'  sample_source={repr(r[0])}  count={r[1]}')

# Check actual PLC tag rows
cur.execute("SELECT tag_id, sample_source, value_num FROM historian_raw.historian_timeseries WHERE tag_id IN ('AY1101','CV1101','PDY1101') ORDER BY time DESC LIMIT 6")
print()
print('=== Sample PLC tag rows ===')
for r in cur.fetchall():
    print(f'  tag_id={r[0]}  sample_source={repr(r[1])}  value={r[2]}')

conn.close()
