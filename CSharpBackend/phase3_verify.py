import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
conn.autocommit = True
cur = conn.cursor()

print("=" * 65)
print("Phase 3 — Final Verification")
print("=" * 65)

cur.execute("SELECT COUNT(*) FROM historian_raw.historian_timeseries;")
print(f"Row count:   {cur.fetchone()[0]:,}")

cur.execute("SELECT pg_size_pretty(pg_total_relation_size('historian_raw.historian_timeseries'));")
print(f"Total size:  {cur.fetchone()[0]}")

print("\nChunks (7-day slices):")
cur.execute("""
    SELECT
        chunk_schema || '.' || chunk_name AS chunk,
        range_start::date AS start,
        range_end::date   AS end,
        is_compressed
    FROM timescaledb_information.chunks
    WHERE hypertable_schema = 'historian_raw'
      AND hypertable_name   = 'historian_timeseries'
    ORDER BY range_start;
""")
chunks = cur.fetchall()
for c in chunks:
    comp = "COMPRESSED" if c[3] else "uncompressed"
    print(f"  {c[1]} → {c[2]}  [{comp}]")
print(f"\n  Total chunks: {len(chunks)}")

print("\nCompression settings:")
cur.execute("""
    SELECT attname, segmentby_column_index, orderby_column_index, orderby_asc, orderby_nullsfirst
    FROM timescaledb_information.compression_settings
    WHERE hypertable_schema = 'historian_raw'
      AND hypertable_name   = 'historian_timeseries'
    ORDER BY COALESCE(segmentby_column_index, orderby_column_index);
""")
rows = cur.fetchall()
for r in rows:
    role = f"segmentby[{r[1]}]" if r[1] is not None else f"orderby[{r[2]}] asc={r[3]}"
    print(f"  {r[0]:20s}  {role}")

print("\nBackground policies:")
cur.execute("""
    SELECT application_name, schedule_interval, next_start
    FROM timescaledb_information.jobs
    WHERE hypertable_schema = 'historian_raw'
      AND hypertable_name   = 'historian_timeseries';
""")
for j in cur.fetchall():
    print(f"  {j[0]:40s}  every {j[1]}  next: {j[2]}")

cur.close()
conn.close()
print("\n✅ Verification complete.")
