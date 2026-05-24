"""
Simple OPC Data Publisher using latest_sample_mqtt_data.json format
Publishes to test/gateway/data topic
"""
import paho.mqtt.client as mqtt
import json
from datetime import datetime
import time

# MQTT Configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
TOPIC = "test/gateway/data"
QOS = 1

def create_opc_message():
    """Create OPC message based on latest_sample_mqtt_data.json format"""
    
    timestamp = datetime.utcnow().isoformat() + "Z"
    
    # Create message matching the expected format with tag_id and value fields
    message = {
        "timestamp": timestamp,
        "publishIntervalMs": 1000,
        "tagCount": 10,
        "totalSamples": 10,
        "values": [
            {
                "plcId": "Rockwel_PLC_001",
                "tag_id": "TEST.Blastfurnace_Tuyer1_Pressure",  # Changed 'tag' to 'tag_id'
                "address": "Blastfurnace_Tuyer1_Pressure",
                "dataType": "float",
                "value_num": 22.21,  # Using value_num for numeric values
                "quality": "Good",
                "timestamp": timestamp
            },
            {
                "plcId": "Rockwel_PLC_001",
                "tag_id": "TEST.Boiler_Inlet_Pressure",
                "address": "Boiler_Inlet_Pressure",
                "dataType": "float",
                "value_num": 7.89,
                "quality": "Good",
                "timestamp": timestamp
            },
            {
                "plcId": "Rockwel_PLC_001",
                "tag_id": "TEST.Boiler_Inlet_Temp",
                "address": "Boiler_Inlet_Temp",
                "dataType": "float",
                "value_num": 70.95,
                "quality": "Good",
                "timestamp": timestamp
            },
            {
                "plcId": "Rockwel_PLC_001",
                "tag_id": "TEST.Cooling_FAN_SPEED",
                "address": "Cooling_FAN_SPEED",
                "dataType": "float",
                "value_num": 65.85,
                "quality": "Good",
                "timestamp": timestamp
            },
            {
                "plcId": "Rockwel_PLC_001",
                "tag_id": "TEST.Motor_Running_Status",
                "address": "Motor_Running_Status",
                "dataType": "boolean",
                "value_bool": True,  # Using value_bool for boolean
                "quality": "Good",
                "timestamp": timestamp
            },
            {
                "plcId": "Rockwel_PLC_001",
                "tag_id": "TEST.Production_Rate",
                "address": "Production_Rate",
                "dataType": "float",
                "value_num": 150.5,
                "quality": "Good",
                "timestamp": timestamp
            },
            {
                "plcId": "Rockwel_PLC_001",
                "tag_id": "TEST.Tank_Level",
                "address": "Tank_Level",
                "dataType": "float",
                "value_num": 75.3,
                "quality": "Good",
                "timestamp": timestamp
            },
            {
                "plcId": "Rockwel_PLC_001",
                "tag_id": "TEST.Valve_Position",
                "address": "Valve_Position",
                "dataType": "float",
                "value_num": 45.2,
                "quality": "Good",
                "timestamp": timestamp
            },
            {
                "plcId": "Rockwel_PLC_001",
                "tag_id": "TEST.Alarm_Status",
                "address": "Alarm_Status",
                "dataType": "text",
                "value_text": "NORMAL",  # Using value_text for string
                "quality": "Good",
                "timestamp": timestamp
            },
            {
                "plcId": "Rockwel_PLC_001",
                "tag_id": "TEST.Pump_Speed_RPM",
                "address": "Pump_Speed_RPM",
                "dataType": "float",
                "value_num": 1500.0,
                "quality": "Good",
                "timestamp": timestamp
            }
        ]
    }
    
    return message

def publish_test_data(num_messages=5):
    """Publish test OPC data to MQTT broker"""
    
    print("=" * 80)
    print("🔬 OPC DATA TEST PUBLISHER")
    print("=" * 80)
    print(f"Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"Topic: {TOPIC}")
    print(f"QoS: {QOS}")
    print(f"Messages to send: {num_messages}")
    print("=" * 80 + "\n")
    
    try:
        # Connect to MQTT broker
        client = mqtt.Client("opc_test_publisher")
        print("Connecting to MQTT broker...")
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        print("✅ Connected to MQTT broker\n")
        
        # Publish messages
        for i in range(1, num_messages + 1):
            message = create_opc_message()
            payload = json.dumps(message, indent=2)
            
            print(f"📤 Publishing message {i}/{num_messages}...")
            print(f"   Timestamp: {message['timestamp']}")
            print(f"   Tag Count: {message['tagCount']}")
            print(f"   Payload Size: {len(payload)} bytes")
            
            result = client.publish(TOPIC, payload, qos=QOS)
            result.wait_for_publish()
            
            print(f"   ✅ Published successfully\n")
            
            if i < num_messages:
                time.sleep(2)  # Wait 2 seconds between messages
        
        # Disconnect
        client.disconnect()
        
        print("=" * 80)
        print(f"✅ TEST COMPLETE - Published {num_messages} messages")
        print("=" * 80)
        print("\n📝 Next Steps:")
        print("   1. Check MQTT Subscriber Service logs")
        print("   2. Verify data in database:")
        print("      SELECT * FROM historian_raw.mqtt_audit_main ORDER BY first_received_time DESC LIMIT 5;")
        print("      SELECT * FROM historian_raw.timeseries_data ORDER BY timestamp DESC LIMIT 20;")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    publish_test_data(5)
