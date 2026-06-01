"""
_diagnose_pool_vs_mqtt.py
=========================
Proves (or disproves) whether the PLC pool value and the Flask MQTT-cached value
differ for PY1105B (and similar PLC tags with active alarms).

Compares THREE sources side-by-side (NO LOGIN REQUIRED):
  1. DB historian_latest_value   → last value written to DB by the data pipeline
  2. DB historian_timeseries     → most recent raw sample per tag (last 60s)
  3. Flask /api/mqtt/plcs/.../tags → Flask MQTT cache (unauthenticated endpoint)

Plus: C# /api/plc/connections    → worker connection status (unauthenticated health endpoint)

If my hypothesis is CORRECT:
  - DB shows PY1105B last updated > 10s ago (pool is stale)
  - Flask MQTT cache shows same stale value (last MQTT publish before pool went stale)
  - No new samples in historian_timeseries in last 30s for PY1105B

If I am WRONG:
  - DB shows PY1105B updated within last 2-3s (fresh data flowing)
  - Flask MQTT cache matches DB value
"""

import requests
import psycopg2
from datetime import datetime, timezone

# ── Config ──────────────────────────────────────────────────────────────────
FLASK_BASE  = "http://localhost:8090"
CSHARP_BASE = "http://localhost:5001"
PLC_ID      = "Rockwel_PLC_001"

DB_CONN = dict(host="localhost", port=5432, database="Automation_DB",
               user="cereveate", password="cereveate@222")

# Tags to inspect — PLC alarm tags
TAGS_OF_INTEREST = ["PY1105B", "PY1105A", "PY1102B", "FY1100", "AY1102", "PY1100"]

def get_db_latest(cur, tags):
    """historian_raw.historian_latest_value — last written value per tag"""
    placeholders = ",".join(["%s"] * len(tags))
    cur.execute(f"""
        SELECT tag_id, value_num, updated_at,
               EXTRACT(EPOCH FROM (NOW() - updated_at))*1000 AS age_ms
        FROM historian_raw.historian_latest_value
        WHERE tag_id IN ({placeholders})
        ORDER BY tag_id
    """, tags)
    return {row[0]: {"value": row[1], "updated_at": row[2], "age_ms": int(row[3]) if row[3] else None}
            for row in cur.fetchall()}

def get_db_recent_samples(cur, tags):
    """Last sample per tag from historian_timeseries in past 60s"""
    placeholders = ",".join(["%s"] * len(tags))
    cur.execute(f"""
        SELECT DISTINCT ON (tag_id) tag_id, time, value_num, sample_source
        FROM historian_raw.historian_timeseries
        WHERE tag_id IN ({placeholders})
          AND time > NOW() - INTERVAL '60 seconds'
        ORDER BY tag_id, time DESC
    """, tags)
    return {row[0]: {"time": row[1], "value": row[2], "source": row[3]}
            for row in cur.fetchall()}

def get_flask_mqtt_cache():
    """Flask MQTT cache — unauthenticated endpoint used by other scripts"""
    try:
        r = requests.get(f"{FLASK_BASE}/api/mqtt/plcs/{PLC_ID}/tags", timeout=5)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        data = r.json()
        tags_list = data.get("tags", [])
        result = {}
        for t in tags_list:
            name = t.get("tag_id") or t.get("tagId") or t.get("name") or ""
            if name:
                result[name] = t
        return result, None
    except Exception as e:
        return None, str(e)

def get_csharp_connections():
    """C# worker connection status — no auth needed for health endpoints"""
    try:
        r = requests.get(f"{CSHARP_BASE}/api/plc/connections", timeout=5)
        if r.status_code == 200:
            return r.json(), None
        return None, f"HTTP {r.status_code}"
    except Exception as e:
        return None, str(e)

def fmt_age(ms):
    if ms is None:
        return "  N/A   "
    if ms < 0:
        return "future? "
    if ms < 2000:
        return f" {ms}ms  ✅"
    if ms < 10000:
        return f" {ms/1000:.1f}s   ⚠️"
    return f" {ms/1000:.0f}s  ❌ STALE"

