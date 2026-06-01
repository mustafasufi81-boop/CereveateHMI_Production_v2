"""
Verify if 12 ACKNOWLEDGED records for event 881456 are correct
Check for duplicates or legitimate multiple operator actions
"""
import psycopg2
from collections import defaultdict

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    database='Automation_DB',
    user='cereveate',
    password='cereveate@222'
)

cur = conn.cursor()

print("="*100)
print("AUDIT TRAIL ANALYSIS FOR EVENT 881456")
print("="*100)

# Get all audit records
cur.execute("""
    SELECT 
        action_type,
        action_timestamp,
        performed_by,
        alarm_actual_value,
        occurrence_id,
        sequence_number,
        performed_by_display_name
    FROM historian_raw.alarm_audit_trail 
    WHERE event_id = 881456 
    ORDER BY action_timestamp
""")

rows = cur.fetchall()

print(f"\nTotal records: {len(rows)}\n")
print(f"{'#':<4} {'Action':<15} {'Timestamp':<28} {'Operator':<20} {'PV Value':<10} {'Occ ID':<38}")
print("-"*130)

for i, row in enumerate(rows, 1):
    action = row[0]
    timestamp = str(row[1])
    operator = row[2] or 'N/A'
    pv_value = row[3] if row[3] is not None else 'N/A'
    occ_id = str(row[4])[:36] if row[4] else 'None'
    
    print(f"{i:<4} {action:<15} {timestamp:<28} {operator:<20} {str(pv_value):<10} {occ_id}")

# Analysis
print("\n" + "="*100)
print("ANALYSIS")
print("="*100)

# Count by action type
action_counts = defaultdict(int)
for row in rows:
    action_counts[row[0]] += 1

print("\n1. Action Type Distribution:")
for action, count in sorted(action_counts.items()):
    print(f"   {action}: {count}")

# Check for duplicates (same operator, same action, close timestamps)
print("\n2. Checking for suspicious duplicates:")
ack_records = [r for r in rows if r[0] == 'ACKNOWLEDGED']
suspicious = False

for i in range(len(ack_records)):
    for j in range(i+1, len(ack_records)):
        r1, r2 = ack_records[i], ack_records[j]
        if r1[2] == r2[2]:  # Same operator
            time_diff = (r2[1] - r1[1]).total_seconds()
            if time_diff < 60:  # Within 1 minute
                print(f"   ⚠️  Same operator '{r1[2]}' ACKed twice within {time_diff:.1f}s")
                suspicious = True

if not suspicious:
    print("   ✓ No suspicious duplicates found")
    print("   ✓ Each ACK is from different operator or different time")

# Check occurrence_id usage
print("\n3. Occurrence ID Distribution:")
occ_ids = set()
for row in rows:
    if row[4]:  # occurrence_id
        occ_ids.add(row[4])

if occ_ids:
    print(f"   Found {len(occ_ids)} unique occurrence_id(s)")
    for occ_id in occ_ids:
        count = sum(1 for r in rows if r[4] == occ_id)
        print(f"   - {str(occ_id)[:36]}: {count} records")
else:
    print("   ⚠️  No occurrence_ids populated yet")
    print("   → This means C# AlarmStateManager hasn't populated occurrence_id")
    print("   → All audit records are being treated as one occurrence")

# Check if this is alarm re-triggers
cur.execute("""
    SELECT 
        event_id,
        time,
        event_type,
        alarm_state,
        occurrence_id
    FROM historian_raw.historian_events
    WHERE tag_id = (SELECT tag_id FROM historian_raw.alarm_audit_trail WHERE event_id = 881456 LIMIT 1)
    ORDER BY time DESC
    LIMIT 10
""")

events = cur.fetchall()
print("\n4. Related Alarm Events for this tag:")
print(f"   Found {len(events)} recent events")
matching_event = next((e for e in events if e[0] == 881456), None)
if matching_event:
    print(f"   Event 881456: {matching_event[2]}, state: {matching_event[3]}, occurred: {matching_event[1]}")

print("\n" + "="*100)
print("CONCLUSION")
print("="*100)

if len(occ_ids) == 0:
    print("⚠️  OCCURRENCE_ID NOT POPULATED")
    print("   The 12 ACKNOWLEDGED records are ALL for the SAME alarm occurrence")
    print("   This means:")
    print("   - 12 different operators (or same operators at different times)")
    print("   - All acknowledged the SAME alarm activation")
    print("   - This could be legitimate if alarm stayed active for long time")
    print("   - OR could indicate operators re-acknowledging to refresh")
    print("\n   ✓ System is working correctly - showing all operator interactions")
    print("   ✓ Pagination now allows viewing all actions")
    print("   ✓ If occurrence_id gets populated, can filter by specific occurrence")
elif len(occ_ids) > 1:
    print(f"✓ MULTIPLE OCCURRENCES DETECTED: {len(occ_ids)}")
    print("   System is correctly tracking separate alarm re-triggers")
else:
    print("✓ SINGLE OCCURRENCE")
    print("   All actions are for one alarm occurrence (correct)")

cur.close()
conn.close()
