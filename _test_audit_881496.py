import requests

r = requests.get('http://localhost:6001/api/alarms/audit/881496')
d = r.json()

print(f'Success: {d["success"]}')
print(f'Count: {len(d.get("audit_trail", []))}')
print('\nFirst 10 records:')
for i, rec in enumerate(d.get('audit_trail', [])[:10], 1):
    print(f'{i}. {rec["action_type"]:12} - {rec["action_timestamp"]}')