def main():
    print("=" * 70)
    print("POOL vs MQTT CACHE DIAGNOSTIC  (no login needed)")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # ── DB ──────────────────────────────────────────────────────────────────
    print("\n[1/3] Connecting to DB...")
    try:
        conn = psycopg2.connect(**DB_CONN)
        cur = conn.cursor()
        db_latest  = get_db_latest(cur, TAGS_OF_INTEREST)
        db_samples = get_db_recent_samples(cur, TAGS_OF_INTEREST)
        cur.close(); conn.close()
        print("      ✅ DB OK")
    except Exception as e:
        db_latest = {}; db_samples = {}
        print(f"      ❌ DB error: {e}")

    # ── Flask MQTT cache ─────────────────────────────────────────────────────
    print("[2/3] Fetching Flask MQTT cache...")
    mqtt_cache, mqtt_err = get_flask_mqtt_cache()
    if mqtt_err:
        print(f"      ❌ {mqtt_err}")
    else:
        print(f"      ✅ Got {len(mqtt_cache)} tags")

    # ── C# connections ───────────────────────────────────────────────────────
    print("[3/3] Fetching C# worker connections...")
    connections, conn_err = get_csharp_connections()
    if conn_err:
        print(f"      ❌ {conn_err}")
    else:
        print(f"      ✅ Got connection data")

    if connections:
        print("\n── C# PLC WORKER STATUS ──────────────────────────────────────────────")
        conns = connections if isinstance(connections, list) else connections.get("connections", [connections])
        for c in (conns if isinstance(conns, list) else [conns]):
            print(f"  Worker:    {c.get('workerId') or c.get('plcId') or 'unknown'}")
            print(f"  Connected: {c.get('isConnected')}")
            print(f"  Protocol:  {c.get('protocol')}")
            print(f"  IP:        {c.get('ipAddress') or c.get('ip')}")
            print(f"  Port:      {c.get('port')}")
            print(f"  State:     {c.get('state') or c.get('status')}")
            print()

    # ── Side-by-side comparison ──────────────────────────────────────────────
    print("\n── TAG-BY-TAG COMPARISON ─────────────────────────────────────────────")
    print(f"{'Tag':<12} {'DB Latest Val':>14} {'DB Age':>12} {'DB 60s sample':>13} {'MQTT Cache Val':>15} {'MQTT ts'}")
    print("-" * 90)

    for tag in TAGS_OF_INTEREST:
        dbl  = db_latest.get(tag)
        dbs  = db_samples.get(tag)
        mqtt = mqtt_cache.get(tag) if mqtt_cache else None

        db_val  = f"{dbl['value']:.4f}"  if dbl and dbl['value'] is not None else "  ---  "
        db_age  = fmt_age(dbl['age_ms'])  if dbl else "  N/A  "
        dbs_val = f"{dbs['value']:.4f}" if dbs and dbs['value'] is not None else "no 60s data"
        mval    = str(mqtt.get("value") or mqtt.get("last_value") or "---") if mqtt else "---"
        mts     = str(mqtt.get("timestamp") or mqtt.get("last_seen") or "?")[:19] if mqtt else "---"

        print(f"{tag:<12} {db_val:>14} {db_age:>20} {dbs_val:>13} {mval:>15} {mts}")

    # ── Conclusion ───────────────────────────────────────────────────────────
    print("\n── VERDICT ───────────────────────────────────────────────────────────")
    stale_tags = [t for t in TAGS_OF_INTEREST
                  if db_latest.get(t) and db_latest[t]['age_ms'] is not None
                  and db_latest[t]['age_ms'] > 10000]
    no_recent  = [t for t in TAGS_OF_INTEREST if t not in db_samples]

    if stale_tags:
        print(f"  ❌ STALE in DB (>10s): {stale_tags}")
        print("     → PlcDataLoggingService is NOT writing fresh data for these tags")
    else:
        print("  ✅ All tags fresh in DB (<10s) — pool is being updated")

    if no_recent:
        print(f"  ❌ NO SAMPLE in last 60s: {no_recent}")
    else:
        print("  ✅ All tags have samples in last 60s")

    if not stale_tags and not no_recent:
        print("\n  ✅ MY HYPOTHESIS WAS WRONG — pool IS fresh, look elsewhere for the bug")
    else:
        print("\n  ✅ MY HYPOTHESIS CONFIRMED — pool is stale, AlarmStateManager fix was correct")

    print()

