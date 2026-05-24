"""
MQTT Topic-Specific Test Data Generator
Reads topics from mqtt_topic_config table and generates realistic test data for each topic
"""

import psycopg2
import paho.mqtt.client as mqtt
import json
from datetime import datetime, timedelta
import random
import time
import uuid
from typing import List, Dict

# Database Configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'Historian_data',
    'user': 'postgres',
    'password': 'Database@19c'
}

# MQTT Configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 1883

class TopicDataGenerator:
    """Generates realistic OPC data based on topic patterns"""
    
    def __init__(self):
        self.tag_counters = {}
        
    def generate_gateway_data(self, topic_name: str, tag_count: int = 20) -> Dict:
        """Generate gateway data with multiple tags"""
        
        # Extract gateway/plant info from topic
        parts = topic_name.split('/')
        gateway_id = parts[-1] if len(parts) > 0 else "gateway_001"
        plant = parts[1] if len(parts) > 1 else "plant_a"
        
        # Generate unique file_id for message tracking
        file_id = f"{gateway_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        tags = []
        timestamp = datetime.utcnow()
        
        # Generate different types of tags based on topic
        if 'test' in topic_name:
            # Test data - simple patterns
            tags = self._generate_test_tags(gateway_id, tag_count, timestamp)
        elif 'production' in topic_name:
            # Production data - realistic industrial values
            tags = self._generate_production_tags(gateway_id, plant, tag_count, timestamp)
        elif 'development' in topic_name:
            # Development data - various data types
            tags = self._generate_development_tags(gateway_id, tag_count, timestamp)
        else:
            # Generic data
            tags = self._generate_generic_tags(gateway_id, tag_count, timestamp)
        
        message = {
            "file_id": file_id,
            "timestamp": timestamp.isoformat() + "Z",
            "source": gateway_id,
            "plant": plant,
            "tag_count": len(tags),
            "data": tags
        }
        
        return message
    
    def _generate_test_tags(self, gateway_id: str, count: int, timestamp: datetime) -> List[Dict]:
        """Generate simple test tags"""
        tags = []
        for i in range(1, count + 1):
            tag_id = f"TEST.{gateway_id}.Tag{i:03d}"
            tags.append({
                "tag_id": tag_id,
                "value": round(random.uniform(0, 100), 2),
                "quality": "Good",
                "timestamp": timestamp.isoformat() + "Z"
            })
        return tags
    
    def _generate_production_tags(self, gateway_id: str, plant: str, count: int, timestamp: datetime) -> List[Dict]:
        """Generate realistic production/industrial tags"""
        tags = []
        
        # Common industrial measurements
        tag_types = [
            ("Temperature", 20, 200, "°C"),
            ("Pressure", 0, 150, "PSI"),
            ("Flow", 0, 500, "L/min"),
            ("Level", 0, 100, "%"),
            ("Speed", 0, 3600, "RPM"),
            ("Power", 0, 500, "kW"),
            ("Vibration", 0, 10, "mm/s"),
            ("Current", 0, 100, "A")
        ]
        
        equipment_types = ["Pump", "Motor", "Tank", "Reactor", "Compressor"]
        
        for i in range(count):
            equipment = random.choice(equipment_types)
            tag_type, min_val, max_val, unit = random.choice(tag_types)
            equipment_num = (i % 5) + 1
            
            tag_id = f"{plant.upper()}.{equipment}{equipment_num:02d}.{tag_type}"
            value = round(random.uniform(min_val, max_val), 2)
            
            # Occasionally add bad quality
            quality = "Good" if random.random() > 0.05 else random.choice(["Bad", "Uncertain"])
            
            tags.append({
                "tag_id": tag_id,
                "value": value,
                "quality": quality,
                "timestamp": timestamp.isoformat() + "Z",
                "unit": unit,
                "equipment": f"{equipment}{equipment_num:02d}"
            })
        
        return tags
    
    def _generate_development_tags(self, gateway_id: str, count: int, timestamp: datetime) -> List[Dict]:
        """Generate development/debug tags with various data types"""
        tags = []
        
        for i in range(1, count + 1):
            tag_id = f"DEV.{gateway_id}.Test{i:03d}"
            
            # Mix different value types
            if i % 4 == 0:
                value = random.choice([0, 1])  # Boolean
            elif i % 4 == 1:
                value = random.randint(0, 1000)  # Integer
            elif i % 4 == 2:
                value = round(random.uniform(-999.99, 999.99), 2)  # Float
            else:
                value = round(random.uniform(0, 100), 2)  # Normal range
            
            tags.append({
                "tag_id": tag_id,
                "value": value,
                "quality": "Good",
                "timestamp": timestamp.isoformat() + "Z",
                "data_type": type(value).__name__
            })
        
        return tags
    
    def _generate_generic_tags(self, gateway_id: str, count: int, timestamp: datetime) -> List[Dict]:
        """Generate generic tags"""
        tags = []
        for i in range(1, count + 1):
            tag_id = f"{gateway_id}.Tag{i:04d}"
            tags.append({
                "tag_id": tag_id,
                "value": round(random.uniform(0, 1000), 2),
                "quality": "Good",
                "timestamp": timestamp.isoformat() + "Z"
            })
        return tags


