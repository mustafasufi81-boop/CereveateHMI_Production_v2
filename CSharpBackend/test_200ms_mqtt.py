#!/usr/bin/env python3
"""
TEST: Verify 200ms Scan Rate via MQTT
=====================================
This script subscribes to MQTT and measures:
1. How many samples per tag we receive per second
2. Time between messages
3. Sample array size (should be 5 if 200ms scan / 1000ms publish)

Run: python test_200ms_mqtt.py
"""

import json
import time
from datetime import datetime
from collections import defaultdict

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("ERROR: pip install paho-mqtt")
    exit(1)

# Track statistics
stats = {
    'messages_received': 0,
    'last_message_time': None,
    'message_intervals': [],
    'samples_per_tag': defaultdict(list),
    'start_time': None
}

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("\n" + "="*70)
        print("✅ CONNECTED TO MQTT BROKER")
        print("="*70)
        print("Subscribing to plc/# topics...")
        client.subscribe('plc/#', qos=1)
        stats['start_time'] = time.time()
        print("Waiting for messages... (Press Ctrl+C to stop)\n")
    else:
        print(f"❌ Connection failed: {rc}")

def on_message(client, userdata, msg):
    now = time.time()
    stats['messages_received'] += 1
    
    # Calculate interval between messages
    if stats['last_message_time']:
        interval_ms = (now - stats['last_message_time']) * 1000
        stats['message_intervals'].append(interval_ms)
    stats['last_message_time'] = now
    
    try:
        payload = json.loads(msg.payload.decode())
        
        # Extract info
        publish_interval = payload.get('publishIntervalMs', 'N/A')
        total_samples = payload.get('totalSamples', 0)
        tag_count = payload.get('tagCount', payload.get('count', 0))
        values = payload.get('values', [])
        
        # Count samples per tag
        for v in values:
            tag_name = v.get('tag', v.get('tagName', 'unknown'))
            samples = v.get('samples', [])
            sample_count = v.get('sampleCount', len(samples) if samples else 1)
            scan_rate = v.get('scanRateMs', '?')
            
            stats['samples_per_tag'][tag_name].append({
                'count': sample_count,
                'scan_rate': scan_rate,
                'time': now
            })
        
        # Print summary every message
        elapsed = now - stats['start_time'] if stats['start_time'] else 0
        avg_interval = sum(stats['message_intervals'][-10:]) / len(stats['message_intervals'][-10:]) if stats['message_intervals'] else 0
        
        # Calculate avg samples per tag
        avg_samples = total_samples / tag_count if tag_count > 0 else 0
        
        print(f"\r[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
              f"Msg #{stats['messages_received']:4d} | "
              f"Tags: {tag_count:3d} | "
              f"TotalSamples: {total_samples:4d} | "
              f"Avg/Tag: {avg_samples:.1f} | "
              f"Interval: {avg_interval:6.1f}ms | "
              f"PublishRate: {publish_interval}ms", end='', flush=True)
        
        # Every 10 messages, print detailed stats
        if stats['messages_received'] % 10 == 0:
            print_detailed_stats(values)
            
    except Exception as e:
        print(f"\n❌ Error parsing message: {e}")

def print_detailed_stats(values):
    print("\n" + "-"*70)
    print("DETAILED SAMPLE ANALYSIS (First 5 tags):")
    print("-"*70)
    
    for v in values[:5]:
        tag_name = v.get('tag', v.get('tagName', 'unknown'))
        samples = v.get('samples', [])
        sample_count = v.get('sampleCount', len(samples) if samples else 1)
        scan_rate = v.get('scanRateMs', '?')
        value = v.get('value', 'N/A')
        
        if samples and len(samples) > 1:
            # Multiple samples - show timestamps
            sample_values = [s.get('value') for s in samples]
            timestamps = [s.get('timestamp', '') for s in samples]
            
            print(f"\n  📊 {tag_name}")
            print(f"     ScanRate: {scan_rate}ms | SampleCount: {sample_count}")
            print(f"     Latest: {value}")
            
            if all(isinstance(sv, (int, float)) for sv in sample_values if sv is not None):
                valid_values = [sv for sv in sample_values if sv is not None]
                if valid_values:
                    print(f"     Range: {min(valid_values):.2f} - {max(valid_values):.2f}")
                    print(f"     Samples: {[round(sv, 2) if isinstance(sv, float) else sv for sv in sample_values[:5]]}...")
        else:
            print(f"\n  📊 {tag_name}")
            print(f"     ScanRate: {scan_rate}ms | SampleCount: {sample_count} | Value: {value}")
    
    print("-"*70)
    
    # Summary
    intervals = stats['message_intervals']
    if len(intervals) > 0:
        avg = sum(intervals) / len(intervals)
        min_i = min(intervals)
        max_i = max(intervals)
        print(f"\n📈 MESSAGE INTERVALS: Avg={avg:.1f}ms, Min={min_i:.1f}ms, Max={max_i:.1f}ms")
        
        # Expected vs actual
        print(f"\n🎯 EXPECTATION CHECK:")
        print(f"   If scan=200ms, publish=1000ms → Expect ~5 samples/tag")
        print(f"   If scan=1000ms, publish=1000ms → Expect ~1 sample/tag")
    
    print("")

def on_disconnect(client, userdata, rc):
    print(f"\n⚠️ Disconnected (rc={rc})")

def main():
    print("\n" + "="*70)
    print("    MQTT 200ms SCAN RATE TEST")
    print("="*70)
    print("This script verifies if PLC is being scanned at 200ms")
    print("and if MQTT is publishing accumulated samples correctly.")
    print("="*70 + "\n")
    
    client = mqtt.Client(client_id='test_200ms_scanner', clean_session=True)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    
    try:
        print("Connecting to localhost:1883...")
        client.connect('localhost', 1883, 60)
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n\n" + "="*70)
        print("FINAL STATISTICS")
        print("="*70)
        print(f"Total messages received: {stats['messages_received']}")
        if stats['message_intervals']:
            avg = sum(stats['message_intervals']) / len(stats['message_intervals'])
            print(f"Average message interval: {avg:.1f}ms")
        print("="*70)
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == '__main__':
    main()
