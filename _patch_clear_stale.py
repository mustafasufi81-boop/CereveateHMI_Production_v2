path = r'd:\CereveateHMI_Production\HMI\apex-hmi\src\components\hmi\AlarmPanel.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_clear_disabled = (
    'disabled={isPending(alarm.id) || (() => { const _ts = alarm.tag_id ? tagTimestamps[alarm.tag_id] : undefined;'
    ' return _ts !== undefined && (Date.now() - _ts) > 30_000; })()}\n'
    '                                  title={(() => { const _ts = alarm.tag_id ? tagTimestamps[alarm.tag_id] : undefined;'
    ' const stale = _ts !== undefined && (Date.now() - _ts) > 30_000;'
    " return stale ? `Tag data is stale (${Math.floor((Date.now() - (_ts ?? 0)) / 1000)}s since last poll) \u2014 CLEAR blocked until live data restored` : \"Clear this alarm\"; })()}"
)

new_clear_disabled = (
    'disabled={isPending(alarm.id) || (alarm.tag_id ? tagStale[alarm.tag_id] === true : false)}\n'
    '                                  title={(alarm.tag_id && tagStale[alarm.tag_id])'
    ' ? "Tag data is stale \u2014 PLC connection lost or no recent data. CLEAR blocked until live data is restored."'
    ' : "Clear this alarm"}'
)

if old_clear_disabled in content:
    content = content.replace(old_clear_disabled, new_clear_disabled, 1)
    print('CLEAR button updated')
else:
    print('CLEAR NOT FOUND - dumping nearby:')
    pos = content.find('CLEAR blocked until')
    print(repr(content[pos-200:pos+100]))

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Saved')
