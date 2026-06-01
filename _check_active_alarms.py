import psycopg2

conn = psycopg2.connect(
    dbname="Automation_DB",
    user="cereveate",
    password="cereveate@222",
    host="localhost",
    port="5432"
)

cur = conn.cursor()

print("=" * 80)
print("CHECKING ALARM_ACTIVE TABLE - Current Active Alarms")
print("=" * 80)

cur.execute("""
    SELECT 
        alarm_key,
        tag_id,
        level,
        alarm_state,
        current_event_id,
        raised_at,
        ack_by,
        ack_at
    FROM historian_raw.alarm_active
    ORDER BY raised_at DESC
""")

rows = cur.fetchall()
print(f"\nFound {len(rows)} active alarms:\n")

for row in rows:
    alarm_key, tag_id, level, state, event_id, raised_at, ack_by, ack_at = row
    print(f"Tag: {tag_id:12} | Level: {level:2} | State: {state:12} | Event ID: {event_id} | Raised: {raised_at}")
    if ack_by:
        print(f"  └─ ACK by {ack_by} at {ack_at}")

print("\n" + "=" * 80)
print("CHECKING IF VALUES ARE STILL ABOVE SETPOINT")
print("=" * 80)

# Check current tag values vs setpoints
cur.execute("""
    SELECT 
        aa.tag_id,
        aa.level,
        aa.alarm_state,
        aa.current_event_id,
        aa.raised_at,
        aa.raised_value,
        aa.setpoint_value,
        tm.current_value,
        tm.updated_at as value_timestamp
    FROM historian_raw.alarm_active aa
    LEFT JOIN historian_meta.tag_master tm ON aa.tag_id = tm.tag_id
    ORDER BY aa.raised_at DESC
""")

rows = cur.fetchall()
print(f"\nChecking if alarms should still be active:\n")

for row in rows:
    tag_id, level, state, event_id, raised_at, raised_val, setpoint, current_val, val_ts = row
    
    still_alarming = "?"
    if current_val is not None and setpoint is not None:
        if level in ('H', 'HH'):
            still_alarming = "YES" if current_val > setpoint else "NO"
        elif level in ('L', 'LL'):
            still_alarming = "YES" if current_val < setpoint else "NO"
    
    print(f"\nTag: {tag_id} ({level})")
    print(f"  Event ID: {event_id} | Raised: {raised_at}")
    print(f"  State: {state}")
    print(f"  Raised Value: {raised_val} | Setpoint: {setpoint}")
    print(f"  Current Value: {current_val} (as of {val_ts})")
    print(f"  Still Alarming: {still_alarming}")

cur.close()
conn.close()

print("\n" + "=" * 80)
print("RECOMMENDATION:")
print("If current values are NORMAL but alarms show as ACTIVE_ACK,")
print("they should be CLEARED to allow new occurrences with fresh event_ids.")
print("=" * 80)
