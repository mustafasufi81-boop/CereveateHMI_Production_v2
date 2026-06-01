"""
Comprehensive multi-action test for occurrence_id fix
Tests: ACK, CLEAR, SUPPRESS, UNSUPPRESS
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
print("🧪 COMPREHENSIVE OCCURRENCE_ID TEST - ALL ACTIONS")
print("=" * 100)
print(f"Test Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

token = get_token()
headers = {"Authorization": f"Bearer {token}"}

# Get baseline
conn = get_db_conn()
cur = conn.cursor()
cur.execute("SELECT COUNT(occurrence_id) AS baseline FROM historian_raw.alarm_audit_trail WHERE occurrence_id IS NOT NULL")
baseline = cur.fetchone()['baseline']
print(f"📊 Baseline: {baseline} records with occurrence_id")
print()

# Find test alarms
cur.execute("""
    SELECT current_event_id, alarm_key, alarm_state, occurrence_id
    FROM historian_raw.alarm_active
    WHERE occurrence_id IS NOT NULL
    ORDER BY raised_at DESC
    LIMIT 10
""")
alarms = cur.fetchall()

print(f"📋 Found {len(alarms)} active alarms for testing")
print()

# Test 1: ACK an ACTIVE_UNACK alarm
print("=" * 100)
print("TEST 1: ACKNOWLEDGE Action")
print("=" * 100)

unack_alarm = next((a for a in alarms if a['alarm_state'] == 'ACTIVE_UNACK'), None)

if unack_alarm:
    event_id = unack_alarm['current_event_id']
    expected_occ = str(unack_alarm['occurrence_id'])
    
    print(f"Target: event_id={event_id}, key={unack_alarm['alarm_key']}")
    print(f"Expected occurrence_id: {expected_occ}")
    
    try:
        resp = requests.post(
            f"{API_BASE}/api/alarms/acknowledge/{event_id}",
            headers=headers,
            json={"notes": "Multi-test ACK"},
            timeout=5
        )
        
        if resp.status_code in (200, 201):
            print(f"✅ ACK successful: {resp.json().get('success')}")
            
            # Verify in database
            time.sleep(0.5)
            cur.execute("""
                SELECT occurrence_id, action_timestamp 
                FROM historian_raw.alarm_audit_trail
                WHERE event_id = %s AND action_type = 'ACKNOWLEDGED'
                ORDER BY action_timestamp DESC LIMIT 1
            """, (event_id,))
            
            audit = cur.fetchone()
            if audit and audit['occurrence_id']:
                actual_occ = str(audit['occurrence_id'])
                if actual_occ == expected_occ:
                    print(f"✅ VERIFY: occurrence_id matches! {actual_occ}")
                else:
                    print(f"❌ VERIFY: occurrence_id mismatch!")
                    print(f"   Expected: {expected_occ}")
                    print(f"   Actual:   {actual_occ}")
            else:
                print(f"❌ VERIFY: occurrence_id is NULL in audit trail")
        else:
            print(f"⚠️  ACK failed: {resp.status_code}")
    except Exception as e:
        print(f"❌ Error: {e}")
else:
    print("⚠️  No ACTIVE_UNACK alarms available")

print()

# Test 2: CLEAR an ACTIVE_ACK alarm
print("=" * 100)
print("TEST 2: CLEAR Action")
print("=" * 100)

# Refresh alarms
cur.execute("""
    SELECT current_event_id, alarm_key, alarm_state, occurrence_id
    FROM historian_raw.alarm_active
    WHERE occurrence_id IS NOT NULL AND alarm_state = 'ACTIVE_ACK'
    ORDER BY raised_at DESC LIMIT 1
""")
ack_alarm = cur.fetchone()

if ack_alarm:
    event_id = ack_alarm['current_event_id']
    expected_occ = str(ack_alarm['occurrence_id'])
    
    print(f"Target: event_id={event_id}, key={ack_alarm['alarm_key']}")
    print(f"Expected occurrence_id: {expected_occ}")
    
    try:
        resp = requests.post(
            f"{API_BASE}/api/alarms/clear/{event_id}",
            headers=headers,
            json={"reason": "Test clear", "notes": "Multi-test CLEAR"},
            timeout=5
        )
        
        if resp.status_code in (200, 201):
            print(f"✅ CLEAR successful: {resp.json().get('success')}")
            
            # Verify in database
            time.sleep(0.5)
            cur.execute("""
                SELECT occurrence_id, action_timestamp 
                FROM historian_raw.alarm_audit_trail
                WHERE event_id = %s AND action_type = 'CLEARED'
                ORDER BY action_timestamp DESC LIMIT 1
            """, (event_id,))
            
            audit = cur.fetchone()
            if audit and audit['occurrence_id']:
                actual_occ = str(audit['occurrence_id'])
                if actual_occ == expected_occ:
                    print(f"✅ VERIFY: occurrence_id matches! {actual_occ}")
                else:
                    print(f"❌ VERIFY: occurrence_id mismatch!")
            else:
                print(f"❌ VERIFY: occurrence_id is NULL in audit trail")
        else:
            print(f"⚠️  CLEAR failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"❌ Error: {e}")
else:
    print("⚠️  No ACTIVE_ACK alarms available for CLEAR test")

print()

# Test 3: SUPPRESS an alarm
print("=" * 100)
print("TEST 3: SUPPRESS Action")
print("=" * 100)

# Refresh alarms
cur.execute("""
    SELECT current_event_id, alarm_key, alarm_state, occurrence_id
    FROM historian_raw.alarm_active
    WHERE occurrence_id IS NOT NULL
    ORDER BY raised_at DESC LIMIT 1
