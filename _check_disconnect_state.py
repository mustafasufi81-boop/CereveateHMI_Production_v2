"""
Check current state during PLC disconnect (since 22:40)
"""
import requests
from datetime import datetime

FLASK_API = "http://localhost:6001"

print("="*70)
print("PLC DISCONNECT STATE CHECK")
print(f"Current time: {datetime.now().strftime('%H:%M:%S')}")
print("PLC disconnected since: ~22:40 (10:40 PM)")
print("="*70)

# 1. Check active alarms
print("\n[1] ACTIVE ALARMS:")
try:
    resp = requests.get(f"{FLASK_API}/api/alarms/active?limit=20", timeout=5)
    if resp.ok:
        alarms = resp.json().get("alarms", [])
        print(f"   Total active: {len(alarms)}")
        for alarm in alarms[:5]:
            tag = alarm.get('tag_id')
            level = alarm.get('alarm_level')
            state = alarm.get('alarm_state')
            value = alarm.get('current_value')
            ts = alarm.get('timestamp', '')[:19] if alarm.get('timestamp') else 'N/A'
            print(f"   • {tag}:{level} = {value} | {state} | {ts}")
    else:
        print(f"   ❌ HTTP {resp.status_code}")
except Exception as e:
    print(f"   ❌ {e}")

# 2. Check TY1101D specifically
print("\n[2] TY1101D TAG STATE:")
try:
    resp = requests.get(f"{FLASK_API}/api/tags/TY1101D/value", timeout=5)
    if resp.ok:
        data = resp.json()
        print(f"   Value: {data.get('value')}")
        print(f"   Quality: {data.get('quality')}")
        print(f"   Timestamp: {data.get('timestamp', '')[:19]}")
    else:
        print(f"   ❌ HTTP {resp.status_code}")
except Exception as e:
    print(f"   ❌ {e}")

# 3. Check C# OPC service status
print("\n[3] C# OPC SERVICE STATUS:")
try:
    resp = requests.get("http://localhost:5001/api/tags/status", timeout=2)
    if resp.ok:
        data = resp.json()
        print(f"   Connected: {data.get('connected')}")
        print(f"   Tag count: {data.get('tagCount')}")
        print(f"   Last update: {data.get('lastUpdate', '')[:19]}")
    else:
        print(f"   ❌ HTTP {resp.status_code}")
except Exception as e:
    print(f"   ❌ Service not responding: {e}")

# 4. Check alarm evaluation diagnostics
print("\n[4] ALARM EVALUATOR DIAGNOSTICS:")
try:
    resp = requests.get("http://localhost:5001/api/alarms/diagnostics", timeout=2)
    if resp.ok:
        data = resp.json()
        print(f"   Evaluation cycles: {data.get('evaluationCycles')}")
        print(f"   Active alarms: {data.get('activeAlarmsCount')}")
        print(f"   Last cycle: {data.get('lastCycleTime', '')[:19]}")
    else:
        print(f"   ❌ HTTP {resp.status_code}")
except Exception as e:
    print(f"   ❌ {e}")

print("\n" + "="*70)
print("ANALYSIS:")
print("="*70)
print("""
If PLC disconnected at 22:40:
1. ✅ MQTT should stop sending updates (frontend shows STALE)
2. ✅ C# cache should mark IsStale=true after 30s
3. ✅ AlarmEvaluationService should SKIP evaluation (line 192)
4. ❓ BUT old alarms remain in alarm_active table (not auto-cleared)

Expected behavior:
- Existing alarms stay ACTIVE (correct - they were real before disconnect)
- No NEW alarms should be raised (cache is stale)
- Frontend shows STALE badge (correct)
- Values shown are LAST KNOWN GOOD values before disconnect

This is ISA-18.2 compliant: alarms persist until operator clears them,
even if PLC disconnects. System shows last known state + STALE warning.
""")
