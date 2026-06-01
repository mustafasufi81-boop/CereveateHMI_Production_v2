import urllib.request, json
with urllib.request.urlopen('http://127.0.0.1:5001/api/plc/values', timeout=3) as r:
    data = json.loads(r.read().decode())
raw = data.get('values') or data.get('tags') or []
if isinstance(raw, dict):
    raw = list(raw.values())
for row in raw:
    if row.get('tagName') == 'AY1101' or row.get('address') == 'AY1101':
        print("RAW KEYS:", list(row.keys()))
        print("RAW JSON:", json.dumps(row, indent=2))
        break
