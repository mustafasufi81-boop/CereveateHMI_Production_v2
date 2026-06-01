import psycopg2, urllib.request, json, math

conn = psycopg2.connect(host='localhost', port=5432, database='Automation_DB',
                        user='cereveate', password='cereveate@222')
cur = conn.cursor()
cur.execute("""
    SELECT t.tag_id, t.tag_name, lv.last_value_num, lv.last_value_bool, lv.last_value_text
    FROM historian_meta.tag_master t
    LEFT JOIN historian_raw.historian_latest_value lv ON lv.tag_id = t.tag_id
    WHERE t.enabled = true AND (t.tag_name ILIKE '%AY1101%' OR t.tag_id::text ILIKE '%AY1101%')
""")
tags = {}
name_to_id = {}
for tag_id, tag_name, num, b, txt in cur.fetchall():
    raw = num if num is not None else (b if b is not None else txt)
    tags[tag_id] = {'value': float(raw) if isinstance(raw, (int, float)) else raw}
    name_to_id[str(tag_id).upper()] = tag_id
    if tag_name:
        name_to_id[str(tag_name).upper()] = tag_id
print("DB tags (pre-overlay):", tags)

with urllib.request.urlopen('http://127.0.0.1:5001/api/plc/values', timeout=3) as r:
    data = json.loads(r.read().decode())
raw = data.get('values') or data.get('tags') or []
if isinstance(raw, dict):
    raw = list(raw.values())

def coerce(v):
    try:
        n = float(v)
        return n if math.isfinite(n) else None
    except Exception:
        return None

for lv in raw:
    cand = lv.get('tagId') or lv.get('tag_id') or lv.get('tagName') or lv.get('address')
    tid = None
    if cand is not None:
        tid = cand if cand in tags else name_to_id.get(str(cand).upper())
    if tid is None or tid not in tags:
        continue
    tags[tid] = {'value': coerce(lv.get('value'))}
    print(f"OVERLAID {tid} = {tags[tid]}")

print("FINAL tags['AY1101']:", tags.get('AY1101'))
cur.close(); conn.close()
