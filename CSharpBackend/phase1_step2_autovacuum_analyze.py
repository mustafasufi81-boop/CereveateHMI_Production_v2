"""
Phase 1 - Step 2: Fix autovacuum settings + force ANALYZE
No restart needed. Takes effect immediately on the per-table storage settings.
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

# ── BEFORE ───────────────────────────────────────────────────────────────────
print("=" * 60)
print("BEFORE: autovacuum state of historian_timeseries")
print("=" * 60)
cur.execute("""
    SELECT
        n_live_tup,
        n_dead_tup,
        n_mod_since_analyze,
        last_autovacuum,
        last_autoanalyze,
        last_analyze
    FROM pg_stat_user_tables
    WHERE relname = 'historian_timeseries';
""")
before = cur.fetchone()
print(f"  Live tuples:            {before['n_live_tup']:,}")
print(f"  Dead tuples:            {before['n_dead_tup']:,}")
print(f"  Modified since analyze: {before['n_mod_since_analyze']:,}")
print(f"  Last autovacuum:        {before['last_autovacuum']}")
print(f"  Last autoanalyze:       {before['last_autoanalyze']}")
print(f"  Last manual analyze:    {before['last_analyze']}")

# ── APPLY per-table autovacuum overrides ─────────────────────────────────────
print("\n⚙️  Applying per-table autovacuum overrides...")
cur.execute("""
    ALTER TABLE historian_raw.historian_timeseries
    SET (
        autovacuum_vacuum_scale_factor    = 0.01,
        autovacuum_analyze_scale_factor   = 0.005,
        autovacuum_vacuum_cost_delay      = 2,
        toast.autovacuum_vacuum_scale_factor = 0.01
    );
""")
print("   ALTER TABLE SET (...) done.")

# ── FORCE immediate ANALYZE to fix stale planner statistics ──────────────────
print("\n⚙️  Running ANALYZE (fixes stale query planner statistics)...")
cur.execute("ANALYZE VERBOSE historian_raw.historian_timeseries;")
print("   ANALYZE complete.")

# ── AFTER ────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("AFTER: autovacuum state of historian_timeseries")
print("=" * 60)
cur.execute("""
    SELECT
        n_live_tup,
        n_dead_tup,
        n_mod_since_analyze,
        last_autovacuum,
        last_autoanalyze,
        last_analyze
    FROM pg_stat_user_tables
    WHERE relname = 'historian_timeseries';
""")
after = cur.fetchone()
print(f"  Live tuples:            {after['n_live_tup']:,}")
print(f"  Dead tuples:            {after['n_dead_tup']:,}")
print(f"  Modified since analyze: {after['n_mod_since_analyze']:,}")
print(f"  Last autovacuum:        {after['last_autovacuum']}")
print(f"  Last autoanalyze:       {after['last_autoanalyze']}")
print(f"  Last manual analyze:    {after['last_analyze']}")

# ── Verify per-table settings were saved ────────────────────────────────────
print("\n" + "=" * 60)
print("Per-table storage settings (confirmed saved in pg_class):")
print("=" * 60)
cur.execute("""
    SELECT reloptions
    FROM pg_class
    WHERE relname = 'historian_timeseries'
      AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'historian_raw');
""")
opts = cur.fetchone()
print(f"  reloptions: {opts['reloptions']}")

print("\n✅ Phase 1 Step 2 complete.")
cur.close()
conn.close()
