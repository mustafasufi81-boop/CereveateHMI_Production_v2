"""
Test script to verify SignalR subscription is working for all 36 tags
"""
import requests
import json
from signalrcore.hub_connection_builder import HubConnectionBuilder
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

base_url = "http://127.0.0.1:5001"
received_tags = {}

def on_tag_update(data):
    """Track which tags we're receiving"""
    global received_tags
    
    # Handle nested array [[{tags}]]
    if isinstance(data, list) and len(data) > 0:
        if isinstance(data[0], list):
            data = data[0]  # Unwrap
    
    if not isinstance(data, list):
        data = [data]
    
    for tag in data:
        if isinstance(tag, dict):
            tag_id = tag.get('itemID') or tag.get('itemId')
            if tag_id:
                received_tags[tag_id] = tag.get('value')
    
    logger.info(f"📊 Receiving data for {len(received_tags)} unique tags...")

# Step 1: Fetch all enabled tags from API
logger.info("🔍 Step 1: Fetching enabled tags from /api/historian/mapping...")
response = requests.get(f"{base_url}/api/historian/mapping")
data = response.json()
mappings = data.get('mappings', [])
tag_ids = [tag['tagId'] for tag in mappings if tag.get('tagId')]

logger.info(f"✅ Found {len(tag_ids)} enabled tags in database")
logger.info(f"   First 10 tags: {tag_ids[:10]}")

# Step 2: Connect to SignalR
logger.info("\n🔌 Step 2: Connecting to SignalR hub...")
connection = HubConnectionBuilder()\
    .with_url(f"{base_url}/opcHub")\
    .with_automatic_reconnect({
        "type": "raw",
        "keep_alive_interval": 10,
        "reconnect_interval": 5,
        "max_attempts": 5
    })\
    .build()

connection.on("TagValuesUpdated", on_tag_update)
connection.start()

logger.info("✅ Connected to SignalR hub")

# Step 3: Subscribe to all tags
logger.info(f"\n📝 Step 3: Subscribing to {len(tag_ids)} tags...")
connection.send("SubscribeToTags", [tag_ids])
logger.info("✅ Subscription request sent")

# Step 4: Wait and monitor
logger.info("\n⏱️  Step 4: Monitoring for 15 seconds...")
logger.info("=" * 60)

for i in range(15):
    time.sleep(1)
    if (i + 1) % 3 == 0:
        logger.info(f"   {i+1}s: Receiving data for {len(received_tags)}/{len(tag_ids)} tags")

# Final report
logger.info("\n" + "=" * 60)
logger.info("📊 FINAL REPORT")
logger.info("=" * 60)
logger.info(f"Expected tags: {len(tag_ids)}")
logger.info(f"Receiving data for: {len(received_tags)} tags")
logger.info(f"Missing: {len(tag_ids) - len(received_tags)} tags")

if len(received_tags) < len(tag_ids):
    missing = set(tag_ids) - set(received_tags.keys())
    logger.warning(f"\n❌ Tags NOT receiving data:")
    for tag in list(missing)[:10]:
        logger.warning(f"   • {tag}")
    if len(missing) > 10:
        logger.warning(f"   ... and {len(missing) - 10} more")

if len(received_tags) > 0:
    logger.info(f"\n✅ Tags receiving data:")
    for tag_id, value in list(received_tags.items())[:10]:
        logger.info(f"   • {tag_id} = {value}")

connection.stop()
logger.info("\n✅ Test complete")
