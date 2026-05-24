import requests

r = requests.get('http://localhost:1202/api/opc/values')
data = r.json()

arc_tags = [t for t in data.get('tags', []) if 'Arc' in t.get('tagId', '')]

print('\n=== ARC TAG VALUES FROM HMI ===')
for t in arc_tags:
    print(f"tagId: {t['tagId']:30s} | value: {t['value']:20} | quality: {t['quality']}")

# Also check PLC endpoint directly
print('\n=== ARC TAG VALUES FROM PLC ===')
r2 = requests.get('http://localhost:5001/api/plc/values')
data2 = r2.json()

arc_plc = [v for v in data2.get('values', []) if 'Arc' in v.get('address', '') or 'Arc' in v.get('tagName', '')]
for v in arc_plc:
    print(f"address: {v['address']:30s} | value: {v['value']:20} | quality: {v['quality']}")
    print(f"tagName: {v['tagName']:30s} | dataType: {v['dataType']}")
