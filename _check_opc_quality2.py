import requests, jwt, datetime

SECRET = 'hmi-secret-key-change-in-production'
payload = {'user_id': 0, 'username': 'diag', 'role': 'admin',
           'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1)}
token = jwt.encode(payload, SECRET, algorithm='HS256')

r = requests.get('http://127.0.0.1:6001/api/tags/latest',
                 headers={'Authorization': f'Bearer {token}'})
print('status:', r.status_code)
tags = r.json().get('tags', {})
print('total tags:', len(tags))

# Show quality breakdown
from collections import Counter
qs = Counter(v.get('quality') for v in tags.values())
print('quality breakdown:', dict(qs))

# Show first 10 with non-Good quality
bad = [(k, v.get('quality')) for k, v in tags.items() if v.get('quality') != 'Good']
print(f'\nnon-Good tags ({len(bad)} total):')
for k, q in bad[:20]:
    print(f'  {k}: {q}')
