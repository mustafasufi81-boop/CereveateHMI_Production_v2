import paho.mqtt.client as mqtt
import json
import time

msg_count = 0
start_time = None

def on_message(client, userdata, msg):
    global msg_count, start_time
    if start_time is None:
        start_time = time.time()
    msg_count += 1
    try:
        data = json.loads(msg.payload)
        tag_count = data.get('tagCount', data.get('count', 0))
        total_samples = data.get('totalSamples', tag_count)
        publish_interval = data.get('publishIntervalMs', 'N/A')
        
        # Check samples per tag
        values = data.get('values', [])
        sample_counts = []
        for v in values[:5]:  # First 5 tags
            addr = v.get('address', v.get('tagName', '?'))
            if 'samples' in v:
                samples = v['samples']
                scan_rate = v.get('scanRateMs', '?')
                sample_counts.append(f"{addr}:{len(samples)}@{scan_rate}ms")
            else:
                sample_counts.append(f"{addr}:1sample")
        
        elapsed = time.time() - start_time
        print(f'Msg#{msg_count}: Tags={tag_count} TotalSamples={total_samples} PublishInterval={publish_interval}ms | {elapsed:.1f}s')
        if sample_counts:
            print(f'  Samples/tag: {sample_counts}')
        print()
    except Exception as e:
        print(f'Error: {e}')

client = mqtt.Client()
client.on_message = on_message
client.connect('localhost', 1883, 60)
client.subscribe('plc/plc/all')
print('Listening to plc/plc/all for 15 seconds...')
print('Checking per-tag sample counts...\n')
client.loop_start()
time.sleep(15)
client.loop_stop()
print(f'\nRate: {msg_count/15:.2f} msg/sec')
