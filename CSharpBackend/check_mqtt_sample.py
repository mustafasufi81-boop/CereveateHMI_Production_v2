"""Quick script to sample MQTT messages"""
import paho.mqtt.client as mqtt
import json
import time

data = []

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload)
        data.append(payload)
        print(f"Topic: {msg.topic}")
    except Exception as e:
        print(f"Error: {e}")

client = mqtt.Client()
client.on_message = on_message
client.connect('localhost', 1883)
client.subscribe('plc/#')
print("Listening for 3 seconds...")
client.loop_start()
time.sleep(3)
client.loop_stop()

if data:
    print("\n=== SAMPLE MESSAGE ===")
    print(json.dumps(data[0], indent=2)[:3000])
else:
    print("No messages received")
