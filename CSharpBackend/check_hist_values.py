import psycopg2, psycopg2.extras
conn = psycopg2.connect(host='localhost', dbname='Automation_DB', user='cereveate', password='cereveate@222', port=5432)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
cur.execute("SELECT tag_id, time, value_num, value_text, value_bool, quality FROM historian_raw.historian_timeseries ORDER BY time DESC LIMIT 10")
rows = cur.fetchall()
for r in rows:
    print(dict(r))
# Count nulls
cur.execute("SELECT COUNT(*) as total, COUNT(value_num) as non_null_num, COUNT(value_text) as non_null_text, COUNT(value_bool) as non_null_bool FROM historian_raw.historian_timeseries")
stats = cur.fetchone()
print("\nStats:", dict(stats))
conn.close()
