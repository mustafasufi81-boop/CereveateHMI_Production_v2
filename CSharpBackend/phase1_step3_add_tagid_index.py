"""
Phase 1 - Step 3: Add (tag_id, time DESC) index for tag-based range queries.
Runs CONCURRENTLY — zero downtime, builds in background.
This fixes queries like: WHERE tag_id = 'X' AND time BETWEEN a AND b
which currently do a full 15M-row table scan.
"""
import psycopg2
import psycopg2.extras
import time

conn = psycopg2.connect(
    host='localhost', port=5432,
    dbname='Automation_DB',
    user='cereveate', password='cereveate@222'
)
conn.autocommit = True
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# ── Check if index already exists ────────────────────────────────────────────
cur.execute("""
    SELECT indexname FROM pg_indexes
    WHERE schemaname = 'historian_raw'
      AND tablename  = 'historian_timeseries'
      AND indexname  = 'idx_historian_ts_tagid_time';
""")
exists = cur.fetchone()

if exists:
    print("⚠️  Index 'idx_historian_ts_tagid_time' already exists — skipping.")
else:
    print("=" * 60)
    print("Phase 1 Step 3: Creating (tag_id, time DESC) index")
    print("Running CONCURRENTLY — this may take 1-3 minutes on 15M rows")
    print("Writes are NOT blocked during this.")
    print("=" * 60)

    t0 = time.time()
    cur.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_historian_ts_tagid_time
        ON historian_raw.historian_timeseries (tag_id, "time" DESC);
    """)
    elapsed = time.time() - t0
    print(f"\n✅ Index created in {elapsed:.1f} seconds.")

# ── Show final index list ─────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("Current indexes on historian_timeseries:")
print("=" * 60)
cur.execute("""
    SELECT
        indexrelname AS indexname,
        pg_size_pretty(pg_relation_size(indexrelid)) AS size
    FROM pg_stat_user_indexes
    WHERE relname = 'historian_timeseries'
    ORDER BY pg_relation_size(indexrelid) DESC;
""")
for r in cur.fetchall():
    print(f"  {r['indexname']:55s}  {r['size']}")

cur.execute("""
    SELECT pg_size_pretty(pg_total_relation_size('historian_raw.historian_timeseries')) AS total;
""")
print(f"\n  Total table size: {cur.fetchone()['total']}")

print("\n✅ Phase 1 Step 3 complete.")
cur.close()
conn.close()
