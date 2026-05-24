import psycopg2, json, re

cfg = json.load(open('appsettings.json'))
cs = cfg['Historian']['Database']['ConnectionString']
m = re.findall(r'Host=([^;]+);Port=([^;]+);Database=([^;]+);Username=([^;]+);Password=([^;]+)', cs, re.I)
h, p, db, u, pw = m[0]
conn = psycopg2.connect(host=h, port=p, dbname=db, user=u, password=pw)
cur = conn.cursor()

tags = ['Random.Real4', 'Triangle Waves.Real4']

for tag in tags:
    print(f"\n{'='*60}")
    print(f"TAG: {tag}")
    print(f"{'='*60}")

    # Last 10 writes with actual gap between them
    cur.execute("""
        SELECT time, value_num,
               ROUND(EXTRACT(EPOCH FROM (time - LAG(time) OVER (ORDER BY time))) * 1000) AS gap_ms
        FROM historian_raw.historian_timeseries
        WHERE tag_id = %s
        ORDER BY time DESC
        LIMIT 15
    """, (tag,))
    rows = cur.fetchall()
    if not rows:
        print("  No data yet.")
        continue

    print(f"  {'TIMESTAMP':<35} {'VALUE':>12}  {'GAP_FROM_PREV_MS':>18}")
    print(f"  {'-'*70}")
    for r in rows:
        gap = f"{int(r[2])}ms" if r[2] is not None else "  (first)"
        print(f"  {str(r[0]):<35} {str(round(float(r[1]),2)):>12}  {gap:>18}")

conn.close()
