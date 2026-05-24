import json

with open('trends-config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

limits = config['PivotTableSettings']['AlarmLimits']

print('ALARM LIMITS VERIFICATION')
print('='*80)
all_valid = True
for tag, v in limits.items():
    valid = v['Warning'] < v['Alarm'] < v['Trip']
    status = '✅' if valid else '❌'
    print(f'{status} {tag:30} W={v["Warning"]:3} A={v["Alarm"]:3} T={v["Trip"]:3}')
    if not valid:
        all_valid = False

print('='*80)
if all_valid:
    print('✅ ALL LIMITS VALID - Warning < Alarm < Trip')
else:
    print('❌ SOME LIMITS INVALID - Fix needed!')
