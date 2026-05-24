import psycopg2, os, sys
DB_HOST = os.environ.get('PGHOST','localhost')
DB_PORT = os.environ.get('PGPORT','5432')
DB_NAME = os.environ.get('PGDATABASE','Automation_DB')
DB_USER = os.environ.get('PGUSER','cereveate')
DB_PASS = os.environ.get('PGPASSWORD','cereveate@222')
try:
    conn = psycopg2.connect(host=DB_HOST,port=DB_PORT,dbname=DB_NAME,user=DB_USER,password=DB_PASS)
    cur = conn.cursor()
    cur.execute("SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'historian_meta.tag_master'::regclass;")
    rows = cur.fetchall()
    if not rows:
        print('No constraints found')
    for name, defn in rows:
        print(name)
        print(defn)
        print()
except Exception as e:
    print('Error:', e)
    sys.exit(2)
finally:
    try:
        conn.close()
    except:
        pass
