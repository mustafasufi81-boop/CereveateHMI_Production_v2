import urllib.request, json

try:
    with urllib.request.urlopen('http://127.0.0.1:5001/api/opc/values', timeout=5) as r:
        data = json.loads(r.read())
    tags = data.get('tags') or data.get('values') or []
    print(f'OPC /api/opc/values: {len(tags)} tags returned')
    from collections import Counter
    qs = Counter(str(t.get('quality','?')) for t in tags)
    print('Quality breakdown:', dict(qs))
    print('\nFirst 10 tags:')
    for t in tags[:10]:
        print(f"  tagId={t.get('tagId') or t.get('tag_id')}  quality={t.get('quality')}  value={t.get('value')}")
except Exception as e:
    print(f'ERROR: {e}')
