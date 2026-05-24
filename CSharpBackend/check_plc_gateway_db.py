import psycopg2
import psycopg2.extras

conn = psycopg2.connect(host='localhost', port=5432, database='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# 1. Check plc_gateway schema tables
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='plc_gateway' ORDER BY table_name")
print('=== plc_gateway tables ===')
for r in cur.fetchall():
    print(' ', r['table_name'])

# 2. Check historian_meta tables
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='historian_meta' ORDER BY table_name")
print('\n=== historian_meta tables ===')
for r in cur.fetchall():
    print(' ', r['table_name'])

# 3. Try to get PLC configs
try:
    cur.execute("SELECT * FROM plc_gateway.plc_configs WHERE enabled=true ORDER BY plc_id")
    print('\n=== plc_gateway.plc_configs (enabled) ===')
    rows = cur.fetchall()
    if rows:
        for r in rows:
            print(dict(r))
    else:
        print('  NO ROWS FOUND')
except Exception as e:
    print(f'\n  plc_configs query failed: {e}')

# 4. Try historian_meta for plc info
try:
    cur.execute("SELECT DISTINCT server_progid, count(*) FROM historian_meta.tag_master WHERE enabled=true GROUP BY server_progid ORDER BY server_progid")
    print('\n=== tag_master enabled tags by server_progid ===')
    for r in cur.fetchall():
        print(' ', dict(r))
except Exception as e:
    print(f'  tag_master query failed: {e}')

conn.close()
