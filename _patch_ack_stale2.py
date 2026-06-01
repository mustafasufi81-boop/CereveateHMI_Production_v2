path = r'd:\CereveateHMI_Production\HMI\apex-hmi\src\components\hmi\AlarmPanel.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# ── ACK button: replace timestamp-based stale with tagStale from API ──────
old_ack = (
    'const _ackTagTs = alarm.tag_id ? tagTimestamps[alarm.tag_id] : undefined;\n'
    '                                  const isTagStaleForAck = _ackTagTs !== undefined && (Date.now() - _ackTagTs) > 30_000;\n'
)
new_ack = (
    '// API sets stale=true when PLC pool is down or data age > 60s\n'
    '                                  const isTagStaleForAck = alarm.tag_id ? (tagStale[alarm.tag_id] === true) : false;\n'
)
if old_ack in content:
    content = content.replace(old_ack, new_ack, 1)
    print('ACK stale logic replaced')
else:
    print('ACK NOT FOUND')

# ── CLEAR button: find the disabled prop (contains handleClear nearby) ───
# Find and dump what's after handleClear
pos = content.find('handleClear(alarm.id')
print('handleClear at:', pos)
print(repr(content[pos:pos+600]))

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Saved')
