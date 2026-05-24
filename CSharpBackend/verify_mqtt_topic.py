import paho.mqtt.client as mqtt, json, time

def on_message(c, u, msg):
    print("TOPIC:", msg.topic)
    d = json.loads(msg.payload)
    vals = d.get('values', [])
    print(f"  tagCount={d.get('tagCount',0)}")
    for v in vals:
        print(f"  {v.get('tag')}: value={v.get('value')} quality={v.get('quality')}")

c = mqtt.Client()
c.on_message = on_message
c.connect('localhost', 1883)
c.subscribe('#')
c.loop_start()
time.sleep(8)
c.loop_stop()
