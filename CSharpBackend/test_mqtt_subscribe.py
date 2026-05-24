#!/usr/bin/env python3
"""
MQTT Test Subscriber
Subscribes to PLC topics and displays incoming values

Usage:
    pip install paho-mqtt
    python test_mqtt_subscribe.py

Topics monitored:
    - plc/#  (all PLC messages)
"""

import json
import sys
from datetime import datetime

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("ERROR: paho-mqtt not installed")
    print("Run: pip install paho-mqtt")
    sys.exit(1)

# Configuration
BROKER_HOST = "localhost"
BROKER_PORT = 1883
TOPICS = ["plc/#", "factory1/#"]  # Subscribe to all PLC topics

def on_connect(client, userdata, flags, rc):
    """Called when connected to MQTT broker"""
    if rc == 0:
        print(f"\n✅ Connected to MQTT broker at {BROKER_HOST}:{BROKER_PORT}")
        print("=" * 60)
        
        # Subscribe to all topics
        for topic in TOPICS:
            client.subscribe(topic, qos=1)
            print(f"📡 Subscribed to: {topic}")
        
        print("=" * 60)
        print("\n⏳ Waiting for messages...\n")
    else:
        print(f"\n❌ Connection failed with code: {rc}")

def on_message(client, userdata, msg):
    """Called when a message is received - handles both legacy and sample-based formats"""
    try:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        topic = msg.topic
        
        # Try to parse as JSON
        try:
            payload = json.loads(msg.payload.decode())
            
            print(f"\n{'─' * 60}")
            print(f"📬 [{timestamp}] Topic: {topic}")
            print(f"{'─' * 60}")
            
            # Check if it's bulk message
            if "values" in payload:
                # DYNAMIC format detection
                publish_interval = payload.get('publishIntervalMs', 'N/A')
                total_samples = payload.get('totalSamples', payload.get('count', 0))
                tag_count = payload.get('tagCount', payload.get('count', 0))
                
                print(f"  Timestamp: {payload.get('timestamp', 'N/A')}")
                print(f"  PublishInterval: {publish_interval}ms")
                print(f"  Tags: {tag_count}, TotalSamples: {total_samples}")
                
                # Calculate avg samples per tag
                if tag_count > 0 and total_samples > 0:
                    avg_samples = total_samples / tag_count
                    print(f"  Avg Samples/Tag: {avg_samples:.1f}")
                print()
                
                values = payload.get("values", [])
                for v in values[:20]:  # Limit to first 20 tags
                    plc_id = v.get("plcId", v.get("plc_id", ""))
                    tag = v.get("tag", v.get("tagName", ""))
                    value = v.get("value", "N/A")
                    quality = v.get("quality", "Good")
                    data_type = v.get("dataType", v.get("data_type", ""))
                    
                    # DYNAMIC: Check for samples array
                    samples = v.get("samples", [])
                    scan_rate = v.get("scanRateMs", "?")
                    sample_count = v.get("sampleCount", len(samples) if samples else 1)
                    
                    quality_icon = "✓" if quality in ["Good", "GOOD"] else "⚠"
                    
                    # Show sample info if available
                    if samples and len(samples) > 1:
                        # Multiple samples - show range
                        sample_values = [s.get('value') for s in samples if s.get('value') is not None]
                        if sample_values and all(isinstance(sv, (int, float)) for sv in sample_values):
                            min_val = min(sample_values)
                            max_val = max(sample_values)
                            print(f"  {quality_icon} [{plc_id}] {tag:25} = {value:>10} ({data_type}) [{sample_count} samples @ {scan_rate}ms, range: {min_val:.2f}-{max_val:.2f}]")
                        else:
                            print(f"  {quality_icon} [{plc_id}] {tag:25} = {value:>10} ({data_type}) [{sample_count} samples @ {scan_rate}ms]")
                    else:
                        # Single value (legacy format)
                        print(f"  {quality_icon} [{plc_id}] {tag:25} = {value:>10} ({data_type})")
                
                if len(values) > 20:
                    print(f"  ... and {len(values) - 20} more tags")
                    
            elif "plcId" in payload or "plc_id" in payload:
                # Single PLC message
                plc_id = payload.get("plcId", payload.get("plc_id", ""))
                print(f"  PLC: {plc_id}")
                print(f"  Timestamp: {payload.get('timestamp', 'N/A')}")
                print(f"  Count: {payload.get('count', 0)} tags")
                print()
                
                values = payload.get("values", [])
                for v in values[:20]:
                    tag = v.get("tag", v.get("tagName", ""))
                    value = v.get("value", "N/A")
                    quality = v.get("quality", "Good")
                    
                    quality_icon = "✓" if quality in ["Good", "GOOD"] else "⚠"
                    print(f"  {quality_icon} {tag:35} = {value}")
                    
            else:
                # Unknown format - print raw
                print(f"  Payload: {json.dumps(payload, indent=2)}")
                
        except json.JSONDecodeError:
            # Not JSON - print raw
            print(f"\n[{timestamp}] {topic}: {msg.payload.decode()[:200]}")
            
    except Exception as e:
        print(f"\n❌ Error processing message: {e}")

def on_disconnect(client, userdata, rc):
    """Called when disconnected"""
    print(f"\n⚠️  Disconnected from broker (rc={rc})")
    if rc != 0:
        print("    Unexpected disconnect - will auto-reconnect")

def main():
    print("\n" + "=" * 60)
    print("    MQTT TEST SUBSCRIBER")
    print("    Monitoring PLC tag values from MQTT broker")
    print("=" * 60)
    print(f"\nBroker: {BROKER_HOST}:{BROKER_PORT}")
    print(f"Topics: {', '.join(TOPICS)}")
    print("\nConnecting...")

    # Create MQTT client
    client = mqtt.Client(client_id=f"test_subscriber_{datetime.now().strftime('%H%M%S')}")
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    try:
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
        client.loop_forever()
    except ConnectionRefusedError:
        print(f"\n❌ Connection refused - is MQTT broker running at {BROKER_HOST}:{BROKER_PORT}?")
        print("\nTo start Mosquitto broker:")
        print("  Windows: net start mosquitto")
        print("  Linux:   sudo systemctl start mosquitto")
        print("\nOr install Mosquitto: https://mosquitto.org/download/")
    except KeyboardInterrupt:
        print("\n\n👋 Stopped by user")
        client.disconnect()

if __name__ == "__main__":
    main()
