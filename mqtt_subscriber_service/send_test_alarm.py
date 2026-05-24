"""
Simple MQTT Test Publisher - Send sample messages with tag data and alarms
"""
import paho.mqtt.client as mqtt
import json
from datetime import datetime

# MQTT Configuration
MQTT_BROKER = "127.0.0.1"
MQTT_PORT = 1883
TOPIC = "plant/sensors/data"

def format_timestamp_with_ms():
    """Generate ISO 8601 timestamp with milliseconds"""
    now = datetime.utcnow()
    return now.strftime('%Y-%m-%dT%H:%M:%S.') + f"{now.microsecond // 1000:03d}Z"

def create_test_message_with_alarms():
    """Create test message with tag data and alarm_summary"""
    timestamp = format_timestamp_with_ms()
    
    message = {
        "timestamp": timestamp,
        "publishIntervalMs": 1000,
        "tagCount": 3,
        "totalSamples": 3,
        "values": [
            {
                "tagId": "TT_001",
                "value": 95.5,
                "quality": "Good",
                "timestamp": timestamp,
                "dataType": "FLOAT",
                "plcId": "PLC_001"
            },
            {
                "tagId": "PT_001",
                "value": 13.8,
                "quality": "Good",
                "timestamp": timestamp,
                "dataType": "FLOAT",
                "plcId": "PLC_001"
            },
            {
                "tagId": "ST_001",
                "value": 1650,
                "quality": "Good",
                "timestamp": timestamp,
                "dataType": "FLOAT",
                "plcId": "PLC_001"
            }
        ],
        "alarm_summary": {
            "total_alarms": 3,
            "critical_count": 2,
            "warning_count": 1,
            "info_count": 0,
            "alarms": [
                {
                    "tag_id": "TT_001",
                    "severity": 5,  # CRITICAL
                    "event_type": "HIGH_ALARM",
                    "message": "Temperature High Alarm - TT_001 value 95.5°C exceeds critical limit 90°C",
                    "time": timestamp,
                    "metadata": {
                        "current_value": 95.5,
                        "limit": 90.0,
                        "unit": "°C",
                        "acknowledged": False,
                        "state": "ACTIVE"
                    }
                },
                {
                    "tag_id": "PT_001",
                    "severity": 5,  # CRITICAL
                    "event_type": "HIGH_ALARM",
                    "message": "Pressure High Alarm - PT_001 value 13.8 bar exceeds critical limit 13.0 bar",
                    "time": timestamp,
                    "metadata": {
                        "current_value": 13.8,
                        "limit": 13.0,
                        "unit": "bar",
                        "acknowledged": False,
                        "state": "ACTIVE"
                    }
                },
                {
                    "tag_id": "ST_001",
                    "severity": 2,  # WARNING
                    "event_type": "HIGH_ALARM",
                    "message": "Speed High Warning - ST_001 value 1650 rpm exceeds warning limit 1600 rpm",
                    "time": timestamp,
                    "metadata": {
                        "current_value": 1650,
                        "limit": 1600,
                        "unit": "rpm",
                        "acknowledged": False,
                        "state": "ACTIVE"
                    }
                }
            ]
        }
    }
    
    return message

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✅ Connected to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}")
    else:
        print(f"❌ Failed to connect, return code {rc}")

def on_publish(client, userdata, mid):
    print(f"✅ Message published successfully (mid: {mid})")

def main():
    print("=" * 80)
    print("MQTT Test Publisher - Tag Data with Alarms")
    print("=" * 80)
    
    # Create MQTT client
    client = mqtt.Client(client_id="TestAlarmPublisher")
    client.on_connect = on_connect
    client.on_publish = on_publish
    
    try:
        # Connect to broker
        print(f"🔌 Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        
        import time
        time.sleep(1)  # Wait for connection
        
        # Create and publish test message
        print(f"\n📤 Publishing test message to topic: {TOPIC}")
        message = create_test_message_with_alarms()
        
        # Pretty print the message
        print("\n📋 Message Content:")
        print(json.dumps(message, indent=2))
        
        # Publish
        payload = json.dumps(message)
        result = client.publish(TOPIC, payload, qos=1)
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"\n✅ Published {len(payload)} bytes")
            print(f"   - 3 tag values")
            print(f"   - 3 alarms (2 CRITICAL, 1 WARNING)")
        else:
            print(f"\n❌ Publish failed with code: {result.rc}")
        
        time.sleep(2)  # Wait for publish to complete
        
        print("\n" + "=" * 80)
        print("✅ Test complete! Check the MQTT subscriber logs to verify:")
        print("   - Log location: mqtt_subscriber_service/logs/mqtt_subscriber.log")
        print("   - Look for: 'Inserted X alarm events'")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
