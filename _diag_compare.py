import urllib.request, json, psycopg2

TARGETS = ['AY1101', 'PDY1104']

# --- 1. PLC pool ---
with urllib.request.urlopen('http://127.0.0.1:5001/api/plc/values', timeout=3) as r:
    data = json.loads(r.read().decode())
raw = data.get('values') or data.get('tags') or []
if isinstance(raw, dict):
    raw = list(raw.values())

pool = {}
for row in raw:
    nm = row.get('tagName') or row.get('address')
    if nm in TARGETS:
        pool[nm] = row

print("===== PLC POOL =====")
for t in TARGETS:
    if t in pool:
        print(f"{t}: keys={list(pool[t].keys())}")
        print(f"      {json.dumps(pool[t])}")
    else:
        print(f"{t}: NOT IN POOL")

# --- 2. DB tag_master + latest_value ---
conn = psycopg2.connect(host='localhost', port=5432, database='Automation_DB',
                        user='cereveate', password='cereveate@222')
cur = conn.cursor()
print("\n===== TAG MASTER + LATEST VALUE =====")
for t in TARGETS:
    cur.execute("""
        SELECT t.tag_id, t.tag_name, t.enabled,
               lv.last_value_num, lv.last_quality, lv.last_time
        FROM historian_meta.tag_master t
        LEFT JOIN historian_raw.historian_latest_value lv ON lv.tag_id = t.tag_id
        WHERE t.tag_id::text = %s OR t.tag_name = %s
    """, (t, t))
    rows = cur.fetchall()
    print(f"{t}: {rows if rows else 'NOT IN tag_master'}")

cur.close(); conn.close()
