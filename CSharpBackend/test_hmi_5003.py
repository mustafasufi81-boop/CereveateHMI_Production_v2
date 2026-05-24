#!/usr/bin/env python3
"""
Test script to check why PLC tags are not showing in HMI port 5003
"""
import requests
import json

def test_hmi_port_5003():
    """Test the main HMI on port 5003"""
    print("=" * 60)
    print("TESTING HMI PORT 5003 - PLC TAG INTEGRATION")
    print("=" * 60)
    
    # Test the main API endpoint
    try:
        print("\n1. Testing /api/tags/latest endpoint...")
        response = requests.get('http://localhost:5003/api/tags/latest', timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ SUCCESS - Got response")
            print(f"   Total tags: {data.get('count', 0)}")
            
            # Check connection status
            sources = data.get('sources', {})
            print(f"   Historian connected: {sources.get('historian_connected')}")
            print(f"   MQTT connected: {sources.get('mqtt_connected')}")
            print(f"   MQTT last update: {sources.get('mqtt_last_update')}")
            
            # Look for PLC tags specifically
            tags = data.get('tags', {})
            plc_tags_found = []
            
            for tag_id, tag_info in tags.items():
                if 'Blastfurnace' in tag_id or 'Boiler' in tag_id or 'PLC' in tag_id.upper():
                    plc_tags_found.append({
                        'tag_id': tag_id,
                        'value': tag_info.get('value'),
                        'quality': tag_info.get('quality'),
                        'source': tag_info.get('source'),
                        'timestamp': tag_info.get('timestamp')
                    })
            
            if plc_tags_found:
                print(f"\n🔥 FOUND {len(plc_tags_found)} PLC TAGS:")
                for tag in plc_tags_found:
                    print(f"   {tag['tag_id']}: {tag['value']} ({tag['quality']}) from {tag['source']}")
            else:
                print(f"\n❌ NO PLC TAGS FOUND in response")
                print("   Available tags:")
                for tag_id in list(tags.keys())[:5]:  # Show first 5
                    print(f"     - {tag_id}: {tags[tag_id].get('value')} ({tags[tag_id].get('source')})")
                if len(tags) > 5:
                    print(f"     ... and {len(tags) - 5} more")
            
        else:
            print(f"❌ FAILED - Status: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
    
    except Exception as e:
        print(f"❌ ERROR: {e}")

def test_mqtt_direct():
    """Test if MQTT broker is working"""
    print(f"\n2. Testing MQTT broker directly...")
    try:
        import paho.mqtt.client as mqtt
        
        received_messages = []
        
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                print(f"   ✅ Connected to MQTT broker")
                client.subscribe('plc/#')
            else:
                print(f"   ❌ MQTT connection failed: {rc}")
        
        def on_message(client, userdata, msg):
            received_messages.append({
                'topic': msg.topic,
                'payload': msg.payload.decode()[:100]  # First 100 chars
            })
        
        client = mqtt.Client()
        client.on_connect = on_connect
        client.on_message = on_message
        
        client.connect('localhost', 1883, 60)
        client.loop_start()
        
        import time
        time.sleep(3)  # Wait 3 seconds for messages
        
        if received_messages:
            print(f"   ✅ Received {len(received_messages)} MQTT messages:")
            for msg in received_messages:
                print(f"     {msg['topic']}: {msg['payload']}...")
        else:
            print(f"   ❌ No MQTT messages received in 3 seconds")
        
        client.loop_stop()
        client.disconnect()
        
    except Exception as e:
        print(f"   ❌ MQTT test error: {e}")

def test_plc_api_direct():
    """Test PLC API on port 5001 directly"""
    print(f"\n3. Testing PLC API on port 5001...")
    try:
        response = requests.get('http://localhost:5001/api/plc/values', timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ PLC API responding")
            print(f"   Tags count: {data.get('count', 0)}")
            
            values = data.get('values', [])
            if values:
                print(f"   Sample tags:")
                for tag in values[:3]:  # First 3 tags
                    print(f"     {tag.get('tagName')}: {tag.get('value')}")
        else:
            print(f"   ❌ PLC API failed - Status: {response.status_code}")
    
    except Exception as e:
        print(f"   ❌ PLC API error: {e}")

if __name__ == "__main__":
    test_hmi_port_5003()
    test_mqtt_direct()
    test_plc_api_direct()
    print("\n" + "=" * 60)
    print("TEST COMPLETED")
    print("=" * 60)