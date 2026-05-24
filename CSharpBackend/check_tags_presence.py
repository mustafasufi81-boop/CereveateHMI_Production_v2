import psycopg2
from psycopg2.extras import RealDictCursor

DB = dict(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')

query = """
SELECT tag_id, tag_name, server_progid, enabled
FROM historian_meta.tag_master
WHERE tag_id = ANY(%s)
ORDER BY tag_id
"""

tags = ['WPS_ID','sim_step','TY1101A']

try:
    conn = psycopg2.connect(host=DB['host'], port=DB['port'], dbname=DB['dbname'], user=DB['user'], password=DB['password'])
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(query, (tags,))
    rows = cur.fetchall()
    if not rows:
        print('No rows found for tags:', tags)
    else:
        print('Found rows:')
        for r in rows:
            print(r)
except Exception as e:
    print('ERROR:', e)
finally:
    try:
        conn.close()
    except:
        pass
