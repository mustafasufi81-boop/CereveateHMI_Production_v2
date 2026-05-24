import json
with open('tags_to_insert.json') as f:
    tags = json.load(f)
print(f'Total tags: {len(tags)}')
print('Sample (first 5):')
for t in tags[:5]:
    print(f"  {t['tag_id']:12} unit={t['eng_unit']:6} LL={t['alarm_ll_limit']} L={t['alarm_l_limit']} H={t['alarm_h_limit']} HH={t['alarm_hh_limit']}")
units = set(t['eng_unit'] for t in tags)
print(f'\nUnique units: {units}')
nulls = [t['tag_id'] for t in tags if t['alarm_hh_limit'] is None]
print(f'Tags with NULL HH limit: {len(nulls)} -> {nulls}')