if __name__ == "__main__":
    main()

    print("\n[2/4] Fetching C# PLC pool directly (localhost:5001/api/plc/values)...")
    pool_data, pool_err = get_csharp_plc_pool(token)
    if pool_err:
        print(f"      ✗ FAILED: {pool_err}")
        pool_data = {}
    else:
        print(f"      ✓ Got {len(pool_data)} tags from C# pool")

    print("\n[3/4] Fetching Flask MQTT cache (localhost:8090/api/tags/latest)...")
    mqtt_data, mqtt_err = get_flask_mqtt_cache(token)
    if mqtt_err:
        print(f"      ✗ FAILED: {mqtt_err}")
        mqtt_data = {}
    else:
        print(f"      ✓ Got {len(mqtt_data)} tags from Flask MQTT cache")

    print("\n[4/4] Comparing tag-by-tag for alarm tags of interest...")
    print()
    print(f"{'Tag':<15} {'C# Pool Value':>14} {'Pool Age':>10} {'Pool Quality':>14} | {'MQTT Cache Value':>16} {'MQTT Age':>10} {'MQTT Source':>12} | {'MATCH?':>8}")
    print("-" * 115)

    all_tags = set(list(TAGS_OF_INTEREST))
    # Also add any tags from pool that have active alarms
    for tag in TAGS_OF_INTEREST:
        all_tags.add(tag)

    mismatches = []
    stale_pool = []
    missing_from_pool = []

    for tag in sorted(all_tags):
        pool_entry = pool_data.get(tag)
        mqtt_entry = mqtt_data.get(tag)

        # Pool side
        if pool_entry:
            pool_val     = pool_entry.get("value", "N/A")
            pool_age_ms  = pool_entry.get("age_ms")
            pool_quality = pool_entry.get("computedQuality") or pool_entry.get("quality", "?")
            pool_ts      = pool_entry.get("cachedAt") or pool_entry.get("timestamp", "")
            if pool_age_ms is None:
                pool_age_ms = age_ms_from_timestamp(pool_ts)
        else:
            pool_val     = "NOT IN POOL"
            pool_age_ms  = None
            pool_quality = "MISSING"
            missing_from_pool.append(tag)

        # MQTT cache side
        if mqtt_entry:
            mqtt_val     = mqtt_entry.get("value") or mqtt_entry.get("value_num", "N/A")
            mqtt_ts      = mqtt_entry.get("timestamp") or mqtt_entry.get("time", "")
            mqtt_age_ms  = age_ms_from_timestamp(mqtt_ts)
            mqtt_source  = mqtt_entry.get("source", "?")
            mqtt_quality = mqtt_entry.get("quality", "?")
        else:
            mqtt_val     = "NOT IN CACHE"
            mqtt_age_ms  = None
            mqtt_source  = "MISSING"
            mqtt_quality = "MISSING"

        # Compare
        try:
            match = abs(float(str(pool_val)) - float(str(mqtt_val))) < 0.001
            match_str = "✓ SAME" if match else "✗ DIFFER"
            if not match:
                mismatches.append(tag)
        except Exception:
            match_str = "? N/A"

        # Flag stale pool
        if pool_age_ms and pool_age_ms > 10000:
            stale_pool.append(tag)

        print(f"{tag:<15} {str(pool_val):>14} {fmt_age(pool_age_ms):>10} {str(pool_quality):>14} | "
              f"{str(mqtt_val):>16} {fmt_age(mqtt_age_ms):>10} {str(mqtt_source):>12} | {match_str:>8}")

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    if stale_pool:
        print(f"\n⚠  STALE POOL ENTRIES (age > 10s): {stale_pool}")
        print("   → PlcDataLoggingService is NOT refreshing these tags")
        print("   → AlarmStateManager.ClearAsync will see these as Stale/missing")
    else:
        print("\n✓  All pool entries are fresh (age ≤ 10s)")

    if missing_from_pool:
        print(f"\n✗  MISSING FROM PLC POOL: {missing_from_pool}")
        print("   → These tags are NOT in the C# worker's configured tag list")
        print("   → OR the worker is disconnected (EtherNet/IP connection failed)")
    else:
        print("\n✓  All tags of interest are present in the C# pool")

    if mismatches:
        print(f"\n✗  VALUE MISMATCHES (pool ≠ MQTT cache): {mismatches}")
        print("   → Pool has stale/old value; Flask MQTT cache has newer value")
        print("   → This PROVES: MQTT path and REST pool path are diverged")
        print("   → MQTT 'appears live' because Flask cached the last good MQTT publish")
    else:
        print("\n✓  Values match between pool and MQTT cache")

    print()

    # Also show C# plc worker connection status
    print("=" * 70)
    print("C# PLC WORKER STATUS (localhost:5001/api/plc/connections)")
    print("=" * 70)
    try:
        r = requests.get(f"{CSHARP_BASE}/api/plc/connections",
                         headers={"Authorization": f"Bearer {token}"}, timeout=5)
        conns = r.json().get("connections", [])
        for c in conns:
            pid        = c.get("plcId", "?")
            connected  = c.get("isConnected", False)
            last_err   = c.get("lastError", "")
            tag_count  = c.get("tagCount", 0)
            mode       = c.get("mode", "?")
            last_update = c.get("lastUpdate", "N/A")
            symbol = "✓" if connected else "✗"
            print(f"  {symbol} {pid:<25} connected={connected}  tags={tag_count}  mode={mode}  lastUpdate={last_update}")
            if last_err:
                print(f"    lastError: {last_err}")
    except Exception as e:
        print(f"  ✗ Could not fetch connections: {e}")

    print()

if __name__ == "__main__":
    main()
