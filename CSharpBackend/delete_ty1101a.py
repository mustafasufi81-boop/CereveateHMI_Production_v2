import psycopg2
import os, sys
DB_HOST = os.environ.get('PGHOST', 'localhost')
DB_PORT = os.environ.get('PGPORT', '5432')
DB_NAME = os.environ.get('PGDATABASE', 'Automation_DB')
DB_USER = os.environ.get('PGUSER', 'cereveate')
DB_PASS = os.environ.get('PGPASSWORD', 'cereveate@222')

try:
    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
    cur = conn.cursor()
    cur.execute('BEGIN')
    cur.execute("DELETE FROM historian_meta.tag_master WHERE tag_id = %s RETURNING tag_id, tag_name", ('TY1101A',))
    row = cur.fetchone()
    if row:
        print('Deleted row:', row)
    else:
        print('No row found to delete for tag_id=TY1101A')
    conn.commit()
    # Verify
    cur.execute("SELECT tag_id FROM historian_meta.tag_master WHERE tag_id = %s", ('TY1101A',))
    verify = cur.fetchone()
    if verify:
        print('Verification failed: row still present:', verify)
        sys.exit(2)
    else:
        print('Verification passed: TY1101A no longer present')
except Exception as e:
    try:
        conn.rollback()
    except:
        pass
    print('Error:', e)
    sys.exit(2)
finally:
    try:
        conn.close()
    except:
        pass
