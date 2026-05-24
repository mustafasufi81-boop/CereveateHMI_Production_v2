import psycopg2, json, re

cfg = json.load(open('appsettings.json'))
cs = cfg['Historian']['Database']['ConnectionString']
m = re.findall(r'Host=([^;]+);Port=([^;]+);Database=([^;]+);Username=([^;]+);Password=([^;]+)', cs, re.I)
h, p, db, u, pw = m[0]
conn = psycopg2.connect(host=h, port=p, dbname=db, user=u, password=pw)
cur = conn.cursor()

print("=== historian_meta.tag_master SCHEMA ===")
cur.execute("""
    SELECT ordinal_position, column_name, data_type, is_nullable, column_default
    FROM information_schema.columns
    WHERE table_schema='historian_meta' AND table_name='tag_master'
    ORDER BY ordinal_position
""")
cols = cur.fetchall()
for c in cols:
    print(f"  [{c[0]:2d}] {c[1]:<30} {c[2]:<25} nullable={c[3]}  default={c[4]}")

print()
print("=== SAMPLE ROW ===")
cur.execute("SELECT * FROM historian_meta.tag_master LIMIT 3")
rows = cur.fetchall()
col_names = [desc[0] for desc in cur.description]
for row in rows:
    print()
    for name, val in zip(col_names, row):
        print(f"  {name:<30} = {val}")

conn.close()
