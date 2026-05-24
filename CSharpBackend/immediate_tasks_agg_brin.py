"""
Immediate Task 1: Create TimescaleDB continuous aggregate (ts_hourly_agg)
Immediate Task 2: Create BRIN index on time

Both zero-downtime. Runs while OPC backend is writing.
"""
import psycopg2
import time

conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
conn.autocommit = True
cur = conn.cursor()

# ═══════════════════════════════════════════════════════════════════
# TASK 1: Hourly continuous aggregate
# ═══════════════════════════════════════════════════════════════════
print("=" * 65)
print("TASK 1: Creating ts_hourly_agg continuous aggregate")
print("=" * 65)

# Check if already exists
cur.execute("""
    SELECT view_name FROM timescaledb_information.continuous_aggregates
    WHERE view_schema = 'historian_raw' AND view_name = 'ts_hourly_agg';
""")
if cur.fetchone():
    print("⚠️  ts_hourly_agg already exists — skipping CREATE.")
else:
    print("Creating continuous aggregate (WITH NO DATA — fast, fills in background)...")
    t0 = time.time()
    cur.execute("""
        CREATE MATERIALIZED VIEW historian_raw.ts_hourly_agg
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('1 hour', "time") AS bucket,
            tag_id,
            AVG(value_num)              AS avg_val,
            MAX(value_num)              AS max_val,
            MIN(value_num)              AS min_val,
            COUNT(*)                    AS sample_count,
            LAST(value_num, "time")     AS last_val,
            FIRST(value_num, "time")    AS first_val
        FROM historian_raw.historian_timeseries
        GROUP BY bucket, tag_id
        WITH NO DATA;
    """)
    print(f"   View created in {time.time()-t0:.1f}s")

    print("Adding auto-refresh policy (every 1 hour, covers last 3 hours)...")
    cur.execute("""
        SELECT add_continuous_aggregate_policy(
            'historian_raw.ts_hourly_agg',
            start_offset      => INTERVAL '3 hours',
            end_offset        => INTERVAL '1 hour',
            schedule_interval => INTERVAL '1 hour',
            if_not_exists     => true
        );
    """)
    print("   Refresh policy added.")

    print("Triggering initial backfill for last 90 days (runs in background)...")
    cur.execute("""
        CALL refresh_continuous_aggregate(
            'historian_raw.ts_hourly_agg',
            NOW() - INTERVAL '90 days',
            NOW() - INTERVAL '1 hour'
        );
    """)
    print(f"   Backfill complete in {time.time()-t0:.1f}s")

# Verify
cur.execute("""
    SELECT view_name, materialization_hypertable_schema || '.' ||
           materialization_hypertable_name AS mat_table
    FROM timescaledb_information.continuous_aggregates
    WHERE view_schema = 'historian_raw' AND view_name = 'ts_hourly_agg';
""")
r = cur.fetchone()
print(f"\n✅ ts_hourly_agg → materialized in: {r[1]}")

cur.execute("SELECT COUNT(*) FROM historian_raw.ts_hourly_agg;")
print(f"   Rows in aggregate: {cur.fetchone()[0]:,}")

# ═══════════════════════════════════════════════════════════════════
# TASK 2: BRIN index on time
# ═══════════════════════════════════════════════════════════════════
print()
print("=" * 65)
print("TASK 2: Creating BRIN index on time")
print("=" * 65)

cur.execute("""
    SELECT indexname FROM pg_indexes
    WHERE schemaname = 'historian_raw'
      AND tablename  = 'historian_timeseries'
      AND indexname  = 'idx_historian_ts_time_brin';
""")
if cur.fetchone():
    print("⚠️  BRIN index already exists — skipping.")
else:
    print("Creating BRIN index on time (brief lock, seconds only on hypertable)...")
    t0 = time.time()
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_historian_ts_time_brin
        ON historian_raw.historian_timeseries
        USING BRIN ("time")
        WITH (pages_per_range = 128);
    """)
    print(f"   BRIN index created in {time.time()-t0:.1f}s")

# ═══════════════════════════════════════════════════════════════════
# FINAL: Show all indexes + aggregate policy summary
# ═══════════════════════════════════════════════════════════════════
print()
print("=" * 65)
print("FINAL STATE — Indexes on historian_timeseries")
print("=" * 65)
cur.execute("""
    SELECT indexrelname, pg_size_pretty(pg_relation_size(indexrelid)) AS size,
           am.amname AS type
    FROM pg_stat_user_indexes si
    JOIN pg_class ic ON ic.oid = si.indexrelid
    JOIN pg_am am ON am.oid = ic.relam
    WHERE si.relname = 'historian_timeseries'
    ORDER BY pg_relation_size(si.indexrelid) DESC;
""")
for r in cur.fetchall():
    print(f"  {r[0]:<45}  {r[2]:>6}   {r[1]}")

print()
print("Background jobs:")
cur.execute("""
    SELECT application_name, schedule_interval, next_start::timestamptz(0)
    FROM timescaledb_information.jobs
    WHERE hypertable_schema = 'historian_raw'
       OR application_name ILIKE '%hourly%'
    ORDER BY application_name;
""")
for r in cur.fetchall():
    print(f"  {r[0]:<45}  every {r[1]}  next: {r[2]}")

cur.close()
conn.close()
print("\n✅ Both tasks complete.")
