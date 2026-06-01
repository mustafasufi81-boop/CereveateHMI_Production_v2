"""
Alarm ACK Regression Bug — Live Test Script
============================================

This script simulates the exact scenario that causes ACK regression:
1. High alarm is raised
2. Operator acknowledges it
3. HighHigh alarm is raised (escalation)
4. Bug: High alarm's ACK is stripped off by WebSocket event

Requirements:
- Flask HMI running on :6001
- Mosquitto MQTT broker running on :1883
- React frontend running on :8090
"""

import time
import json
import requests
import paho.mqtt.client as mqtt
from datetime import datetime

# Configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
FLASK_API = "http://localhost:6001"
TAG_ID = "PY1105G"  # Use real tag from system (has both High and HighHigh setpoints)

# MQTT client setup
mqtt_client = mqtt.Client()

def publish_alarm(level, value, setpoint, transition="RAISED"):
    """Publish alarm event to opc/alarms/events topic"""
    priority_map = {"HighHigh": 5, "High": 4, "Low": 3, "LowLow": 2}
    
    payload = {
        "tag_id": TAG_ID,
        "level": level,
        "state": "ACTIVE" if transition == "RAISED" else "RTN",
        "transition": transition,
        "value": value,
        "setpoint": setpoint,
        "priority": priority_map.get(level, 3),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "raised_at": datetime.utcnow().isoformat() + "Z",
        "event_id": int(time.time() * 1000)
    }
    
    mqtt_client.publish("opc/alarms/events", json.dumps(payload))
    print(f"\n📡 MQTT → {level} alarm {transition}: {value} > {setpoint}")
    return payload

def get_active_alarms():
    """Fetch current active alarms from Flask API"""
    try:
        response = requests.get(f"{FLASK_API}/api/alarms/active", timeout=5)
        if response.ok:
            data = response.json()
            return data.get("alarms", [])
    except Exception as e:
        print(f"❌ Failed to fetch alarms: {e}")
    return []

def acknowledge_alarm(alarm_id, username="test_operator"):
    """Send ACK request to Flask API"""
    try:
        response = requests.post(
            f"{FLASK_API}/api/alarms/acknowledge/{alarm_id}?user={username}",
            json={"notes": "Test ACK"},
            timeout=5
        )
        if response.ok:
            print(f"✅ ACK sent for alarm {alarm_id}")
            return response.json()
        else:
            print(f"❌ ACK failed: {response.status_code} {response.text}")
    except Exception as e:
        print(f"❌ ACK request error: {e}")
    return None

def display_alarm_state(alarms, step_name):
    """Pretty-print current alarm state"""
    print(f"\n{'='*70}")
    print(f"STATE: {step_name}")
    print(f"{'='*70}")
    
    if not alarms:
        print("  (no active alarms)")
        return
    
    for alarm in alarms:
        tag = alarm.get("tag_id", "???")
        level = alarm.get("alarm_level", "???")
        state = alarm.get("alarm_state", "???")
        value = alarm.get("alarm_actual_value", "?")
        sp = alarm.get("alarm_setpoint", "?")
        ack_by = alarm.get("acknowledged_by", "")
        ack_at = alarm.get("acknowledged_at", "")
        
        state_icon = "✓" if state == "ACTIVE_ACK" else "❌" if state == "ACTIVE_UNACK" else "?"
        
        print(f"  {state_icon} {tag} | {level} | {value} > {sp} | {state}")
        if ack_by:
            print(f"      └─ ACK: {ack_by} @ {ack_at}")

