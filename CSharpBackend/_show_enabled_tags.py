import psycopg2, json, re

cfg = json.load(open('appsettings.json'))
cs = cfg['Historian']['Database']['ConnectionString']
m = re.findall(r'Host=([^;]+);Port=([^;]+);Database=([^;]+);Username=([^;]+);Password=([^;]+)', cs, re.I)
h, p, db, u, pw = m[0]
conn = psycopg2.connect(host=h, port=p, dbname=db, user=u, password=pw)
cur = conn.cursor()

cur.execute("""
    SELECT tag_id, data_type, db_logging_interval_ms, deadband_enabled, deadband_value
    FROM historian_meta.tag_master
    WHERE enabled = true
    ORDER BY tag_id
""")
rows = cur.fetchall()
print(f"{'TAG_ID':<35} {'TYPE':<8} {'INTERVAL_MS':>12}  {'DEADBAND':>10}  {'DB_VALUE':>10}")
print("-" * 80)
for r in rows:
    print(f"{r[0]:<35} {r[1]:<8} {r[2]:>12}  {str(r[3]):>10}  {str(r[4]):>10}")
print(f"\nTotal enabled: {len(rows)}")
conn.close()
