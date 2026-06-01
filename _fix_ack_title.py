path = r'd:\CereveateHMI_Production\HMI\apex-hmi\src\components\hmi\AlarmPanel.tsx'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

# Locate the broken title by finding _ackTagTs
pos = c.find('_ackTagTs')
if pos < 0:
    print('_ackTagTs not found - already clean')
else:
    # Find the title={ that wraps it
    ts = c.rfind('title={', 0, pos)
    # Walk forward to find matching closing }
    depth = 0
    i = ts + 7  # skip past 'title={'
    while i < len(c):
        if c[i] == '{':
            depth += 1
        elif c[i] == '}':
            if depth == 0:
                break
            depth -= 1
        i += 1
    te = i + 1  # include the closing }

    old_title = c[ts:te]
    print('OLD title (first 100):', old_title[:100])

    # Build clean replacement - no template literals, no _ackTagTs
    new_title = (
        'title={'
        'isTagStaleForAck'
        ' ? "Tag data is stale \u2014 PLC connection lost. ACK blocked until live data restored."'
        ' : !isDatabaseBackedAlarm(alarm)'
        ' ? "Waiting for DB save before acknowledge"'
        " : alarm.alarm_state === 'RTN_UNACK'"
        ' ? "ACK this alarm \u2014 value returned to normal, ACK will CLEAR it"'
        ' : "Acknowledge alarm"'
        '}'
    )

    c = c[:ts] + new_title + c[te:]
    print('NEW title:', new_title[:100])

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
print('Saved OK')
