import urllib.request, json
try:
    with urllib.request.urlopen('http://127.0.0.1:5001/api/plc/values', timeout=3) as r:
        data = json.loads(r.read().decode())
    raw = data.get('values') or data.get('tags') or []
    if isinstance(raw, dict):
        raw = list(raw.values())
    print("total pool rows:", len(raw))
    found = False
    for row in raw:
        keys = {k: row.get(k) for k in ('tagId','tag_id','tagName','address','value','quality','computedQuality')}
        s = json.dumps(keys)
        if 'AY1101' in s:
            print("MATCH:", s)
            found = True
    if not found:
        print("AY1101 NOT in PLC pool")
        print("Sample row keys:", list(raw[0].keys()) if raw else "none")
        if raw:
            print("Sample row:", json.dumps(raw[0]))
except Exception as e:
    print("ERR", e)
