import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
conn.autocommit = True
cur = conn.cursor()

cur.execute("""
    SELECT
        cs.chunk_name,
        c.range_start::date AS start,
        c.range_end::date   AS end,
        pg_size_pretty(cs.before_compression_total_bytes) AS before,
        pg_size_pretty(cs.after_compression_total_bytes)  AS after,
        ROUND(cs.before_compression_total_bytes::numeric /
              NULLIF(cs.after_compression_total_bytes, 0), 1) AS ratio
    FROM chunk_compression_stats('historian_raw.historian_timeseries') cs
    JOIN timescaledb_information.chunks c
      ON c.chunk_name = cs.chunk_name
     AND c.hypertable_schema = 'historian_raw'
     AND c.hypertable_name   = 'historian_timeseries'
    ORDER BY c.range_start;
""")
rows = cur.fetchall()

print(f"{'Chunk':<45} {'Period':<25} {'Before':>10} {'After':>10} {'Ratio':>8}")
print("-" * 105)
for r in rows:
    period = f"{r[1]} → {r[2]}"
    ratio_str = f"{r[5]}x" if r[5] else "N/A"
    before_str = r[3] or "N/A"
    after_str  = r[4] or "N/A"
    print(f"  {r[0]:<43} {period:<25} {before_str:>10} {after_str:>10} {ratio_str:>8}")# Totals
cur.execute("""
    SELECT
        pg_size_pretty(SUM(before_compression_total_bytes)) AS total_before,
        pg_size_pretty(SUM(after_compression_total_bytes))  AS total_after,
        ROUND(SUM(before_compression_total_bytes)::numeric /
              NULLIF(SUM(after_compression_total_bytes), 0), 2) AS overall_ratio,
        SUM(before_compression_total_bytes) AS raw_before,
        SUM(after_compression_total_bytes)  AS raw_after
    FROM chunk_compression_stats('historian_raw.historian_timeseries');
""")
t = cur.fetchone()
saved = t[3] - t[4]

print("-" * 105)
print(f"\n  {'TOTAL COMPRESSED CHUNKS':43}  {'':25} {t[0]:>10} {t[1]:>10} {str(t[2])+'x':>8}")
print(f"\n  Disk saved by compression : {saved / (1024**2):.0f} MB")

# Also show uncompressed chunks sizes
print("\n  Uncompressed chunks (active write window):")
cur.execute("""
    SELECT range_start::date, range_end::date,
           pg_size_pretty(pg_total_relation_size(
               (chunk_schema || '.' || chunk_name)::regclass)) AS size
    FROM timescaledb_information.chunks
    WHERE hypertable_schema = 'historian_raw'
      AND hypertable_name   = 'historian_timeseries'
      AND is_compressed = false
    ORDER BY range_start;
""")
for r in cur.fetchall():
    print(f"    {r[0]} → {r[1]}  {r[2]:>10}  (not yet compressed)")

cur.close()
conn.close()
