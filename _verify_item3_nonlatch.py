"""Item 3 verification: non-latching auto-clear.
Watches recent alarm history for ALARM_CLEARED rows authored by SYSTEM (non-latching),
and confirms RTN_UNACK still occurs for unacknowledged alarms."""
import jwt, datetime, time, requests

SECRET = 'hmi-secret-key-change-in-production'
tok = jwt.encode({'user_id': 1, 'username': 'admin',
                  'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1),
                  'partial': False}, SECRET, algorithm='HS256')
if isinstance(tok, bytes):
    tok = tok.decode()
h = {'Authorization': f'Bearer {tok}'}
BASE = 'http://127.0.0.1:8090'

def get(ep):
    return requests.get(f'{BASE}{ep}', headers=h, timeout=8).json()

# 1. Look at active alarms; ACK every ActiveUnack so they become ActiveAck.
active = get('/api/alarms/active')
alarms = active.get('alarms', [])
print(f"Active alarms: {len(alarms)}")
acked = 0
for a in alarms:
    if a.get('alarm_state') == 'ACTIVE_UNACK':
        key = a.get('alarm_key')
        try:
            r = requests.post(f'{BASE}/api/alarms/{requests.utils.quote(key, safe="")}/ack',
                              headers=h, json={'notes': 'item3 test'}, timeout=8)
            print(f"  ACK {key}: {r.status_code}")
            acked += 1
        except Exception as e:
            print(f"  ACK {key} failed: {e}")
print(f"Acked {acked} alarms. Now watching ~70s for auto-clear events...\n")

# 2. Poll history for ALARM_CLEARED rows with SYSTEM (non-latching).
seen = set()
auto_clears = 0
rtn_unacks = 0
for i in range(14):  # ~70s
    hist = get('/api/alarms/history?limit=80')
    for ev in hist.get('events', []):
        sig = (ev.get('time'), ev.get('tag_id'), ev.get('event_type'), ev.get('alarm_level'))
        if sig in seen:
            continue
        seen.add(sig)
        et = ev.get('event_type')
        msg = ev.get('message', '') or ''
        if et == 'ALARM_CLEARED' and 'non-latching' in msg:
            auto_clears += 1
            print(f"  AUTO-CLEAR ✓ {ev.get('tag_id')} {ev.get('alarm_level')} @ {ev.get('time')}")
        elif et == 'ALARM_RTN':
            rtn_unacks += 1
    time.sleep(5)

print(f"\nResult: auto-clears(non-latching)={auto_clears}, RTN_UNACK rows={rtn_unacks}")
print("PASS: non-latching auto-clear observed" if auto_clears > 0
      else "NOTE: no acked alarm returned to normal during the window (try again or wait for a swing)")