def run_test():
    """Execute the bug reproduction test"""
    print("\n" + "="*70)
    print("ALARM ACK REGRESSION BUG — LIVE TEST")
    print("="*70)
    
    # Connect to MQTT broker
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
        print(f"✅ Connected to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}")
    except Exception as e:
        print(f"❌ MQTT connection failed: {e}")
        return
    
    time.sleep(1)  # Let MQTT settle
    
    # ============================================================
    # STEP 1: Raise High alarm
    # ============================================================
    print("\n" + "─"*70)
    print("STEP 1: Raise High alarm (value=105, setpoint=100)")
    print("─"*70)
    
    publish_alarm("High", 105, 100, "RAISED")
    time.sleep(3)  # Wait for WebSocket + REST poll + DB insert
    
    alarms = get_active_alarms()
    # Filter to only our test tag
    test_alarms = [a for a in alarms if a.get("tag_id") == TAG_ID]
    display_alarm_state(test_alarms, "After High Alarm Raised")
    
    # Find the High alarm
    high_alarm = next((a for a in test_alarms if a.get("alarm_level") == "High"), None)
    
    if not high_alarm:
        print("\n❌ TEST FAILED: High alarm not found in active alarms")
        mqtt_client.loop_stop()
        return
    
    if high_alarm.get("alarm_state") != "ACTIVE_UNACK":
        print(f"\n⚠️  UNEXPECTED: High alarm state is {high_alarm.get('alarm_state')}, expected ACTIVE_UNACK")
    else:
        print("\n✅ PASS: High alarm is ACTIVE_UNACK")
    
    alarm_id = high_alarm.get("id")
    
    # ============================================================
    # STEP 2: Operator acknowledges High alarm
    # ============================================================
    print("\n" + "─"*70)
    print(f"STEP 2: Operator acknowledges High alarm (id={alarm_id})")
    print("─"*70)
    
    ack_result = acknowledge_alarm(alarm_id)
    time.sleep(3)  # Wait for ACK to propagate
    
    alarms = get_active_alarms()
    test_alarms = [a for a in alarms if a.get("tag_id") == TAG_ID]
    display_alarm_state(test_alarms, "After High Alarm Acknowledged")
    
    high_alarm = next((a for a in test_alarms if a.get("alarm_level") == "High"), None)
    
    if not high_alarm:
        print("\n❌ TEST FAILED: High alarm disappeared after ACK")
        mqtt_client.loop_stop()
        return
    
    if high_alarm.get("alarm_state") != "ACTIVE_ACK":
        print(f"\n⚠️  UNEXPECTED: High alarm state is {high_alarm.get('alarm_state')}, expected ACTIVE_ACK")
    else:
        print("\n✅ PASS: High alarm is ACTIVE_ACK")
    
    # ============================================================
    # STEP 3: Escalate to HighHigh (BUG TRIGGER)
    # ============================================================
    print("\n" + "─"*70)
    print("STEP 3: Value rises to 125 → HighHigh alarm (BUG TRIGGER)")
    print("─"*70)
    
    publish_alarm("HighHigh", 125, 120, "RAISED")
    
    # Wait 1 second — this is BEFORE the next REST poll (5s interval)
    # so we'll catch the bug if WebSocket event stripped the ACK
    time.sleep(1)
    
    alarms = get_active_alarms()
    test_alarms = [a for a in alarms if a.get("tag_id") == TAG_ID]
    display_alarm_state(test_alarms, "1 Second After HighHigh (Before REST Poll)")
    
    high_alarm = next((a for a in test_alarms if a.get("alarm_level") == "High"), None)
    highhigh_alarm = next((a for a in test_alarms if a.get("alarm_level") == "HighHigh"), None)
    
    # ============================================================
    # VERIFICATION (This is where we catch the bug)
    # ============================================================
    print("\n" + "="*70)
    print("VERIFICATION RESULTS")
    print("="*70)
    
    test_passed = True
    
    # Check 1: High alarm should still be ACTIVE_ACK
    if high_alarm:
        if high_alarm.get("alarm_state") == "ACTIVE_ACK":
            print("✅ PASS: High alarm retained ACTIVE_ACK state")
        else:
            print(f"❌ BUG DETECTED: High alarm regressed to {high_alarm.get('alarm_state')}")
            print("   Expected: ACTIVE_ACK")
            print("   Actual: ACTIVE_UNACK (ACK was stripped by WebSocket event)")
            test_passed = False
    else:
        print("⚠️  UNEXPECTED: High alarm disappeared")
        test_passed = False
    
    # Check 2: HighHigh alarm should be created as separate card
    if highhigh_alarm:
        print(f"✅ PASS: HighHigh alarm created as separate card (state={highhigh_alarm.get('alarm_state')})")
    else:
        print("❌ FAIL: HighHigh alarm not created (event consumed by wrong match)")
        test_passed = False
    
    # Wait for REST poll to repair (if bug exists)
    print("\n" + "─"*70)
    print("Waiting 5 seconds for REST poll to repair state...")
    print("─"*70)
    time.sleep(5)
    
    alarms = get_active_alarms()
    test_alarms = [a for a in alarms if a.get("tag_id") == TAG_ID]
    display_alarm_state(test_alarms, "After REST Poll Repair")
    
    high_alarm = next((a for a in test_alarms if a.get("alarm_level") == "High"), None)
    
    if high_alarm and high_alarm.get("alarm_state") == "ACTIVE_ACK":
        print("\n✅ REST poll restored ACTIVE_ACK (bug was temporarily visible)")
    
    # ============================================================
    # FINAL RESULT
    # ============================================================
    print("\n" + "="*70)
    if test_passed:
        print("✅ TEST PASSED — No ACK regression detected")
    else:
        print("❌ TEST FAILED — ACK REGRESSION BUG CONFIRMED")
        print("\nBug details:")
        print("  - handleRealtimeAlarm matches by tag_id only (no level check)")
        print("  - WebSocket event blindly overwrites alarm_state")
        print("  - No ACK regression guard on WebSocket path")
        print("  - REST poll repairs it 5 seconds later")
    print("="*70)
    
    # Cleanup
    mqtt_client.loop_stop()
    mqtt_client.disconnect()

if __name__ == "__main__":
    run_test()
