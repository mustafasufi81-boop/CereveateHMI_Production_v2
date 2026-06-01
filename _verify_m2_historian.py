import psycopg2, time

# Give the historian a few write cycles (interval default 5s)
time.sleep(15)

c = psycopg2.connect(host='localhost', database='Automation_DB',
                     user='cereveate', password='cereveate@222')
cur = c.cursor()

def latest(tag, n=5):
    cur.execute("""
        SELECT time, tag_id, value_num, quality
        FROM historian_raw.historian_timeseries
        WHERE tag_id = %s
        ORDER BY time DESC
        LIMIT %s
    """, (tag, n))
    return cur.fetchall()

print("=== TY1102F (Bad denormal tag) — expect value_num=NULL, quality='B' ===")
for r in latest('TY1102F'):
    vn = 'NULL' if r[2] is None else r[2]
    print(f"  {r[0]}  value_num={vn}  quality={r[3]!r}")

print("\n=== TY1103F (healthy REAL) — expect real number, quality='G' ===")
for r in latest('TY1103F'):
    vn = 'NULL' if r[2] is None else r[2]
    print(f"  {r[0]}  value_num={vn}  quality={r[3]!r}")

# Sanity: any NaN/Inf that slipped into value_num anywhere recently?
cur.execute("""
    SELECT COUNT(*) FROM historian_raw.historian_timeseries
    WHERE time > now() - interval '2 minutes'
      AND value_num IS NOT NULL
      AND (value_num = 'NaN'::float8 OR value_num = 'Infinity'::float8 OR value_num = '-Infinity'::float8)
""")
print(f"\n=== Non-finite values in value_num (last 2 min): {cur.fetchone()[0]} (expect 0) ===")

# Cross-check: rows where quality='B' but value_num is not null (should be 0 after M2)
cur.execute("""
    SELECT COUNT(*) FROM historian_raw.historian_timeseries
    WHERE time > now() - interval '2 minutes'
      AND quality = 'B' AND value_num IS NOT NULL
""")
print(f"=== Bad-quality rows WITH a value_num (last 2 min): {cur.fetchone()[0]} (expect 0) ===")

c.close()
