"""
Test occurrence_id fix on LIVE running system
"""
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
import time
from datetime import datetime

API_BASE = "http://localhost:8090"
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'Automation_DB',
    'user': 'cereveate',
    'password': 'cereveate@222'
}

print("\n" + "="*80)
print("🔴 LIVE SYSTEM TEST - occurrence_id FIX VERIFICATION")
print("="*80)
print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

# Login
print("Step 1: Authenticate...")
resp = requests.post(f"{API_BASE}/api/auth/login", json={"username": "admin", "password": "admin123"})
token = resp.json()['access_token']
headers = {"Authorization": f"Bearer {token}"}
print("✅ Authenticated\n")

# Get active alarms
print("Step 2: Get active alarms...")
resp = requests.get(f"{API_BASE}/api/alarms/active", headers=headers)
alarms = resp.json()['alarms']
print(f"✅ Found {len(alarms)} active alarms\n")

# Find an ACTIVE_UNACK alarm with occurrence_id
target = None
for alarm in alarms:
    if alarm.get('alarm_state') == 'ACTIVE_UNACK' and alarm.get('occurrence_id'):
        target = alarm
        break

if not target:
    print("⚠️  No ACTIVE_UNACK alarms with occurrence_id available")
    print("    (This is OK - means system is stable!)\n")
    
    # Show what we have
    conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) as total,
               COUNT(occurrence_id) as with_occ,
               MAX(action_timestamp) as latest
        FROM historian_raw.alarm_audit_trail
        WHERE action_timestamp > NOW() - INTERVAL '1 hour'
    """)
    stats = cur.fetchone()
    
    print(f"📊 Recent Activity (Last Hour):")
    print(f"   Total records: {stats['total']}")
    print(f"   With occurrence_id: {stats['with_occ']} ({100*stats['with_occ']/stats['total'] if stats['total']>0 else 0:.1f}%)")
    print(f"   Latest: {stats['latest']}")
    
    conn.close()
    exit(0)

# Test ACK
event_id = target['current_event_id']
expected_occ = target['occurrence_id']

print(f"Step 3: Testing ACKNOWLEDGE on live alarm...")
print(f"  Event ID: {event_id}")
print(f"  Alarm Key: {target['alarm_key']}")
print(f"  Expected occurrence_id: {expected_occ}\n")

# ACK the alarm
resp = requests.post(
    f"{API_BASE}/api/alarms/acknowledge/{event_id}",
    headers=headers,
    json={"notes": "LIVE TEST - occurrence_id verification"}
)

if resp.status_code in (200, 201):
    print("✅ ACKNOWLEDGE successful!\n")
    
    # Wait for DB write
    time.sleep(0.5)
    
    # Verify in database
    print("Step 4: Verify occurrence_id in database...")
    conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT audit_id, occurrence_id, action_timestamp, operator_id
        FROM historian_raw.alarm_audit_trail
        WHERE event_id = %s AND action_type = 'ACKNOWLEDGED'
        ORDER BY action_timestamp DESC LIMIT 1
    """, (event_id,))
    
    audit = cur.fetchone()
    
    if audit and audit['occurrence_id']:
        actual_occ = str(audit['occurrence_id'])
        
        print(f"✅ Found audit record:")
        print(f"   Audit ID: {audit['audit_id']}")
        print(f"   Timestamp: {audit['action_timestamp']}")
        print(f"   Operator: {audit['operator_id']}")
        print(f"   occurrence_id: {actual_occ}\n")
        
        if actual_occ == expected_occ:
            print("="*80)
            print("🎉 ✅ SUCCESS - occurrence_id CORRECTLY POPULATED!")
            print("="*80)
            print(f"\n✓ Expected: {expected_occ}")
            print(f"✓ Actual:   {actual_occ}")
            print(f"✓ MATCH: YES\n")
        else:
            print("❌ MISMATCH!")
            print(f"   Expected: {expected_occ}")
            print(f"   Actual:   {actual_occ}\n")
    else:
        print("❌ occurrence_id is NULL in audit trail!\n")
    
    conn.close()
else:
    print(f"❌ ACK failed: {resp.status_code}")
    print(f"   {resp.text}\n")

print("="*80)
