import requests

r = requests.get('http://localhost:5001/api/opc/values')
data = r.json()

if isinstance(data, dict) and 'tags' in data:
    all_tags = data['tags']
    welding = [t for t in all_tags if 'Welding' in t.get('tagId','') or 'Joint' in t.get('tagId','') or 'Pipe' in t.get('tagId','') or 'Welder' in t.get('tagId','') or 'WPS' in t.get('tagId','') or t.get('tagId','') in ['Arc','Power','sim_step']]
else:
    welding = []

print(f'\n✅ Welding tags in API NOW: {len(welding)}/9\n')
for t in sorted(welding, key=lambda x: x['tagId']):
    print(f"{t['tagId']}: {t.get('value')}")
