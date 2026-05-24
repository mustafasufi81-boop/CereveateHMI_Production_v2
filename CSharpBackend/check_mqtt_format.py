import paho.mqtt.client as mqtt
import json
import time

messages = []

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT broker")
        client.subscribe('plc/plc/all')
    else:
        print(f"Connection failed: {rc}")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        messages.append(payload)
        print(f"Received message on {msg.topic}")
    except:
        print("Failed to parse message")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect('localhost', 1883, 60)
client.loop_start()

time.sleep(3)  # Wait for messages

if messages:
    print("\nMQTT Message Sample:")
    print(json.dumps(messages[0], indent=2)[:800])
else:
    print("No messages received")

client.disconnect()