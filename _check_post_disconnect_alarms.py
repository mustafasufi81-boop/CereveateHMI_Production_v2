"""
Check if alarm system is STILL RAISING alarms after PLC disconnect
This is the BUG - no new alarms should appear after 22:40 disconnect
"""
import psycopg2
from datetime import datetime, timedelta

conn = psycopg2.connect(
    host="localhost",
    database="Automation_DB",
    user="cereveate",
    password="cereveate@222"
)
cur = conn.cursor()

print("="*70)
print("CHECKING ALARMS AFTER PLC DISCONNECT (22:40)")
print("="*70)

# Get alarms raised AFTER 22:40 (when PLC was already disconnected)
disconnect_time = "2026-05-30 22:40:00"

print(f"\n[1] NEW ALARMS RAISED AFTER DISCONNECT ({disconnect_time}):")
cur.execute("""
    SELECT 
        tag_id,
        alarm_level,
        alarm_state,
        time,
        alarm_actual_value,
        transition_seq
    FROM historian_raw.historian_events
    WHERE time > %s
    AND alarm_state = 'ACTIVE_UNACK'
    ORDER BY time DESC
    LIMIT 20
""", (disconnect_time,))

events = cur.fetchall()
print(f"   Found {len(events)} new alarm raises after disconnect")
print()

for row in events:
    tag, level, state, ts, value, seq = row
    print(f"   🔴 {ts} | {tag}:{level} = {value} | seq={seq}")

if len(events) > 0:
    print("\n   ❌ BUG CONFIRMED: System is raising alarms AFTER PLC disconnect!")
    print("   This should NOT happen - cache should be marked STALE.")

# Check for value CHANGES in alarm_active after disconnect
print(f"\n[2] ALARM VALUE CHANGES AFTER DISCONNECT:")
cur.execute("""
    SELECT 
        tag_id,
        alarm_level,
        current_value,
        previous_value,
        last_transition_time
    FROM historian_raw.alarm_active
    WHERE last_transition_time > %s
    ORDER BY last_transition_time DESC
    LIMIT 10
""", (disconnect_time,))

changes = cur.fetchall()
if changes:
    print(f"   Found {len(changes)} alarm state changes")
    for row in changes:
        tag, level, curr_val, prev_val, ts = row
        print(f"   • {tag}:{level} | {prev_val} → {curr_val} at {ts}")
else:
    print("   ✅ No changes in alarm_active after disconnect")

# Check historian_events for the same tag with different values
print(f"\n[3] TY1101D VALUE CHANGES AFTER DISCONNECT:")
cur.execute("""
    SELECT 
        time,
        alarm_level,
        alarm_state,
        alarm_actual_value,
        transition_seq
    FROM historian_raw.historian_events
    WHERE tag_id = 'TY1101D'
    AND time > %s
    ORDER BY time DESC
    LIMIT 10
""", (disconnect_time,))

ty_events = cur.fetchall()
if ty_events:
    print(f"   Found {len(ty_events)} TY1101D events after disconnect:")
    for row in ty_events:
        ts, level, state, value, seq = row
        print(f"   • {ts} | {level}:{state} | value={value} | seq={seq}")
else:
    print("   ✅ No TY1101D events after disconnect (correct)")

conn.close()

print("\n" + "="*70)
print("ROOT CAUSE ANALYSIS:")
print("="*70)
print("""
IF new alarms appeared after 22:40:
→ Cache IsStale check is NOT working
→ AlarmEvaluationService is still using cached values
→ FIX NEEDED: Quality-based staleness check (already built, needs restart)

IF no new alarms but values are changing in UI:
→ Frontend is interpolating/calculating values
→ OR WebSocket is sending stale MQTT retained messages
→ Check MQTT broker for retained messages on opc/alarms/events
""")