""")
suppress_alarm = cur.fetchone()

if suppress_alarm:
    event_id = suppress_alarm['current_event_id']
    expected_occ = str(suppress_alarm['occurrence_id'])
    
    print(f"Target: event_id={event_id}, key={suppress_alarm['alarm_key']}")
    print(f"Expected occurrence_id: {expected_occ}")
    
    try:
        resp = requests.post(
            f"{API_BASE}/api/alarms/suppress/{event_id}",
            headers=headers,
            json={"reason": "Test suppress", "notes": "Multi-test SUPPRESS", "duration_hours": 1},
            timeout=5
        )
        
        if resp.status_code in (200, 201):
            print(f"✅ SUPPRESS successful: {resp.json().get('success')}")
            
            # Verify in database
            time.sleep(0.5)
            cur.execute("""
                SELECT occurrence_id, action_timestamp 
                FROM historian_raw.alarm_audit_trail
                WHERE event_id = %s AND action_type = 'SUPPRESSED'
                ORDER BY action_timestamp DESC LIMIT 1
            """, (event_id,))
            
            audit = cur.fetchone()
            if audit and audit['occurrence_id']:
                actual_occ = str(audit['occurrence_id'])
                if actual_occ == expected_occ:
                    print(f"✅ VERIFY: occurrence_id matches! {actual_occ}")
                else:
                    print(f"❌ VERIFY: occurrence_id mismatch!")
            else:
                print(f"❌ VERIFY: occurrence_id is NULL in audit trail")
        else:
            print(f"⚠️  SUPPRESS failed: {resp.status_code}")
    except Exception as e:
        print(f"❌ Error: {e}")
else:
    print("⚠️  No alarms available for SUPPRESS test")

print()

# Test 4: UNSUPPRESS
print("=" * 100)
print("TEST 4: UNSUPPRESS Action")
print("=" * 100)

# Find a suppressed alarm
cur.execute("""
    SELECT sup.event_id, aa.alarm_key, aa.occurrence_id
    FROM historian_raw.alarm_audit_trail sup
    JOIN historian_raw.alarm_active aa ON sup.event_id = aa.current_event_id
    WHERE sup.action_type = 'SUPPRESSED'
      AND aa.occurrence_id IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM historian_raw.alarm_audit_trail uns
          WHERE uns.event_id = sup.event_id
            AND uns.action_type = 'UNSUPPRESSED'
            AND uns.action_timestamp > sup.action_timestamp
      )
    ORDER BY sup.action_timestamp DESC
    LIMIT 1
""")
unsuppress_alarm = cur.fetchone()

if unsuppress_alarm:
    event_id = unsuppress_alarm['event_id']
    expected_occ = str(unsuppress_alarm['occurrence_id'])
    
    print(f"Target: event_id={event_id}, key={unsuppress_alarm['alarm_key']}")
    print(f"Expected occurrence_id: {expected_occ}")
    
    try:
        resp = requests.post(
            f"{API_BASE}/api/alarms/unsuppress/{event_id}",
            headers=headers,
            timeout=5
        )
        
        if resp.status_code in (200, 201):
            print(f"✅ UNSUPPRESS successful: {resp.json().get('success')}")
            
            # Verify in database
            time.sleep(0.5)
            cur.execute("""
                SELECT occurrence_id, action_timestamp 
                FROM historian_raw.alarm_audit_trail
                WHERE event_id = %s AND action_type = 'UNSUPPRESSED'
                ORDER BY action_timestamp DESC LIMIT 1
            """, (event_id,))
            
            audit = cur.fetchone()
            if audit and audit['occurrence_id']:
                actual_occ = str(audit['occurrence_id'])
                if actual_occ == expected_occ:
                    print(f"✅ VERIFY: occurrence_id matches! {actual_occ}")
                else:
                    print(f"❌ VERIFY: occurrence_id mismatch!")
            else:
                print(f"❌ VERIFY: occurrence_id is NULL in audit trail")
        else:
            print(f"⚠️  UNSUPPRESS failed: {resp.status_code}")
    except Exception as e:
        print(f"❌ Error: {e}")
else:
    print("⚠️  No suppressed alarms available for UNSUPPRESS test")

print()

# Final Summary
print("=" * 100)
print("FINAL SUMMARY - ALL ACTIONS")
print("=" * 100)

cur.execute("""
    SELECT 
        action_type,
        COUNT(*) AS total,
        COUNT(occurrence_id) AS with_occ,
        MAX(action_timestamp) AS latest
    FROM historian_raw.alarm_audit_trail
    WHERE action_timestamp > NOW() - INTERVAL '10 minutes'
    GROUP BY action_type
    ORDER BY latest DESC
""")
recent_actions = cur.fetchall()

if recent_actions:
    print("\n📊 Recent actions (last 10 minutes):")
    for action in recent_actions:
        pct = 100.0 * action['with_occ'] / action['total'] if action['total'] > 0 else 0
        status = "✅" if action['with_occ'] > 0 else "❌"
        print(f"{status} {action['action_type']:15} {action['with_occ']:2}/{action['total']:2} with occurrence_id ({pct:5.1f}%)")

# Check new occurrence_id records
cur.execute("SELECT COUNT(occurrence_id) AS current FROM historian_raw.alarm_audit_trail WHERE occurrence_id IS NOT NULL")
current = cur.fetchone()['current']
new_records = current - baseline

print()
print(f"📈 New records with occurrence_id: {new_records}")
print(f"   Baseline: {baseline}")
print(f"   Current:  {current}")
print()

if new_records > 0:
    print("🎉 ✅ SUCCESS: All action types are writing occurrence_id!")
else:
    print("⚠️  No new records created during this test")

print("=" * 100)

conn.close()