class MQTTTopicTestPublisher:
    """Publishes test data to configured MQTT topics"""
    
    def __init__(self):
        self.db_conn = None
        self.mqtt_client = None
        self.generator = TopicDataGenerator()
    
    def connect_database(self):
        """Connect to PostgreSQL database"""
        try:
            self.db_conn = psycopg2.connect(**DB_CONFIG)
            print("✅ Connected to database")
            return True
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            return False
    
    def connect_mqtt(self):
        """Connect to MQTT broker"""
        try:
            self.mqtt_client = mqtt.Client(f"topic_test_publisher_{uuid.uuid4().hex[:8]}")
            self.mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
            print("✅ Connected to MQTT broker")
            return True
        except Exception as e:
            print(f"❌ MQTT connection failed: {e}")
            return False
    
    def get_active_topics(self) -> List[Dict]:
        """Retrieve active topics from mqtt_topic_config table"""
        try:
            cursor = self.db_conn.cursor()
            cursor.execute("""
                SELECT topic_id, topic_name, plc_name, qos, thread_group, processing_rules
                FROM historian_raw.mqtt_topic_config
                WHERE is_active = TRUE
                ORDER BY topic_id
            """)
            
            topics = []
            for row in cursor.fetchall():
                topics.append({
                    'topic_id': row[0],
                    'topic_name': row[1],
                    'plc_name': row[2],
                    'qos': row[3],
                    'thread_group': row[4],
                    'processing_rules': row[5]
                })
            
            cursor.close()
            print(f"✅ Retrieved {len(topics)} active topics from database")
            return topics
            
        except Exception as e:
            print(f"❌ Failed to retrieve topics: {e}")
            return []
    
    def publish_test_data(self, topics: List[Dict], messages_per_topic: int = 5, delay: float = 1.0):
        """Publish test data to all configured topics"""
        
        print(f"\n{'='*80}")
        print(f"📤 Publishing {messages_per_topic} messages per topic")
        print(f"{'='*80}\n")
        
        total_published = 0
        
        for topic_config in topics:
            topic_name = topic_config['topic_name']
            qos = topic_config['qos']
            
            # Skip wildcard topics for publishing
            if '#' in topic_name or '+' in topic_name:
                print(f"⚠️  Skipping wildcard topic: {topic_name}")
                continue
            
            print(f"\n📍 Topic: {topic_name} (QoS: {qos})")
            print(f"{'-'*80}")
            
            for msg_num in range(1, messages_per_topic + 1):
                try:
                    # Generate data based on topic
                    data = self.generator.generate_gateway_data(topic_name, tag_count=20)
                    payload = json.dumps(data, indent=2)
                    
                    # Publish message
                    result = self.mqtt_client.publish(topic_name, payload, qos=qos)
                    result.wait_for_publish()
                    
                    print(f"  ✅ Message {msg_num}/{messages_per_topic} published")
                    print(f"     File ID: {data['file_id']}")
                    print(f"     Tags: {data['tag_count']}")
                    print(f"     Size: {len(payload)} bytes")
                    
                    total_published += 1
                    time.sleep(delay)
                    
                except Exception as e:
                    print(f"  ❌ Failed to publish message {msg_num}: {e}")
        
        print(f"\n{'='*80}")
        print(f"✅ Published {total_published} messages total")
        print(f"{'='*80}\n")
        
        return total_published
    
    def show_sample_message(self, topic_name: str):
        """Display a sample message for a topic"""
        print(f"\n{'='*80}")
        print(f"📋 Sample Message for Topic: {topic_name}")
        print(f"{'='*80}\n")
        
        data = self.generator.generate_gateway_data(topic_name, tag_count=5)
        payload = json.dumps(data, indent=2)
        
        print(payload)
        print(f"\n{'='*80}\n")
    
    def cleanup(self):
        """Close connections"""
        if self.mqtt_client:
            self.mqtt_client.disconnect()
        if self.db_conn:
            self.db_conn.close()
        print("✅ Connections closed")


def main():
    """Main execution"""
    print("\n" + "="*80)
    print("🔬 MQTT TOPIC-SPECIFIC TEST DATA GENERATOR")
    print("="*80)
    print("   This script:")
    print("   1. Reads active topics from mqtt_topic_config table")
    print("   2. Generates realistic OPC data for each topic")
    print("   3. Publishes test messages to MQTT broker")
    print("="*80 + "\n")
    
    publisher = MQTTTopicTestPublisher()
    
    try:
        # Connect to database
        if not publisher.connect_database():
            return
        
        # Connect to MQTT broker
        if not publisher.connect_mqtt():
            return
        
        # Get active topics
        topics = publisher.get_active_topics()
        
        if not topics:
            print("⚠️  No active topics found in database")
            return
        
        # Display topics
        print("\n📋 Active Topics:")
        print("-"*80)
        for topic in topics:
            print(f"  {topic['topic_id']}. {topic['topic_name']} (QoS: {topic['qos']}, Group: {topic['thread_group']})")
        print("-"*80 + "\n")
        
        # Show sample message
        sample_topic = [t for t in topics if '#' not in t['topic_name'] and '+' not in t['topic_name']][0]
        publisher.show_sample_message(sample_topic['topic_name'])
        
        input("Press Enter to start publishing test messages...")
        
        # Publish test data
        messages_per_topic = 5
        delay_seconds = 1.0
        
        total = publisher.publish_test_data(topics, messages_per_topic, delay_seconds)
        
        print("\n✅ Test data generation complete!")
        print(f"   Total messages published: {total}")
        print("\n📝 Next Steps:")
        print("   - Check MQTT subscriber logs for processing")
        print("   - Verify data in mqtt_audit_main table")
        print("   - Check historian_timeseries for tag data")
        print("   - Run: SELECT * FROM historian_raw.mqtt_audit_main ORDER BY first_received_time DESC LIMIT 10;")
        
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        publisher.cleanup()


if __name__ == "__main__":
    main()
