import requests

r = requests.get('http://localhost:7001/api/tags')
tags = r.json()

print(f'\n✅ TOTAL TAGS LOADED: {len(tags)}\n')
print('=' * 60)

for i, tag in enumerate(tags, 1):
    print(f'{i:2d}. {tag["tag_id"]}')

print('=' * 60)
print(f'\n✅ All {len(tags)} tags are being sent to the UI')
