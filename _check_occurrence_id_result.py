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
cur.execute("""
    SELECT 
        audit_id, event_id, action_type, performed_by, 
        occurrence_id, action_timestamp 
    FROM historian_raw.alarm_audit_trail 
    WHERE event_id = 97934 
    ORDER BY action_timestamp DESC 
    LIMIT 5
""")

rows = cur.fetchall()

print()
print("=" * 100)
print("✅ OCCURRENCE_ID FIX VERIFICATION - Event 97934")
print("=" * 100)
print()

if rows:
    for r in rows:
        occ_status = "✅ POPULATED" if r['occurrence_id'] else "❌ NULL"
        occ_value = str(r['occurrence_id'])[:36] if r['occurrence_id'] else "NULL"
        ts = r['action_timestamp'].strftime('%Y-%m-%d %H:%M:%S')
        
        print(f"Audit {r['audit_id']:5} | {r['action_type']:15} | by: {r['performed_by']:15} | "
              f"{occ_status} {occ_value:38} | {ts}")
    
    # Check the most recent record
    latest = rows[0]
    print()
    print("=" * 100)
    if latest['occurrence_id']:
        print(f"✅ SUCCESS: Latest record has occurrence_id = {latest['occurrence_id']}")
        print(f"   Action: {latest['action_type']} by {latest['performed_by']}")
        print(f"   Time: {latest['action_timestamp']}")
    else:
        print(f"❌ FAILED: Latest record has NULL occurrence_id")
        print(f"   This indicates the fix is not working correctly")
else:
    print("⚠️  No audit records found for event 97934")

print("=" * 100)
print()

conn.close()
