import psycopg2, json, re

cfg = json.load(open('appsettings.json'))
cs = cfg['Historian']['Database']['ConnectionString']
m = re.findall(r'Host=([^;]+);Port=([^;]+);Database=([^;]+);Username=([^;]+);Password=([^;]+)', cs, re.I)
h, p, db, u, pw = m[0]
conn = psycopg2.connect(host=h, port=p, dbname=db, user=u, password=pw)
cur = conn.cursor()

# Query actual historical stats for Random.* and Triangle Waves.* tags
# from last 24 hours — min, max, avg, stddev, row count
cur.execute("""
    SELECT
        tag_id,
        COUNT(*)                          AS row_count,
        ROUND(MIN(value_num)::numeric, 4) AS min_val,
        ROUND(MAX(value_num)::numeric, 4) AS max_val,
        ROUND(AVG(value_num)::numeric, 4) AS avg_val,
        ROUND(STDDEV(value_num)::numeric, 4) AS stddev_val,
        ROUND((MAX(value_num) - MIN(value_num))::numeric, 4) AS range_val
    FROM historian_raw.historian_timeseries
    WHERE tag_id LIKE 'Random.%'
       OR tag_id LIKE 'Triangle Waves.%'
    GROUP BY tag_id
    ORDER BY tag_id
""")
rows = cur.fetchall()

if not rows:
    print("No historical data found for these tags yet.")
else:
    print(f"{'TAG_ID':<35} {'ROWS':>6}  {'MIN':>10}  {'MAX':>10}  {'AVG':>10}  {'STDDEV':>10}  {'RANGE':>10}  SUGGESTED_DEADBAND")
    print("-" * 120)
    for r in rows:
        tag_id, count, mn, mx, avg, std, rng = r
        # Suggest deadband as ~5% of range, or 1x stddev — whichever is smaller and > 0
        suggested = None
        if rng and rng > 0:
            pct5 = round(float(rng) * 0.05, 4)
            std_val = round(float(std), 4) if std else None
            suggested = min(pct5, std_val) if std_val else pct5
        print(f"{tag_id:<35} {count:>6}  {str(mn):>10}  {str(mx):>10}  {str(avg):>10}  {str(std):>10}  {str(rng):>10}  {suggested if suggested else 'N/A (no range)'}")

conn.close()
