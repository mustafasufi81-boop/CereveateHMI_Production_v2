with open('AlarmPanel.tsx', 'rb') as f:
    raw = f.read()

content = raw.decode('utf-8')

# ── FIX 1: Replace modal call with inline message ──────────────────────────
old1 = (
    '        if (alarmBeforeClear) {\r\n'
    '          setClearBlockedAlarm({ alarm: alarmBeforeClear, liveValue, setpoint });\r\n'
    '        } else {\r\n'
)
if old1 in content:
    # find full if/else block end
    start = content.find(old1)
    # find closing brace of else block
    end = content.find('        }\r\n        scheduleRefresh', start)
    end_pos = end + len('        }\r\n')
    new1 = (
        '        setClearBlockedMsg({ alarmId: alarmBeforeClear?.id ?? (clearingAlarmId ?? 0), '
        'msg: `\u274c Cannot clear \u2014 value ${liveValue.toFixed(3)} still above setpoint ${setpoint.toFixed(3)}` });\r\n'
    )
    content = content[:start] + new1 + content[end_pos:]
    print('FIX 1 OK')
else:
    print('FIX 1 FAIL')
    idx = content.find('setClearBlockedAlarm({ alarm: alarmBeforeClear')
    if idx >= 0:
        print(repr(content[idx-80:idx+250]))

# ── FIX 2: Remove the popup modal block ────────────────────────────────────
# Find the comment that starts the modal
marker_start = '      {/* \u2500\u2500 Value-Still-High Block Popup'
if marker_start not in content:
    # fallback: find by clearBlockedAlarm render
    marker_start = None
    idx = content.find('      {clearBlockedAlarm && (')
    if idx >= 0:
        # walk back to find preceding comment line
        line_start = content.rfind('\n', 0, idx) + 1
        marker_start_idx = line_start
    else:
        print('FIX 2 FAIL - clearBlockedAlarm render not found')
        marker_start_idx = None
else:
    marker_start_idx = content.find(marker_start)

if marker_start_idx is not None:
    # find the closing )}\r\n after the modal
    search_from = content.find('      {clearBlockedAlarm && (', marker_start_idx)
    end_tag = '      )}\r\n'
    end_pos = content.find(end_tag, search_from) + len(end_tag)
    content = content[:marker_start_idx] + content[end_pos:]
    print('FIX 2 OK')

# ── FIX 3: Remove the clearBlockedAlarm state declaration ──────────────────
old3_a = "  const [clearBlockedAlarm, setClearBlockedAlarm] = useState<{ alarm: Alarm; liveValue: number; setpoint: number } | null>(null);\r\n"
old3_b = "  const [clearBlockedAlarm, setClearBlockedAlarm] = useState<{ alarm: Alarm; liveValue: number; setpoint: number } | null>(null);\n"
if old3_a in content:
    content = content.replace(old3_a, '', 1)
    print('FIX 3 OK (CRLF)')
elif old3_b in content:
    content = content.replace(old3_b, '', 1)
    print('FIX 3 OK (LF)')
else:
    print('FIX 3 SKIP - state already removed or not found')

with open('AlarmPanel.tsx', 'w', encoding='utf-8') as f:
    f.write(content)

print('SAVED')

# Verify
remaining = ['setClearBlockedAlarm', 'clearBlockedAlarm &&']
with open('AlarmPanel.tsx', 'r', encoding='utf-8') as f:
    final = f.read()
for r in remaining:
    if r in final:
        print(f'WARNING still contains: {r}')
    else:
        print(f'OK removed: {r}')
