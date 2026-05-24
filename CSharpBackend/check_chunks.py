import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
conn.autocommit = True
cur = conn.cursor()

print("=" * 70)
print("Chunk size breakdown — compressed vs uncompressed")
print("=" * 70)

cur.execute("""
    SELECT
        c.chunk_schema || '.' || c.chunk_name AS chunk,
        c.range_start::date AS start,
        c.range_end::date   AS end,
        c.is_compressed,
        pg_size_pretty(pg_total_relation_size(
            (c.chunk_schema || '.' || c.chunk_name)::regclass
        )) AS size_on_disk
    FROM timescaledb_information.chunks c
    WHERE c.hypertable_schema = 'historian_raw'
      AND c.hypertable_name   = 'historian_timeseries'
    ORDER BY c.range_start;
""")
rows = cur.fetchall()
total_compressed = 0
total_uncompressed = 0

for r in rows:
    label = "✅ COMPRESSED  " if r[3] else "🔓 uncompressed"
    print(f"  {r[1]} → {r[2]}  {label}  {r[4]}")

print()

# Compression ratio for compressed chunks
cur.execute("""
    SELECT
        pg_size_pretty(SUM(before_compression_total_bytes)) AS before,
        pg_size_pretty(SUM(after_compression_total_bytes))  AS after,
        ROUND(SUM(before_compression_total_bytes)::numeric /
              NULLIF(SUM(after_compression_total_bytes),0), 2) AS ratio
    FROM chunk_compression_stats('historian_raw.historian_timeseries');
""")
cs = cur.fetchone()
if cs and cs[0]:
    print(f"Compressed chunks:  {cs[0]} → {cs[1]}  (ratio: {cs[2]}x)")

# Row counts per uncompressed chunk
print("\nUncompressed chunk row counts (active write window):")
cur.execute("""
    SELECT
        chunk_schema || '.' || chunk_name AS chunk,
        range_start::date, range_end::date
    FROM timescaledb_information.chunks
    WHERE hypertable_schema = 'historian_raw'
      AND hypertable_name   = 'historian_timeseries'
      AND is_compressed = false
    ORDER BY range_start;
""")
for r in cur.fetchall():
    cur2 = conn.cursor()
    cur2.execute(f'SELECT COUNT(*) FROM {r[0]}')
    cnt = cur2.fetchone()[0]
    print(f"  {r[1]} → {r[2]}  rows: {cnt:,}")
    cur2.close()

print()
print("WHY uncompressed is correct:")
print("  - Chunks < 7 days old stay uncompressed for fast INSERT + live trend queries")
print("  - 'Columnstore Policy' job runs every 12h — will compress them automatically")
print("  - Today is 2026-05-20 → 2026-05-07→14 chunk is 13 days old")
print("    → it should already be compressed by the policy job")
print()
print("Force compress the 2026-05-07→14 chunk NOW (it is past the 7-day threshold):")

cur.execute("""
    SELECT compress_chunk(c.chunk_schema || '.' || c.chunk_name)
    FROM timescaledb_information.chunks c
    WHERE c.hypertable_schema = 'historian_raw'
      AND c.hypertable_name   = 'historian_timeseries'
      AND c.is_compressed = false
      AND c.range_end < NOW() - INTERVAL '7 days';
""")
forced = cur.fetchall()
if forced:
    print(f"  Force-compressed: {forced}")
else:
    print("  No chunks past the 7-day threshold — nothing to force compress.")

# Final state
print("\nFinal chunk state:")
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

cur.close()
conn.close()
