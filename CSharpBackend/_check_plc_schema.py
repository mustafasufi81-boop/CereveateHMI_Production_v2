import psycopg2
conn = psycopg2.connect(host='localhost', dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()

# All tables
cur.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema') ORDER BY 1,2")
print('=== ALL TABLES ===')
for r in cur.fetchall(): print(f'  {r[0]}.{r[1]}')

# Check plc_connections
print('\n=== plc_connections ===')
try:
    cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='plc_connections' ORDER BY ordinal_position")
    cols = cur.fetchall()
    for c in cols: print(f'  {c[0]} ({c[1]})')
    cur.execute('SELECT * FROM plc_connections')
    for r in cur.fetchall(): print('  ROW:', r)
except Exception as e: print('  ERROR:', e)

# Check plc_tags
print('\n=== plc_tags ===')
try:
    cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='plc_tags' ORDER BY ordinal_position")
    cols = cur.fetchall()
    for c in cols: print(f'  {c[0]} ({c[1]})')
    cur.execute('SELECT COUNT(*) FROM plc_tags')
    print('  COUNT:', cur.fetchone()[0])
    cur.execute('SELECT * FROM plc_tags LIMIT 3')
    for r in cur.fetchall(): print('  ROW:', r)
except Exception as e: print('  ERROR:', e)

# Check plc_tag_values
print('\n=== plc_tag_values (recent) ===')
try:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='plc_tag_values' ORDER BY ordinal_position")
    for c in cur.fetchall(): print(f'  {c[0]}')
    cur.execute('SELECT COUNT(*) FROM plc_tag_values')
    print('  COUNT:', cur.fetchone()[0])
    cur.execute('SELECT * FROM plc_tag_values ORDER BY timestamp DESC LIMIT 3')
    for r in cur.fetchall(): print('  ROW:', r)
except Exception as e: print('  ERROR:', e)

conn.close()
