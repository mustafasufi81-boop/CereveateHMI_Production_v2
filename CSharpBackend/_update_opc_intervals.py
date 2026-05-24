### OVERWRITTEN — set deadband impossibly high for interval-only test
import psycopg2, json, re

cfg = json.load(open('appsettings.json'))
cs = cfg['Historian']['Database']['ConnectionString']
m = re.findall(r'Host=([^;]+);Port=([^;]+);Database=([^;]+);Username=([^;]+);Password=([^;]+)', cs, re.I)
h, p, db, u, pw = m[0]
conn = psycopg2.connect(host=h, port=p, dbname=db, user=u, password=pw)
cur = conn.cursor()

# ── STEP 1: Random.* and Triangle Waves.* → 5 min interval, no deadband ─────
# Bucket Brigade skipped — always 0 value, not useful for historian logging
cur.execute("""
    UPDATE historian_meta.tag_master
    SET db_logging_interval_ms = 300000,
        deadband_enabled       = false,
        deadband_value         = NULL,
        config_updated_at      = now()
    WHERE tag_id LIKE 'Random.%%'
       OR tag_id LIKE 'Triangle Waves.%%'
""")
print(f"[1] Random.* + Triangle Waves.* updated to 5-min interval, deadband OFF: {cur.rowcount} rows")

# ── STEP 2: Random.Real4 → 30s interval + deadband derived from real data ────
# Historical: range=26777, stddev=6173 → 5% of range = 1339 (too wide)
# Use 1x stddev = 6173 → tag writes only when value changes by >6173 before 30s,
# OR unconditionally every 30s (heartbeat). Meaningful for a wide-range random tag.
cur.execute("""
    UPDATE historian_meta.tag_master
    SET db_logging_interval_ms = 30000,
        deadband_enabled       = true,
        deadband_value         = 1339.0,
        config_updated_at      = now()
    WHERE tag_id = 'Random.Real4'
""")
print(f"[2] Random.Real4 → 30s interval + deadband=1339.0 (5% of range 26777): {cur.rowcount} rows")

# ── STEP 3: Triangle Waves.Real4 → 60s interval + deadband from real data ────
# Historical: range=524.92, stddev=42.53 → 5% of range = 26.25
# Deadband=26.25: spike fires if wave moves >26 units before 60s expires
cur.execute("""
    UPDATE historian_meta.tag_master
    SET db_logging_interval_ms = 60000,
        deadband_enabled       = true,
        deadband_value         = 26.25,
        config_updated_at      = now()
    WHERE tag_id = 'Triangle Waves.Real4'
""")
print(f"[3] Triangle Waves.Real4 → 60s interval + deadband=26.25 (5% of range 524.92): {cur.rowcount} rows")

conn.commit()

# ── VERIFY ───────────────────────────────────────────────────────────────────
cur.execute("""
    SELECT tag_id, db_logging_interval_ms, deadband_enabled, deadband_value
    FROM historian_meta.tag_master
    WHERE tag_id LIKE 'Random.%%'
       OR tag_id LIKE 'Triangle Waves.%%'
    ORDER BY tag_id
""")
rows = cur.fetchall()
print()
print(f"{'TAG_ID':<35} {'INTERVAL_MS':>12}  {'DEADBAND':>10}  {'DB_VALUE':>10}")
print("-" * 72)
for r in rows:
    print(f"{r[0]:<35} {r[1]:>12}  {str(r[2]):>10}  {str(r[3]):>10}")

conn.close()
print("\nDone. MappingCacheService will auto-refresh within 30s.")
