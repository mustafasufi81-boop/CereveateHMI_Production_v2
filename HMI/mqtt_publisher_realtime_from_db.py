"""
MQTT Real-Time Publisher - Reads actual tag values from historian_timeseries
Publishes the most recent tag values from the database for real-time HMI visualization
"""
import psycopg2
from psycopg2.extras import RealDictCursor
import paho.mqtt.client as mqtt
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Database Configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'Historian_data',
    'user': 'postgres',
    'password': 'Database@19c'
}

# MQTT Configuration
MQTT_BROKER = "127.0.0.1"
MQTT_PORT = 1883
PUBLISH_INTERVAL = 2  # seconds - publish latest values every 2 seconds

class RealTimePublisher:
    """Publishes actual tag values from historian_timeseries for real-time visualization"""
    
    def __init__(self):
        self.db_conn = None
        self.mqtt_client = None
        self.tag_metadata = {}  # Cache tag metadata from tag_master
        self.last_values = {}  # Track last published values to detect changes
        
    def connect_to_database(self):
        """Establish database connection"""
        try:
            self.db_conn = psycopg2.connect(**DB_CONFIG)
            print("✅ Connected to PostgreSQL database")
            return True
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            return False
    
    def load_tag_metadata(self):
        """Load tag metadata from tag_master for all enabled tags"""
        try:
            cursor = self.db_conn.cursor(cursor_factory=RealDictCursor)
            
            # Get all enabled tags
            query = """
                SELECT 
                    tag_id,
                    tag_name,
                    description,
                    eng_unit,
                    equipment,
                    plant,
                    area,
                    data_type,
                    enabled
                FROM historian_meta.tag_master
                WHERE enabled = true
                ORDER BY tag_name
            """
            
            cursor.execute(query)
            tags = cursor.fetchall()
            
            for tag in tags:
                self.tag_metadata[tag['tag_id']] = dict(tag)
            
            cursor.close()
            print(f"✅ Loaded metadata for {len(self.tag_metadata)} tags")
            
            if len(self.tag_metadata) > 0:
                print(f"\n📋 Sample tags loaded:")
                for i, tag_id in enumerate(list(self.tag_metadata.keys())[:5]):
                    tag = self.tag_metadata[tag_id]
                    eng_unit = tag.get('eng_unit', '')
                    print(f"   {i+1}. {tag['tag_name']} - {tag.get('description', 'N/A')} ({eng_unit})")
            
            return len(self.tag_metadata) > 0
            
        except Exception as e:
            print(f"❌ Failed to load tag metadata: {e}")
            return False
    
    def get_latest_tag_values(self) -> List[Dict]:
        """Query the most recent value for each tag from historian_timeseries"""
        try:
            cursor = self.db_conn.cursor(cursor_factory=RealDictCursor)
            
            tag_ids = list(self.tag_metadata.keys())
            
            if not tag_ids:
                return []
            
            # Get the most recent value for each tag (within last 5 minutes OR most recent available)
            query = """
                WITH latest_data AS (
                    SELECT DISTINCT ON (tag_id)
                        tag_id,
                        value_num as value,
                        quality,
                        opc_timestamp,
                        time
                    FROM historian_raw.historian_timeseries
                    WHERE tag_id = ANY(%s)
                    ORDER BY tag_id, time DESC
                )
                SELECT * FROM latest_data
                ORDER BY tag_id
            """
            
            cursor.execute(query, (tag_ids,))
            results = cursor.fetchall()
            cursor.close()
            
            return [dict(row) for row in results]
            
        except Exception as e:
            print(f"❌ Failed to query latest tag values: {e}")
            return []
    
    def connect_to_mqtt(self):
        """Connect to MQTT broker"""
        try:
            self.mqtt_client = mqtt.Client(client_id="realtime_publisher_from_db")
            
            def on_connect(client, userdata, flags, rc):
                if rc == 0:
                    print("✅ Connected to MQTT broker")
                else:
                    print(f"❌ MQTT connection failed with code {rc}")
            
            def on_publish(client, userdata, mid):
                pass  # Silent - don't print every publish
            
            self.mqtt_client.on_connect = on_connect
            self.mqtt_client.on_publish = on_publish
            
            self.mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self.mqtt_client.loop_start()
            
            time.sleep(1)  # Wait for connection
            return True
            
        except Exception as e:
            print(f"❌ MQTT connection failed: {e}")
            return False
    
    def determine_tag_status(self, quality: str) -> str:
        """Determine tag status based on quality"""
        # If quality is not GOOD, mark as offline
        if quality != 'GOOD':
            return 'offline'
        
        return 'normal'
    
    def publish_realtime_data(self):
        """Publish real-time tag data from historian_timeseries"""
        try:
            # Get latest values from database
            tag_values = self.get_latest_tag_values()
            
            if not tag_values:
                print("⚠️  No data found in historian_timeseries for enabled tags")
                return
            
            # Group tags for publishing
            tags_to_publish = []
            
            for row in tag_values:
                tag_id = row['tag_id']
                value = row['value']
                quality = row['quality']
                opc_timestamp = row.get('opc_timestamp') or row.get('time')
                
                # Skip if value is None
                if value is None:
                    continue
                
                # Clean up quality field (might be char or string)
                if quality:
                    quality = str(quality).strip()
                if not quality or quality == '':
                    quality = 'UNKNOWN'
                
                # Get metadata
                meta = self.tag_metadata.get(tag_id, {})
                tag_name = meta.get('tag_name', tag_id)
                description = meta.get('description', '')
                eng_unit = meta.get('eng_unit', '')
                equipment = meta.get('equipment', 'UNKNOWN')
                plant = meta.get('plant', '')
                area = meta.get('area', '')
                
                # Determine status
                status = self.determine_tag_status(quality)
                
                # Build tag payload
                tag_payload = {
                    'tagId': tag_id,
                    'tagName': tag_name,
                    'value': float(value),
                    'quality': quality,
                    'unit': eng_unit,
                    'timestamp': opc_timestamp.isoformat() if opc_timestamp else datetime.utcnow().isoformat(),
                    'description': description,
                    'equipment': equipment,
                    'plant': plant,
                    'area': area,
                    'status': status
                }
                
                tags_to_publish.append(tag_payload)
                
                # Track for change detection
                self.last_values[tag_id] = value
            
            # Publish as single message with all tags
            payload = {
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'source': 'historian_timeseries',
                'count': len(tags_to_publish),
                'tags': tags_to_publish
            }
            
            topic = "plant/realtime/tags"
            self.mqtt_client.publish(topic, json.dumps(payload))
            
            print(f"📤 Published {len(tags_to_publish)} tags from historian_timeseries (topic: {topic})")
            
            # Show sample values and check data age
            if len(tags_to_publish) > 0:
                sample = tags_to_publish[0]
                print(f"   Sample: {sample['tagName']} = {sample['value']} {sample['unit']} ({sample['status']})")
                
                # Check if data is old
                if tag_values and tag_values[0].get('time'):
                    latest_time = tag_values[0]['time']
                    age = datetime.now(latest_time.tzinfo) - latest_time
                    if age.total_seconds() > 300:  # More than 5 minutes old
                        print(f"   ⚠️  WARNING: Data is {int(age.total_seconds()/60)} minutes old! Check data ingestion.")
            
        except Exception as e:
            print(f"❌ Failed to publish: {e}")
            import traceback
            traceback.print_exc()
    
    def run(self):
        """Main publishing loop"""
        print("\n" + "="*70)
        print("MQTT REAL-TIME PUBLISHER FROM historian_timeseries")
        print("="*70)
        
        # Connect to database
        if not self.connect_to_database():
            return
        
        # Load tag metadata
        if not self.load_tag_metadata():
            print("❌ No enabled tags found in tag_master. Cannot continue.")
            return
        
        # Connect to MQTT
        if not self.connect_to_mqtt():
            return
        
        print(f"\n🚀 Started publishing real-time data from historian_timeseries")
        print(f"   Publishing every {PUBLISH_INTERVAL} seconds")
        print(f"   Press Ctrl+C to stop\n")
        
        try:
            cycle = 0
            while True:
                cycle += 1
                print(f"\n{'='*70}")
                print(f"Cycle #{cycle} - {datetime.now().strftime('%H:%M:%S')}")
                print(f"{'='*70}")
                
                self.publish_realtime_data()
                
                time.sleep(PUBLISH_INTERVAL)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Shutting down...")
        finally:
            if self.mqtt_client:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            if self.db_conn:
                self.db_conn.close()
            print("✅ Cleanup complete")

if __name__ == "__main__":
    publisher = RealTimePublisher()
    publisher.run()
