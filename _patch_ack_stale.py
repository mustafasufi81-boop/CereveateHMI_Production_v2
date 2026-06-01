import sys

path = r'd:\CereveateHMI_Production\HMI\apex-hmi\src\components\hmi\AlarmPanel.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# ── ACK button: wrap in IIFE and add isTagStale guard ──────────────────────
# The file uses unicode lookalike dashes (â€") - find the actual text
idx = content.find('ACK')
# Search for the exact block using substrings we know are there
ACK_DISABLED_OLD = 'disabled={isPending(alarm.id) || !isDatabaseBackedAlarm(alarm)}'
ACK_DISABLED_NEW = 'disabled={isPending(alarm.id) || !isDatabaseBackedAlarm(alarm) || isTagStaleForAck}'

if ACK_DISABLED_OLD not in content:
    print('ERROR: ACK disabled line not found')
    sys.exit(1)

# Replace the disabled prop
content = content.replace(ACK_DISABLED_OLD, ACK_DISABLED_NEW, 1)
print('ACK disabled prop updated')

# Now find the canOperateAlarms && ( line just before the ACK button
# and replace it with the IIFE version
ACK_OPEN_OLD = (
    '{/* ACK \xe2\x80\x94 Viewer cannot operate */}\n\n'
    '                                {canOperateAlarms && (\n\n'
    '                                  <button\n\n'
    '                                    onClick={(e) => handleAcknowledge(alarm, e)}\n\n'
    '                                    disabled={isPending(alarm.id) || !isDatabaseBackedAlarm(alarm) || isTagStaleForAck}'
)

# check bytes vs str issue - file is str after decode
# Try a different approach: replace the wrapper line only
WRAPPER_OLD = '                                {canOperateAlarms && (\n\n                                  <button\n\n                                    onClick={(e) => handleAcknowledge(alarm, e)}\n\n                                    disabled={isPending(alarm.id) || !isDatabaseBackedAlarm(alarm) || isTagStaleForAck}'
WRAPPER_NEW = (
    '                                {canOperateAlarms && (() => {\n'
    '                                  const _ackTagTs = alarm.tag_id ? tagTimestamps[alarm.tag_id] : undefined;\n'
    '                                  const isTagStaleForAck = _ackTagTs !== undefined && (Date.now() - _ackTagTs) > 30_000;\n'
    '                                  return (\n'
    '                                  <button\n\n'
    '                                    onClick={(e) => handleAcknowledge(alarm, e)}\n\n'
    '                                    disabled={isPending(alarm.id) || !isDatabaseBackedAlarm(alarm) || isTagStaleForAck}'
)

if WRAPPER_OLD in content:
    content = content.replace(WRAPPER_OLD, WRAPPER_NEW, 1)
    print('ACK wrapper IIFE applied')
else:
    print('WARNING: ACK wrapper not found, trying to find it...')
    pos = content.find('isTagStaleForAck')
    if pos >= 0:
        print(repr(content[pos-300:pos+50]))

# Now close the IIFE: the existing )} that closes {canOperateAlarms && (
# becomes ); })()}
# Find the </button>\n\n                                )}\n\n                                {/* SUPP
CLOSE_OLD = '                                  </button>\n\n                                )}\n\n                                {/* SUPP'
CLOSE_NEW = (
    '                                  </button>\n'
    '                                  );\n'
    '                                })()}\n\n'
    '                                {/* SUPP'
)

if CLOSE_OLD in content:
    content = content.replace(CLOSE_OLD, CLOSE_NEW, 1)
    print('ACK IIFE close applied')
else:
    print('WARNING: CLOSE not found')

# ── CLEAR button: add isTagStale guard ─────────────────────────────────────
CLEAR_DISABLED_OLD = '                                  disabled={isPending(alarm.id)}\n'
CLEAR_DISABLED_NEW = (
    '                                  disabled={isPending(alarm.id) || (() => { const _ts = alarm.tag_id ? tagTimestamps[alarm.tag_id] : undefined; return _ts !== undefined && (Date.now() - _ts) > 30_000; })()}\n'
    '                                  title={(() => { const _ts = alarm.tag_id ? tagTimestamps[alarm.tag_id] : undefined; const stale = _ts !== undefined && (Date.now() - _ts) > 30_000; return stale ? `Tag data is stale (${Math.floor((Date.now() - (_ts ?? 0)) / 1000)}s since last poll) \u2014 CLEAR blocked until live data restored` : "Clear this alarm"; })()}\n'
)

if CLEAR_DISABLED_OLD in content:
    content = content.replace(CLEAR_DISABLED_OLD, CLEAR_DISABLED_NEW, 1)
    print('CLEAR disabled prop updated')
else:
    print('WARNING: CLEAR disabled prop not found')
    pos = content.find('handleClear(alarm.id')
    if pos >= 0:
        print(repr(content[pos-10:pos+200]))

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('All done - file saved')
