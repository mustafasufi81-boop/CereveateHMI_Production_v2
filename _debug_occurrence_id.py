import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost', 
    port=5432, 
    database='Automation_DB', 
    user='cereveate', 
    password='cereveate@222',
    cursor_factory=RealDictCursor
)

cur = conn.cursor()

print()
print("=" * 100)
print("DEBUGGING OCCURRENCE_ID FIX")
print("=" * 100)
print()

# Check alarm_active for event 97934
print("1. Checking alarm_active table for event 97934:")
cur.execute("""
    SELECT current_event_id, alarm_key, alarm_state, occurrence_id
    FROM historian_raw.alarm_active
    WHERE current_event_id = 97934
""")
active_row = cur.fetchone()

if active_row:
    print(f"   Event: {active_row['current_event_id']}")
    print(f"   Key: {active_row['alarm_key']}")
    print(f"   State: {active_row['alarm_state']}")
    print(f"   occurrence_id: {active_row['occurrence_id']}")
    
    if active_row['occurrence_id']:
        print(f"   ✅ alarm_active HAS occurrence_id")
    else:
        print(f"   ❌ alarm_active has NULL occurrence_id")
else:
    print("   ⚠️  Event 97934 not found in alarm_active (might be cleared)")

print()

# Check the most recent audit record
print("2. Checking most recent audit record for event 97934:")
cur.execute("""
    SELECT audit_id, action_type, performed_by, occurrence_id, action_timestamp
    FROM historian_raw.alarm_audit_trail
    WHERE event_id = 97934
    ORDER BY action_timestamp DESC
    LIMIT 1
""")
audit_row = cur.fetchone()

if audit_row:
    print(f"   Audit ID: {audit_row['audit_id']}")
    print(f"   Action: {audit_row['action_type']}")
    print(f"   By: {audit_row['performed_by']}")
    print(f"   occurrence_id: {audit_row['occurrence_id']}")
    print(f"   Time: {audit_row['action_timestamp']}")
    
    if audit_row['occurrence_id']:
        print(f"   ✅ audit_trail HAS occurrence_id")
    else:
        print(f"   ❌ audit_trail has NULL occurrence_id - FIX NOT WORKING")

print()

# Check if DAO code is being used
print("3. Checking for any recent audit records with occurrence_id (from any event):")
cur.execute("""
    SELECT audit_id, event_id, action_type, occurrence_id, action_timestamp
    FROM historian_raw.alarm_audit_trail
    WHERE occurrence_id IS NOT NULL
    ORDER BY action_timestamp DESC
    LIMIT 3
""")
recent_with_occ = cur.fetchall()

if recent_with_occ:
    print(f"   ✅ Found {len(recent_with_occ)} records with occurrence_id:")
    for r in recent_with_occ:
        print(f"      Event {r['event_id']} | {r['action_type']} | {r['occurrence_id']}")
else:
    print(f"   ❌ NO records with occurrence_id found - DAO fix not being used")

print()
print("=" * 100)
print()

# Diagnosis
print("DIAGNOSIS:")
if not active_row:
    print("⚠️  Event 97934 not in alarm_active - might have been cleared")
elif not active_row['occurrence_id']:
    print("❌ ROOT CAUSE: alarm_active.occurrence_id is NULL")
    print("   C# AlarmStateManager didn't write occurrence_id when raising this alarm")
elif not audit_row['occurrence_id']:
    print("❌ ROOT CAUSE: Python code not passing occurrence_id to database")
    print("   Check if HMI restarted with new code")
else:
    print("✅ Fix appears to be working!")

print("=" * 100)

conn.close()
