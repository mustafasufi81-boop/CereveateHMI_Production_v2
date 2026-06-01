"""
Test CLEAR action specifically by ACKing then CLEARing an alarm
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import requests
import time
from datetime import datetime

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'Automation_DB',
    'user': 'cereveate',
    'password': 'cereveate@222'
}

API_BASE = "http://localhost:8090"

def get_token():
    resp = requests.post(
        f"{API_BASE}/api/auth/login",
        json={"username": "admin", "password": "admin123"},
        timeout=5
    )
    return resp.json().get('access_token')

def get_db_conn():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)

print()
print("=" * 100)
print("🧪 CLEAR ACTION TEST - Full Workflow")
print("=" * 100)
print(f"Test Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

token = get_token()
headers = {"Authorization": f"Bearer {token}"}

conn = get_db_conn()
cur = conn.cursor()

# Step 1: Find an ACTIVE_UNACK alarm
print("STEP 1: Find ACTIVE_UNACK alarm")
print("-" * 100)

cur.execute("""
    SELECT current_event_id, alarm_key, alarm_state, occurrence_id
    FROM historian_raw.alarm_active
    WHERE occurrence_id IS NOT NULL 
      AND alarm_state = 'ACTIVE_UNACK'
    ORDER BY raised_at DESC
    LIMIT 1
""")
unack_alarm = cur.fetchone()

if not unack_alarm:
    print("❌ No ACTIVE_UNACK alarms available")
    exit(1)

event_id = unack_alarm['current_event_id']
expected_occ = str(unack_alarm['occurrence_id'])

print(f"✅ Found alarm:")
print(f"   Event ID: {event_id}")
print(f"   Key: {unack_alarm['alarm_key']}")
print(f"   State: {unack_alarm['alarm_state']}")
print(f"   Occurrence ID: {expected_occ}")
print()

# Step 2: ACK the alarm
print("STEP 2: ACKNOWLEDGE alarm")
print("-" * 100)

try:
    resp = requests.post(
        f"{API_BASE}/api/alarms/acknowledge/{event_id}",
        headers=headers,
        json={"notes": "ACK for CLEAR test"},
        timeout=5
    )
    
    if resp.status_code in (200, 201):
        print(f"✅ ACK successful")
        time.sleep(0.5)
        
        # Verify ACK wrote occurrence_id
        cur.execute("""
            SELECT occurrence_id 
            FROM historian_raw.alarm_audit_trail
            WHERE event_id = %s AND action_type = 'ACKNOWLEDGED'
            ORDER BY action_timestamp DESC LIMIT 1
        """, (event_id,))
        
        ack_audit = cur.fetchone()
        if ack_audit and ack_audit['occurrence_id']:
            actual_occ = str(ack_audit['occurrence_id'])
            if actual_occ == expected_occ:
                print(f"✅ ACK audit has correct occurrence_id: {actual_occ}")
            else:
                print(f"⚠️  ACK audit occurrence_id mismatch!")
        else:
            print(f"❌ ACK audit missing occurrence_id")
            exit(1)
    else:
        print(f"❌ ACK failed: {resp.status_code}")
        exit(1)
except Exception as e:
    print(f"❌ Error during ACK: {e}")
    exit(1)

print()

# Step 3: Verify alarm is now ACTIVE_ACK
print("STEP 3: Verify alarm state changed to ACTIVE_ACK")
print("-" * 100)

cur.execute("""
    SELECT alarm_state
    FROM historian_raw.alarm_active
    WHERE current_event_id = %s
""", (event_id,))
current_state = cur.fetchone()

if current_state and current_state['alarm_state'] == 'ACTIVE_ACK':
    print(f"✅ Alarm state is now: {current_state['alarm_state']}")
else:
    print(f"⚠️  Unexpected state: {current_state['alarm_state'] if current_state else 'NOT FOUND'}")

print()

# Step 4: CLEAR the alarm
print("STEP 4: CLEAR alarm")
print("-" * 100)

try:
    resp = requests.post(
        f"{API_BASE}/api/alarms/clear/{event_id}",
        headers=headers,
        json={"reason": "Normal return", "notes": "CLEAR test"},
        timeout=5
    )
    
    if resp.status_code in (200, 201):
        print(f"✅ CLEAR successful: {resp.json().get('success')}")
        time.sleep(0.5)
        
        # Verify CLEAR wrote occurrence_id
        cur.execute("""
            SELECT occurrence_id, action_timestamp
            FROM historian_raw.alarm_audit_trail
            WHERE event_id = %s AND action_type = 'CLEARED'
            ORDER BY action_timestamp DESC LIMIT 1
        """, (event_id,))
        
        clear_audit = cur.fetchone()
        if clear_audit and clear_audit['occurrence_id']:
            actual_occ = str(clear_audit['occurrence_id'])
            if actual_occ == expected_occ:
                print(f"✅ CLEAR audit has correct occurrence_id: {actual_occ}")
                print(f"   Timestamp: {clear_audit['action_timestamp']}")
            else:
                print(f"❌ CLEAR audit occurrence_id mismatch!")
                print(f"   Expected: {expected_occ}")
                print(f"   Actual:   {actual_occ}")
        else:
            print(f"❌ CLEAR audit missing occurrence_id")
    else:
        print(f"❌ CLEAR failed: {resp.status_code}")
        print(f"   Response: {resp.text}")
except Exception as e:
    print(f"❌ Error during CLEAR: {e}")

print()

# Final verification
print("=" * 100)
print("FINAL VERIFICATION - Full Workflow")
print("=" * 100)

cur.execute("""
    SELECT action_type, occurrence_id, action_timestamp, operator_notes
    FROM historian_raw.alarm_audit_trail
    WHERE event_id = %s
    ORDER BY action_timestamp DESC
    LIMIT 5
""", (event_id,))

audit_history = cur.fetchall()

print(f"\n📋 Complete audit trail for event {event_id}:")
for record in audit_history:
    occ_status = "✅" if record['occurrence_id'] else "❌"
    occ_display = str(record['occurrence_id'])[:36] if record['occurrence_id'] else "NULL"
    print(f"{occ_status} {record['action_type']:15} {occ_display:36} {record['action_timestamp']}")

# Summary
print()
print("=" * 100)
print("TEST RESULT SUMMARY")
print("=" * 100)

cur.execute("""
    SELECT 
        COUNT(*) FILTER (WHERE action_type = 'ACKNOWLEDGED') AS ack_count,
        COUNT(*) FILTER (WHERE action_type = 'ACKNOWLEDGED' AND occurrence_id IS NOT NULL) AS ack_with_occ,
        COUNT(*) FILTER (WHERE action_type = 'CLEARED') AS clear_count,
        COUNT(*) FILTER (WHERE action_type = 'CLEARED' AND occurrence_id IS NOT NULL) AS clear_with_occ
    FROM historian_raw.alarm_audit_trail
    WHERE event_id = %s
""", (event_id,))

summary = cur.fetchone()

print(f"\nFor event {event_id}:")
print(f"  ACK records:   {summary['ack_with_occ']}/{summary['ack_count']} with occurrence_id")
print(f"  CLEAR records: {summary['clear_with_occ']}/{summary['clear_count']} with occurrence_id")
print()

if summary['clear_with_occ'] > 0:
    print("🎉 ✅ SUCCESS: CLEAR action is writing occurrence_id!")
else:
    print("❌ FAIL: CLEAR action not writing occurrence_id")

print("=" * 100)

conn.close()
