import psycopg2
from datetime import datetime

conn = psycopg2.connect(
    dbname="Automation_DB",
    user="cereveate",
    password="cereveate@222",
    host="localhost",
    port="5432"
)

cur = conn.cursor()

# Check historian_events for tag VYAN1101G (event_id 881456)
print("=" * 80)
print("CHECKING HISTORIAN_EVENTS TABLE FOR TAG VYAN1101G")
print("=" * 80)

cur.execute("""
    SELECT 
        event_id,
        tag_id,
        event_type,
        time,
        alarm_actual_value,
        alarm_setpoint
    FROM historian_raw.historian_events
    WHERE tag_id = 'VYAN1101G'
    ORDER BY time DESC
    LIMIT 20
""")

rows = cur.fetchall()
print(f"\nFound {len(rows)} events in historian_events for VYAN1101G:\n")
for i, row in enumerate(rows, 1):
    event_id, tag_id, event_type, time, value, setpoint = row
    print(f"{i}. Event ID: {event_id} | Type: {event_type:15} | Time: {time} | Value: {value} | Setpoint: {setpoint}")

# Check alarm_audit_trail for event_id 881456
print("\n" + "=" * 80)
print("CHECKING ALARM_AUDIT_TRAIL FOR EVENT_ID 881456")
print("=" * 80)

cur.execute("""
    SELECT 
        audit_id,
        event_id,
        action_type,
        action_timestamp,
        performed_by
    FROM historian_raw.alarm_audit_trail
    WHERE event_id = 881456
    ORDER BY action_timestamp DESC
    LIMIT 20
""")

rows = cur.fetchall()
print(f"\nFound {len(rows)} audit records for event_id 881456:\n")
for i, row in enumerate(rows, 1):
    audit_id, event_id, action_type, action_timestamp, performed_by = row
    print(f"{i}. Audit ID: {audit_id} | Action: {action_type:12} | Time: {action_timestamp} | By: {performed_by}")

# Check if there are multiple event_ids for the same tag
print("\n" + "=" * 80)
print("ALL EVENT IDs FOR TAG VYAN1101G")
print("=" * 80)

cur.execute("""
    SELECT 
        event_id,
        event_type,
        time,
        alarm_actual_value
    FROM historian_raw.historian_events
    WHERE tag_id = 'VYAN1101G'
    AND event_type LIKE 'ALARM%'
    ORDER BY time DESC
    LIMIT 50
""")

rows = cur.fetchall()
print(f"\nFound {len(rows)} alarm events:\n")

event_counts = {}
for row in rows:
    event_id, event_type, time, value = row
    if event_id not in event_counts:
        event_counts[event_id] = {'first': time, 'last': time, 'count': 0}
    event_counts[event_id]['count'] += 1
    event_counts[event_id]['last'] = min(event_counts[event_id]['last'], time)

print("\nEvent ID Summary:")
for event_id, info in sorted(event_counts.items(), key=lambda x: x[1]['first'], reverse=True):
    print(f"Event ID {event_id}: {info['count']} occurrences, First: {info['first']}, Last: {info['last']}")

cur.close()
conn.close()

print("\n" + "=" * 80)
print("ANALYSIS COMPLETE")
print("=" * 80)
