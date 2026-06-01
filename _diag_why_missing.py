import urllib.request, json, psycopg2

PORT = 8090  # nginx/HMI port — try common ports
FLASK_PORT = 5000

print("=" * 70)
print("STEP 1 — DB: AY1101 in alarm_active?")
print("=" * 70)
conn = psycopg2.connect(host='localhost', port=5432, database='Automation_DB',
                        user='cereveate', password='cereveate@222')
cur = conn.cursor()
cur.execute("""
    SELECT tag_id, level, alarm_state, setpoint_value, raised_value, raised_at
    FROM historian_raw.alarm_active
    WHERE tag_id ILIKE '%AY1101%'
""")
db_rows = cur.fetchall()
print(f"DB rows: {len(db_rows)}")
for r in db_rows:
    print(f"  {r}")

print("\n" + "=" * 70)
print("STEP 2 — Flask API /api/alarms/active (try ports 5000, 5001, 8090)")
print("=" * 70)
for port in [5000, 5001, 8090]:
    try:
        req = urllib.request.Request(f'http://127.0.0.1:{port}/api/alarms/active')
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read().decode())
        alarms = data.get('alarms', [])
        ay = [a for a in alarms if 'AY1101' in str(a.get('tag_id', ''))]
        print(f"  Port {port}: SUCCESS — total alarms={len(alarms)}, AY1101={len(ay)}")
        for a in ay:
            print(f"    tag_id={a.get('tag_id')} state={a.get('alarm_state')} "
                  f"sp={a.get('alarm_setpoint')} pv={a.get('alarm_actual_value')}")
    except Exception as e:
        print(f"  Port {port}: FAIL — {e}")

print("\n" + "=" * 70)
print("STEP 3 — Is AY1101 suppressed?")
print("=" * 70)
cur.execute("""
    SELECT aat.alarm_key, aat.action_type, aat.performed_by, aat.action_timestamp
    FROM historian_raw.alarm_audit_trail aat
    WHERE aat.alarm_key ILIKE '%AY1101%'
      AND aat.action_type = 'SUPPRESSED'
    ORDER BY aat.action_timestamp DESC LIMIT 5
""")
rows = cur.fetchall()
print(f"Suppression records: {len(rows)}")
for r in rows:
    print(f"  {r}")

print("\n" + "=" * 70)
print("STEP 4 — alarm_active suppression check (the active API excludes suppressed)")
print("=" * 70)
cur.execute("""
    SELECT aa.tag_id, aa.alarm_key, aa.alarm_state
    FROM historian_raw.alarm_active aa
    WHERE aa.tag_id ILIKE '%AY1101%'
      AND EXISTS (
          SELECT 1 FROM historian_raw.alarm_audit_trail sup
          WHERE sup.metadata->>'alarm_key' = aa.alarm_key
            AND sup.action_type = 'SUPPRESSED'
            AND NOT EXISTS (
                SELECT 1 FROM historian_raw.alarm_audit_trail unsup
                WHERE unsup.metadata->>'alarm_key' = aa.alarm_key
                  AND unsup.action_type = 'UNSUPPRESSED'
                  AND unsup.action_timestamp > sup.action_timestamp
            )
      )
""")
rows = cur.fetchall()
print(f"AY1101 suppressed rows: {len(rows)}")
for r in rows:
    print(f"  {r}")

cur.close()
conn.close()
print("\n" + "=" * 70)
print("DONE")
