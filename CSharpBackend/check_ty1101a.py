import psycopg2, os, sys
DB_HOST = os.environ.get('PGHOST', 'localhost')
DB_PORT = os.environ.get('PGPORT', '5432')
DB_NAME = os.environ.get('PGDATABASE', 'Automation_DB')
DB_USER = os.environ.get('PGUSER', 'cereveate')
DB_PASS = os.environ.get('PGPASSWORD', 'cereveate@222')
try:
    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
    cur = conn.cursor()
    cur.execute("SELECT tag_id, tag_name FROM historian_meta.tag_master WHERE tag_id = %s", ('TY1101A',))
    row = cur.fetchone()
    if row:
        print('FOUND:', row)
    else:
        print('NOT FOUND: TY1101A')
except Exception as e:
    print('ERROR:', e)
    sys.exit(2)
finally:
    try:
        conn.close()
    except:
        pass
