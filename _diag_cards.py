import psycopg2, urllib.request, json, math

conn = psycopg2.connect(host='localhost', port=5432, database='Automation_DB',
                        user='cereveate', password='cereveate@222')
cur = conn.cursor()

# 1. All active alarm tags (these are the cards shown in the panel)
cur.execute("""
    SELECT aa.tag_id, aa.alarm_state, aa.setpoint_value, aa.raised_value
    FROM historian_raw.alarm_active aa
    WHERE aa.alarm_state IN ('ACTIVE_UNACK','ACTIVE_ACK','RTN_UNACK')
    ORDER BY aa.tag_id
""")
alarm_tags = cur.fetchall()
print(f"ACTIVE ALARM CARDS: {len(alarm_tags)}")

# 2. Build tags map exactly like /api/tags/latest (DB latest values)
cur.execute("""
    SELECT t.tag_id, t.tag_name, lv.last_value_num, lv.last_value_bool, lv.last_value_text
    FROM historian_meta.tag_master t
    LEFT JOIN historian_raw.historian_latest_value lv ON lv.tag_id = t.tag_id
    WHERE t.enabled = true
""")
tags = {}
name_to_id = {}
for tag_id, tag_name, num, b, txt in cur.fetchall():
    raw = num if num is not None else (b if b is not None else txt)
    tags[tag_id] = {'value': float(raw) if isinstance(raw, (int, float)) else raw}
    name_to_id[str(tag_id).upper()] = tag_id
    if tag_name:
        name_to_id[str(tag_name).upper()] = tag_id

# 3. Overlay live PLC pool (exactly like the route)
def coerce(v):
    try:
        n = float(v); return n if math.isfinite(n) else None
    except Exception:
        return None

with urllib.request.urlopen('http://127.0.0.1:5001/api/plc/values', timeout=3) as r:
    data = json.loads(r.read().decode())
raw = data.get('values') or data.get('tags') or []
if isinstance(raw, dict):
    raw = list(raw.values())

pool_by_name = {}
for lv in raw:
    cand = lv.get('tagId') or lv.get('tag_id') or lv.get('tagName') or lv.get('address')
    tid = None
    if cand is not None:
        tid = cand if cand in tags else name_to_id.get(str(cand).upper())
    if tid is None:
        addr = lv.get('address')
        if addr:
            tid = name_to_id.get(str(addr).upper())
    if tid is None or tid not in tags:
        pool_by_name[str(cand).upper()] = ('NO_MATCH', lv.get('value'))
        continue
    tags[tid] = {'value': coerce(lv.get('value'))}

# 4. For each alarm card, report what the UI tagValues[tag_id] would be
print(f"\n{'TAG':<14}{'in_tags?':<10}{'final_value':<14}{'card_shows_PV?'}")
print("-"*60)
blank = []
for tag_id, state, sp, rv in alarm_tags:
    in_tags = tag_id in tags
    val = tags.get(tag_id, {}).get('value') if in_tags else None
    shows = isinstance(val, (int, float))
    if not shows:
        blank.append(tag_id)
    print(f"{tag_id:<14}{str(in_tags):<10}{str(val):<14}{shows}")

print(f"\nCARDS WITHOUT LIVE PV: {blank}")
cur.close(); conn.close()
