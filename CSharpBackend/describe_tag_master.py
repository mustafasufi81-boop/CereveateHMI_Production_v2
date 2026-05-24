import psycopg2, os, sys
DB_HOST = os.environ.get('PGHOST', 'localhost')
DB_PORT = os.environ.get('PGPORT', '5432')
DB_NAME = os.environ.get('PGDATABASE', 'Automation_DB')
DB_USER = os.environ.get('PGUSER', 'cereveate')
DB_PASS = os.environ.get('PGPASSWORD', 'cereveate@222')
try:
    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema='historian_meta' AND table_name='tag_master'
        ORDER BY ordinal_position
    """)
    rows = cur.fetchall()
    print('column_name | data_type | is_nullable | column_default')
    print('-----------------------------------------------------')
    for r in rows:
        print(f"{r[0]} | {r[1]} | {r[2]} | {r[3]}")
except Exception as e:
    print('Error:', e)
    sys.exit(2)
finally:
    try:
        conn.close()
    except:
        pass
