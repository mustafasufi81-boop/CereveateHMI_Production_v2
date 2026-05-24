"""
Phase 1 - Step 1: Drop duplicate index uq_timeseries_time_tag
Saves 661 MB instantly. The PK still enforces uniqueness — this index is redundant.
"""
import psycopg2
import psycopg2.extras

conn = psycopg2.connect(
    host='localhost', port=5432,
    dbname='Automation_DB',
    user='cereveate', password='cereveate@222'
)
conn.autocommit = True
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# ── BEFORE ──────────────────────────────────────────────────────────────────
print("=" * 60)
print("BEFORE: Indexes on historian_timeseries")
print("=" * 60)
cur.execute("""
    SELECT
        indexrelname AS indexname,
        pg_size_pretty(pg_relation_size(indexrelid)) AS size
    FROM pg_stat_user_indexes
    WHERE relname = 'historian_timeseries'
    ORDER BY pg_relation_size(indexrelid) DESC;
""")
rows = cur.fetchall()
for r in rows:
    print(f"  {r['indexname']:50s}  {r['size']}")

cur.execute("""
    SELECT pg_size_pretty(pg_total_relation_size('historian_raw.historian_timeseries')) AS total;
""")
total_before = cur.fetchone()['total']
print(f"\n  Total table size BEFORE: {total_before}")

# ── CHECK duplicate index exists ─────────────────────────────────────────────
cur.execute("""
    SELECT indexname FROM pg_indexes
    WHERE schemaname = 'historian_raw'
      AND tablename  = 'historian_timeseries'
      AND indexname  = 'uq_timeseries_time_tag';
""")
exists = cur.fetchone()

if not exists:
    print("\n⚠️  Index 'uq_timeseries_time_tag' does NOT exist — nothing to drop.")
else:
    print("\n✅ Duplicate index found. Dropping as constraint...")
    # It is a UNIQUE CONSTRAINT (not a bare index) — must drop via ALTER TABLE
    cur.execute("""
        ALTER TABLE historian_raw.historian_timeseries
        DROP CONSTRAINT IF EXISTS uq_timeseries_time_tag;
    """)
    print("   DROP INDEX executed.")

    # ── AFTER ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("AFTER: Indexes on historian_timeseries")
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
        print(f"  {r['indexname']:50s}  {r['size']}")

    cur.execute("""
        SELECT pg_size_pretty(pg_total_relation_size('historian_raw.historian_timeseries')) AS total;
    """)
    total_after = cur.fetchone()['total']
    print(f"\n  Total table size AFTER:  {total_after}")
    print(f"\n✅ Done. Disk freed = {total_before} → {total_after}")

cur.close()
conn.close()
