#!/usr/bin/env python3
"""
Test SignalR Hub Connection - Check what tags C# is broadcasting
"""
import asyncio
import sys
import json
from signalrcore.hub_connection_builder import HubConnectionBuilder

SIGNALR_URL = "http://localhost:5001/opcHub"

print("=" * 80)
print("TESTING C# SIGNALR HUB CONNECTION")
print("=" * 80)
print(f"SignalR Hub URL: {SIGNALR_URL}")
print()

# Track received messages
received_tags = []
message_count = 0

def on_tag_values_updated(data):
    """Callback when SignalR receives tag updates"""
    global message_count, received_tags
    message_count += 1
    
    print(f"\n📊 Broadcast #{message_count} from C# SignalR Hub:")
    print(f"   Timestamp: {data[0].get('timestamp') if data else 'N/A'}")
    
    if isinstance(data, list) and len(data) > 0:
        tags = data[0].get('tags', [])
        print(f"   Tags in this broadcast: {len(tags)}")
        
        for tag in tags[:5]:  # Show first 5
            tag_id = tag.get('tagId', 'Unknown')
            value = tag.get('value', 'N/A')
            quality = tag.get('quality', 'N/A')
            print(f"      - {tag_id}: {value} ({quality})")
            received_tags.append(tag_id)
        
        if len(tags) > 5:
            print(f"      ... and {len(tags) - 5} more tags")
    else:
        print(f"   ⚠️ Unexpected data format: {type(data)}")
        print(f"   Data: {data}")
    
    print(f"   Total unique tags seen: {len(set(received_tags))}")

async def test_signalr():
    """Connect to SignalR hub and listen for broadcasts"""
    print("🔌 Building SignalR connection...")
    
    hub = HubConnectionBuilder() \
        .with_url(SIGNALR_URL) \
        .with_automatic_reconnect({
            "type": "raw",
            "keep_alive_interval": 10,
            "reconnect_interval": 5,
            "max_attempts": 5
        }) \
        .build()
    
    # Register event handler
    hub.on("TagValuesUpdated", on_tag_values_updated)
    
    # Connection event handlers
    hub.on_open(lambda: print("✅ Connected to SignalR Hub!"))
    hub.on_close(lambda: print("❌ Disconnected from SignalR Hub"))
    hub.on_error(lambda error: print(f"❌ SignalR Error: {error}"))
    
    print("🚀 Starting connection...")
    try:
        hub.start()
        print("✅ SignalR connection started")
        print()
        print("👂 Listening for tag updates from C# OPC service...")
        print("   (Waiting for 30 seconds to collect broadcasts)")
        print()
        
        # Wait for messages
        await asyncio.sleep(30)
        
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total broadcasts received: {message_count}")
        print(f"Total unique tags seen: {len(set(received_tags))}")
        
        if message_count == 0:
            print("\n⚠️ NO BROADCASTS RECEIVED!")
            print("\n💡 Possible reasons:")
            print("   1. No tags are browsed/selected in OPC Browser UI")
            print("   2. SignalR hub is not broadcasting to all connected clients")
            print("   3. Need to subscribe to tags via hub method call")
            print("\n💡 Solution:")
            print("   Open OPC Browser (localhost:5001) and browse/select tags")
            print("   OR check if hub requires explicit subscription")
        else:
            print(f"\n✅ Hub is working!")
            print(f"\nUnique tags being broadcast:")
            for tag_id in sorted(set(received_tags))[:10]:
                print(f"   - {tag_id}")
            if len(set(received_tags)) > 10:
                print(f"   ... and {len(set(received_tags)) - 10} more")
        
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Connection error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n🛑 Closing connection...")
        hub.stop()

if __name__ == "__main__":
    try:
        asyncio.run(test_signalr())
    except KeyboardInterrupt:
        print("\n\n⚠️ Test interrupted by user")
        print(f"Broadcasts received: {message_count}")
        print(f"Unique tags: {len(set(received_tags))}")
