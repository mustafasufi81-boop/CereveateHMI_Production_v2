import paho.mqtt.client as mqtt
import json
import time

print("=" * 80)
print("MQTT DATA FLOW DIAGNOSTIC")
print("=" * 80)

messages_received = []

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Connected to MQTT Broker (Mosquitto)")
        # Subscribe to all OPC topics
        client.subscribe("opc/#")
        print("✅ Subscribed to: opc/#")
    else:
        print(f"❌ Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        tag_count = payload.get('tagCount', 0)
        source = payload.get('serverProgId', 'Unknown')
        timestamp = payload.get('timestamp', 'N/A')
        
        messages_received.append({
            'topic': msg.topic,
            'source': source,
            'tag_count': tag_count,
            'timestamp': timestamp
        })
        
        print(f"[{len(messages_received)}] Topic: {msg.topic}")
        print(f"    Source: {source}, Tags: {tag_count}, Time: {timestamp}")
        
    except json.JSONDecodeError:
        print(f"❌ Invalid JSON on topic {msg.topic}")
    except Exception as e:
        print(f"❌ Error processing message: {e}")

# Create MQTT client
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

print("\n[1] Connecting to Mosquitto MQTT Broker...")
try:
    client.connect("127.0.0.1", 1883, 60)
except Exception as e:
    print(f"❌ Connection failed: {e}")
    exit(1)

print("[2] Listening for 15 seconds...")
print("-" * 80)

# Listen for 15 seconds
client.loop_start()
time.sleep(15)
client.loop_stop()
client.disconnect()

print("-" * 80)
print(f"\n[3] SUMMARY:")
print(f"    Total messages received: {len(messages_received)}")

if messages_received:
    sources = set(msg['source'] for msg in messages_received)
    print(f"    Sources detected: {', '.join(sources)}")
    print(f"\n    ✅ MQTT IS WORKING - C# backend is publishing data")
    print(f"    ✅ Flask backend should be receiving these messages")
else:
    print(f"    ❌ NO MQTT MESSAGES RECEIVED!")
    print(f"    Check:")
    print(f"      1. C# Backend (OpcDaWebBrowser) is running")
    print(f"      2. C# Backend is connected to PLC/OPC")
    print(f"      3. Mosquitto MQTT service is running")

print("\n" + "=" * 80)
