"""
Test script to see what data SignalR is actually receiving
Run this to debug the data flow
"""
import json
import logging
import time
import requests
from signalrcore.hub_connection_builder import HubConnectionBuilder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def on_tag_update(data):
    """Print received data structure"""
    print("\n" + "="*80)
    print("RECEIVED DATA:")
    print(f"Type: {type(data)}")
    
    if isinstance(data, list):
        print(f"List with {len(data)} items")
        if len(data) > 0:
            print(f"First item type: {type(data[0])}")
            print(f"First item keys: {list(data[0].keys()) if isinstance(data[0], dict) else 'Not a dict'}")
            print(f"First item: {json.dumps(data[0], indent=2, default=str)}")
    elif isinstance(data, dict):
        print(f"Dict with keys: {list(data.keys())}")
        print(f"Data: {json.dumps(data, indent=2, default=str)}")
    else:
        print(f"Data: {data}")
    
    print("="*80 + "\n")

def on_connected():
    print("✅ Connected! Fetching tags and subscribing...")
    
    try:
        # Fetch tags from API
        response = requests.get("http://127.0.0.1:5001/api/historian/matrix", timeout=5)
        if response.status_code == 200:
            data = response.json()
            tags = data.get('tags', [])
            tag_ids = [tag['tagId'] for tag in tags if tag.get('tagId')]
            
            print(f"📋 Found {len(tag_ids)} tags, subscribing...")
            
            # Subscribe to tags
            connection.send("SubscribeToTags", [tag_ids])
            print(f"✅ Subscribed to {len(tag_ids)} tags")
        else:
            print(f"⚠️  API returned {response.status_code}")
    except Exception as e:
        print(f"❌ Error subscribing: {e}")

# Connect to SignalR hub
hub_url = "http://127.0.0.1:5001/opcHub"
print(f"Connecting to {hub_url}...")

connection = HubConnectionBuilder() \
    .with_url(hub_url) \
    .with_automatic_reconnect({
        "type": "interval",
        "intervals": [1, 2, 5, 10]
    }) \
    .build()

connection.on_open(on_connected)
connection.on_close(lambda: print("❌ Disconnected"))
connection.on_error(lambda e: print(f"❌ Error: {e}"))

# Subscribe to TagValuesUpdated event
connection.on("TagValuesUpdated", on_tag_update)

connection.start()

print("Listening for TagValuesUpdated events... Press Ctrl+C to exit")

try:
    import time
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopping...")
    connection.stop()
