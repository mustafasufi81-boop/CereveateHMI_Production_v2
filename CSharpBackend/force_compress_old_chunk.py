import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
conn.autocommit = True
cur = conn.cursor()

# Get the exact chunk name for 2026-05-07 → 2026-05-14
cur.execute("""
    SELECT chunk_schema || '.' || chunk_name AS chunk
    FROM timescaledb_information.chunks
    WHERE hypertable_schema = 'historian_raw'
      AND hypertable_name   = 'historian_timeseries'
      AND is_compressed = false
      AND range_end <= '2026-05-14';
""")
rows = cur.fetchall()

if not rows:
    print("No eligible chunks found to force-compress.")
else:
    for r in rows:
        chunk = r[0]
        print(f"Force compressing: {chunk} ...")
        cur.execute(f"SELECT compress_chunk('{chunk}', if_not_compressed => true);")
        print(f"  Done: {cur.fetchone()[0]}")

print("\nFinal state:")
cur.execute("""
    SELECT range_start::date, range_end::date, is_compressed,
           pg_size_pretty(pg_total_relation_size(
               (chunk_schema || '.' || chunk_name)::regclass)) AS size
    FROM timescaledb_information.chunks
    WHERE hypertable_schema = 'historian_raw'
      AND hypertable_name   = 'historian_timeseries'
    ORDER BY range_start;
""")
for r in cur.fetchall():
    label = "✅ COMPRESSED  " if r[2] else "🔓 uncompressed (active)"
    print(f"  {r[0]} → {r[1]}  {label}  {r[3]}")

cur.execute("""
    SELECT
        pg_size_pretty(SUM(before_compression_total_bytes)) AS before,
        pg_size_pretty(SUM(after_compression_total_bytes))  AS after,
        ROUND(SUM(before_compression_total_bytes)::numeric /
              NULLIF(SUM(after_compression_total_bytes),0), 2) AS ratio
    FROM chunk_compression_stats('historian_raw.historian_timeseries');
""")
cs = cur.fetchone()
print(f"\nTotal compressed: {cs[0]} → {cs[1]}  ({cs[2]}x ratio)")

cur.close()
conn.close()
