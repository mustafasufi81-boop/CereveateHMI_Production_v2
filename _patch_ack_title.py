path = r'd:\CereveateHMI_Production\HMI\apex-hmi\src\components\hmi\AlarmPanel.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix ACK title to show stale message
old_title = '                                    title={!isDatabaseBackedAlarm(alarm) ? "Waiting for DB save before acknowledge" : alarm.alarm_state === \'RTN_UNACK\' ?'
new_title = '                                    title={isTagStaleForAck ? `Tag data is stale (${Math.floor((Date.now() - (_ackTagTs ?? 0)) / 1000)}s since last poll) \u2014 ACK blocked until live data restored` : !isDatabaseBackedAlarm(alarm) ? "Waiting for DB save before acknowledge" : alarm.alarm_state === \'RTN_UNACK\' ?'

if old_title in content:
    content = content.replace(old_title, new_title, 1)
    print('ACK title updated')
else:
    # find nearby text
    pos = content.find('Waiting for DB save before acknowledge')
    print(f'Found at {pos}')
    print(repr(content[pos-120:pos+20]))

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('done')
