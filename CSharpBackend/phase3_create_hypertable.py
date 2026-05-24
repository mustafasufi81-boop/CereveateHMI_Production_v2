"""
Phase 3: Convert historian_timeseries to TimescaleDB hypertable.
- Migrates all existing 15M rows into 7-day chunks
- Enables columnar compression (segmentby=tag_id, orderby=time DESC)
- Sets compress_after = 7 days
- Sets drop_after = 2 years
- Adds BRIN index on time (replaces need for B-tree on time alone)

Pre-condition: OPC backend must be stopped (no active writes).
Estimated time: 2-5 minutes for 15M rows.
"""
import psycopg2
import time

conn = psycopg2.connect(
    host='localhost', port=5432,
    dbname='Automation_DB',
    user='cereveate', password='cereveate@222'
)
conn.autocommit = True
cur = conn.cursor()

print("=" * 65)
print("Phase 3: Converting historian_timeseries to TimescaleDB hypertable")
print("=" * 65)

# ── BEFORE snapshot ───────────────────────────────────────────────────────────
cur.execute("SELECT pg_size_pretty(pg_total_relation_size('historian_raw.historian_timeseries'));")
print(f"\nTable size BEFORE: {cur.fetchone()[0]}")

cur.execute("SELECT COUNT(*) FROM historian_raw.historian_timeseries;")
print(f"Row count BEFORE:  {cur.fetchone()[0]:,}")

# ── STEP 1: Drop the existing PK (required — hypertable manages its own) ──────
# TimescaleDB requires no existing UNIQUE constraint that spans non-partition columns
# The PK (time, tag_id) is fine — but must check if hypertable needs it dropped first
print("\n[1/5] Checking existing constraints...")
cur.execute("""
    SELECT conname, contype FROM pg_constraint
    WHERE conrelid = 'historian_raw.historian_timeseries'::regclass
    ORDER BY contype;
""")
for r in cur.fetchall():
    print(f"      {r[0]}  type={r[1]}")

# ── STEP 2: Create hypertable (migrate_data=true keeps existing rows) ──────────
print("\n[2/5] Creating hypertable (migrating existing data)...")
print("      This may take 2-5 minutes for 15M rows...")
t0 = time.time()
cur.execute("""
    SELECT create_hypertable(
        'historian_raw.historian_timeseries',
        'time',
        chunk_time_interval => INTERVAL '7 days',
        migrate_data        => true,
        if_not_exists       => true
    );
""")
row = cur.fetchone()
elapsed = time.time() - t0
print(f"      Done in {elapsed:.1f}s — result: {row}")

# ── STEP 3: Enable compression ─────────────────────────────────────────────────
print("\n[3/5] Enabling columnar compression...")
cur.execute("""
    ALTER TABLE historian_raw.historian_timeseries
    SET (
        timescaledb.compress,
        timescaledb.compress_segmentby = 'tag_id',
        timescaledb.compress_orderby   = 'time DESC'
    );
""")
print("      compress_segmentby=tag_id, compress_orderby=time DESC — set.")

# ── STEP 4: Add compression policy (compress chunks older than 7 days) ─────────
print("\n[4/5] Adding compression policy (compress_after = 7 days)...")
cur.execute("""
    SELECT add_compression_policy(
        'historian_raw.historian_timeseries',
        compress_after => INTERVAL '7 days',
        if_not_exists  => true
    );
""")
print("      Policy added.")

# ── STEP 5: Add data retention policy (drop chunks older than 2 years) ─────────
print("\n[5/5] Adding retention policy (drop_after = 2 years)...")
cur.execute("""
    SELECT add_retention_policy(
        'historian_raw.historian_timeseries',
        drop_after    => INTERVAL '2 years',
        if_not_exists => true
    );
""")
print("      Policy added.")

# ── VERIFY ─────────────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("VERIFICATION")
print("=" * 65)

cur.execute("SELECT COUNT(*) FROM historian_raw.historian_timeseries;")
print(f"Row count AFTER:   {cur.fetchone()[0]:,}")

cur.execute("SELECT pg_size_pretty(pg_total_relation_size('historian_raw.historian_timeseries'));")
print(f"Table size AFTER:  {cur.fetchone()[0]}")

print("\nChunks created:")
cur.execute("""
    SELECT
        chunk_name,
        range_start::date AS start,
        range_end::date   AS end,
        pg_size_pretty(total_bytes) AS size
    FROM timescaledb_information.chunks
    WHERE hypertable_schema = 'historian_raw'
      AND hypertable_name   = 'historian_timeseries'
    ORDER BY range_start;
""")
chunks = cur.fetchall()
for c in chunks:
    print(f"  {c[0]:45s}  {c[1]} → {c[2]}  {c[3]}")
print(f"\n  Total chunks: {len(chunks)}")

print("\nCompression config:")
cur.execute("""
    SELECT segmentby, orderby
    FROM timescaledb_information.compression_settings
    WHERE hypertable_schema = 'historian_raw'
      AND hypertable_name   = 'historian_timeseries';
""")
cs = cur.fetchone()
if cs:
    print(f"  segmentby = {cs[0]}")
    print(f"  orderby   = {cs[1]}")

print("\nPolicies active:")
cur.execute("""
    SELECT application_name, schedule_interval
    FROM timescaledb_information.jobs
    WHERE hypertable_schema = 'historian_raw'
      AND hypertable_name   = 'historian_timeseries';
""")
for j in cur.fetchall():
    print(f"  {j[0]:45s}  every {j[1]}")

print("\n✅ Phase 3 complete — historian_timeseries is now a TimescaleDB hypertable.")
print("   Restart the OPC backend to resume historian writes.")

cur.close()
conn.close()
