"""
Test script to verify MQTT topic config cache loading
"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from utils.config_loader import ConfigLoader
from database.db_connection import DatabaseConnection
from cache.topic_cache import TopicCache

def test_topic_cache():
    """Test topic cache loading"""
    print("=" * 60)
    print("Testing MQTT Topic Config Cache Loading")
    print("=" * 60)
    
    try:
        # Load configuration
        print("\n1. Loading configuration...")
        config_loader = ConfigLoader('config/service_config.yaml')
        config = config_loader.load()
        print("✓ Configuration loaded")
        
        # Initialize database connection
        print("\n2. Connecting to database...")
        db = DatabaseConnection(config['database'])
        db.initialize()
        
        if not db.test_connection():
            print("✗ Database connection test failed")
            return
        print("✓ Database connected")
        
        # Initialize topic cache
        print("\n3. Loading topic cache...")
        cache_refresh_interval = config['service']['topic_cache_refresh_interval']
        topic_cache = TopicCache(db, cache_refresh_interval)
        topic_cache.load()
        print(f"✓ Topic cache loaded")
        
        # Get cache contents
        print("\n4. Verifying cache contents...")
        all_topics = topic_cache.get_all_topics()
        
        print(f"\n{'='*60}")
        print(f"Total Topics in Cache: {len(all_topics)}")
        print(f"{'='*60}")
        
        if all_topics:
            print("\nCached Topics:")
            for topic_name in all_topics:
                config = topic_cache.get(topic_name)
                if config:
                    print(f"\n  Topic: {topic_name}")
                    print(f"    - Active: {config.get('is_active', False)}")
                    print(f"    - QoS: {config.get('qos', 0)}")
                    print(f"    - Processing Rules: {config.get('processing_rules', 'None')}")
                    print(f"    - Created: {config.get('created_at', 'Unknown')}")
        else:
            print("\n⚠ No topics found in cache")
        
        # Test individual topic retrieval
        print(f"\n{'='*60}")
        print("Testing Individual Topic Retrieval")
        print(f"{'='*60}")
        
        test_topics = [
            "production/plant_a/gateway_001",
            "production/plant_b/gateway_002",
            "test/gateway/data",
            "development/test/#"
        ]
        
        for topic in test_topics:
            config = topic_cache.get(topic)
            if config:
                print(f"✓ {topic} - Found (Active: {config.get('is_active')})")
            else:
                print(f"✗ {topic} - NOT FOUND")
        
        # Test pattern matching for wildcard topics
        print(f"\n{'='*60}")
        print("Testing Wildcard Pattern Matching")
        print(f"{'='*60}")
        
        test_incoming_topics = [
            "development/test/sensor1",
            "development/test/sensor2",
            "production/plant_a/gateway_001",
            "production/unknown/gateway_999",
        ]
        
        for incoming_topic in test_incoming_topics:
            matched = False
            for cached_topic in all_topics:
                config = topic_cache.get(cached_topic)
                if config and cached_topic.endswith('#'):
                    # Simple wildcard match
                    prefix = cached_topic[:-1]  # Remove '#'
                    if incoming_topic.startswith(prefix):
                        matched = True
                        print(f"✓ {incoming_topic} matches {cached_topic}")
                        break
                elif incoming_topic == cached_topic:
                    matched = True
                    print(f"✓ {incoming_topic} exact match")
                    break
            
            if not matched:
                print(f"✗ {incoming_topic} - No matching subscription")
        
        print(f"\n{'='*60}")
        print("✅ Cache Loading Test COMPLETE")
        print(f"{'='*60}\n")
        
        # Cleanup
        db.close()
        
    except Exception as e:
        print(f"\n✗ Error during cache testing: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_topic_cache()
