import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB', user='cereveate', password='cereveate@222')
cur = conn.cursor()

print("=" * 60)
print("Post-restart verification")
print("=" * 60)

for setting in ["shared_buffers", "work_mem", "max_wal_size", "checkpoint_completion_target", "shared_preload_libraries"]:
    cur.execute(f"SHOW {setting};")
    print(f"  {setting:40s}: {cur.fetchone()[0]}")

print()
cur.execute("SELECT extname, extversion FROM pg_extension WHERE extname = 'timescaledb';")
row = cur.fetchone()
if row:
    print(f"  TimescaleDB: ✅ ENABLED — version {row[1]}")
else:
    print("  TimescaleDB: ❌ NOT ENABLED — re-run phase2_enable_timescaledb.py")

cur.close()
conn.close()
print("\n✅ All checks passed — ready for Phase 3 (convert to hypertable)")
