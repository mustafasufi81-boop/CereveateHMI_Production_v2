"""
Test script to verify C# backend connectivity and SignalR subscription
"""
import requests
import json
from signalrcore.hub_connection_builder import HubConnectionBuilder
import time

print("=" * 60)
print("🔍 Testing C# OPC Backend Connection")
print("=" * 60)

# Test 1: Check if C# backend is running
print("\n📡 Test 1: Checking C# backend API...")
try:
    response = requests.get("http://127.0.0.1:5001/api/opc/tags", timeout=5)
    print(f"   Status Code: {response.status_code}")
    
    if response.status_code == 200:
        tags = response.json()
        print(f"   ✅ SUCCESS: Found {len(tags)} tags")
        print(f"   Sample tags: {json.dumps(tags[:3], indent=2) if len(tags) > 0 else 'No tags'}")
    else:
        print(f"   ❌ FAILED: HTTP {response.status_code}")
        print(f"   Response: {response.text}")
except Exception as e:
    print(f"   ❌ FAILED: {e}")
    exit(1)

# Test 2: Check SignalR hub connection
print("\n🔌 Test 2: Testing SignalR connection...")
tag_updates_received = []

def on_tag_update(data):
    print(f"   📊 Received {len(data)} tag updates!")
    tag_updates_received.extend(data)
    for tag in data[:3]:  # Show first 3
        print(f"      - {tag.get('itemID')}: {tag.get('value')} ({tag.get('quality')})")

def on_open():
    print("   ✅ SignalR connection opened!")
    
    # Subscribe to tags
    print("   📋 Subscribing to tags...")
    try:
        # Get tag IDs
        response = requests.get("http://127.0.0.1:5001/api/opc/tags", timeout=5)
        tags = response.json()
        tag_ids = [tag.get('itemID') or tag.get('id') for tag in tags]
        tag_ids = [tid for tid in tag_ids if tid]
        
        print(f"   📝 Subscribing to {len(tag_ids)} tags...")
        connection.invoke("SubscribeToTags", [tag_ids])
        print(f"   ✅ Subscription sent for tags: {tag_ids}")
    except Exception as e:
        print(f"   ❌ Subscription failed: {e}")

def on_close():
    print("   ⚠️  SignalR connection closed")

def on_error(error):
    print(f"   ❌ SignalR error: {error}")

try:
    connection = HubConnectionBuilder()\
        .with_url("http://127.0.0.1:5001/opcHub")\
        .build()
    
    connection.on_open(on_open)
    connection.on_close(on_close)
    connection.on_error(on_error)
    connection.on("TagValuesUpdated", on_tag_update)
    
    connection.start()
    
    print("   ⏳ Waiting 10 seconds for tag updates...")
    time.sleep(10)
    
    if len(tag_updates_received) > 0:
        print(f"\n   ✅ SUCCESS: Received {len(tag_updates_received)} total tag updates")
        print("   Sample data:")
        print(json.dumps(tag_updates_received[:5], indent=2))
    else:
        print("\n   ⚠️  WARNING: No tag updates received in 10 seconds")
        print("   Possible reasons:")
        print("   - No tags are being monitored in OPC server")
        print("   - Tag values are not changing")
        print("   - SignalR subscription didn't work")
    
    connection.stop()
    
except Exception as e:
    print(f"   ❌ FAILED: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("🏁 Test Complete")
print("=" * 60)
