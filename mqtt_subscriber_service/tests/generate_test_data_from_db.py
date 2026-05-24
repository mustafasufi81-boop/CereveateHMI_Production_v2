"""
Generate MQTT Test Data - Database-Driven Version
Reads PLC configurations from historian_raw.mqtt_topic_config table
Maps plc_name to plcId in MQTT JSON payload
Publishes each PLC's data to its respective topic
"""
import json
import random
import paho.mqtt.client as mqtt
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
import signal
import sys
import psycopg2

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
PUBLISH_INTERVAL = 1.0  # seconds
ALARM_PROBABILITY = 0.4  # 40% chance to include alarm_summary

# Global state
running = True
stats = {
    'start_time': None,
    'plc_stats': {}  # Per-PLC statistics
}
plc_configs = []

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    global running
    print("\n\n🛑 Stopping data generation...")
    running = False

signal.signal(signal.SIGINT, signal_handler)

def load_plc_configs_from_db():
    """Load PLC configurations from database"""
    global plc_configs
    
    print("📊 Loading PLC configurations from database...")
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT topic_id, topic_name, plc_name, qos, thread_group
            FROM historian_raw.mqtt_topic_config
            WHERE is_active = TRUE
            ORDER BY topic_id
        """)
        
        rows = cursor.fetchall()
        
        for row in rows:
            topic_id, topic_name, plc_name, qos, thread_group = row
            
            # Extract plant and area from topic or use defaults
            if 'plant_a' in topic_name.lower():
                plant = 'Steel_Plant_A'
                area = 'Production_Area_A'
            elif 'plant_b' in topic_name.lower():
                plant = 'Steel_Plant_B'
                area = 'Production_Area_B'
            elif 'test' in topic_name.lower():
                plant = 'Test_Plant'
                area = 'Test_Area'
            else:
                plant = 'Default_Plant'
                area = 'Default_Area'
            
            # Create spool directory path
            spool_base = Path(__file__).parent / f"spool_{plc_name.lower()}" / "pending"
            
            config = {
                'topic_id': topic_id,
                'plc_id': plc_name,  # Map plc_name to plcId
                'plc_name': plc_name,
                'spool_dir': spool_base,
                'topic': topic_name,
                'qos': qos,
                'plant': plant,
                'area': area
            }
            
            plc_configs.append(config)
            
            # Initialize stats
            stats['plc_stats'][plc_name] = {
                'messages_sent': 0,
                'messages_failed': 0,
                'alarms_sent': 0,
                'last_values': {}
            }
        
        cursor.close()
        conn.close()
        
        print(f"✅ Loaded {len(plc_configs)} PLC configurations")
        return True
        
    except Exception as e:
        print(f"❌ Error loading PLC configurations: {e}")
        return False

def generate_realistic_value(tag_name, last_value=None, base_value=None, variance=0.1):
    """Generate realistic values that change gradually over time"""
    if last_value is None:
        return base_value
    
    # Add gradual drift and small random changes
    max_change = abs(base_value * variance)
    change = random.uniform(-max_change, max_change)
    new_value = last_value + change
    
    # Keep within reasonable bounds (±20% of base)
    min_val = base_value * 0.8
    max_val = base_value * 1.2
    new_value = max(min_val, min(max_val, new_value))
    
    return new_value

def generate_mqtt_payload(plc_config, sequence_num):
    """Generate realistic MQTT payload for a PLC matching the required format"""
    plc_id = plc_config['plc_id']
    plc_stats = stats['plc_stats'][plc_id]
    
    now = datetime.now(timezone.utc)
    
    # Define base values for tags with scan rates
    tag_configs = {
        'Blastfurnace_Tuyer1_Pressure': {'base': 22.0, 'dataType': 'float', 'scanRateMs': 200, 'samples': 5},
        'Boiler_Inlet_Pressure': {'base': 7.9, 'dataType': 'float', 'scanRateMs': 200, 'samples': 5},
        'Boiler_Inlet_Temp': {'base': 71.0, 'dataType': 'float', 'scanRateMs': 200, 'samples': 5},
        'Cooling_FAN_SPEED': {'base': 65.0, 'dataType': 'float', 'scanRateMs': 200, 'samples': 5},
        'Production_Rate': {'base': 150.0, 'dataType': 'float', 'scanRateMs': 1000, 'samples': 1},
        'Tank_Level': {'base': 75.0, 'dataType': 'float', 'scanRateMs': 500, 'samples': 2},
        'Valve_Position': {'base': 46.5, 'dataType': 'float', 'scanRateMs': 500, 'samples': 1},
        'Motor_Current': {'base': 45.3, 'dataType': 'float', 'scanRateMs': 200, 'samples': 5},
        'Conveyor_Speed': {'base': 1.8, 'dataType': 'float', 'scanRateMs': 500, 'samples': 2},
        'Quality_Index': {'base': 95.5, 'dataType': 'float', 'scanRateMs': 1000, 'samples': 1},
    }
    
    # Generate tag data
    values = []
    alarm_summary = []
    total_samples = 0
    
    for tag_name, config in tag_configs.items():
        # Get or initialize last value
        last_val = plc_stats['last_values'].get(tag_name, config['base'])
        
        # Generate new value
        new_value = generate_realistic_value(tag_name, last_val, config['base'], variance=0.02)
        plc_stats['last_values'][tag_name] = new_value
        
        # Create tag entry
        tag_entry = {
            'plcId': plc_id,
            'tag': tag_name,
            'address': tag_name,
            'dataType': config['dataType'],
            'scanRateMs': config['scanRateMs'],
            'sampleCount': config['samples'],
            'value': round(new_value, 2),
            'quality': 'Good',
            'timestamp': now.isoformat().replace('+00:00', 'Z')
        }
        
        # Generate samples if sampleCount > 1
        if config['samples'] > 1:
            samples = []
            sample_interval_ms = config['scanRateMs']
            
            for i in range(config['samples']):
                sample_time = now - timedelta(milliseconds=(config['samples'] - i - 1) * sample_interval_ms)
                sample_value = generate_realistic_value(tag_name, new_value, config['base'], variance=0.01)
                
                samples.append({
                    'value': round(sample_value, 2),
                    'quality': 'Good',
                    'timestamp': sample_time.isoformat().replace('+00:00', 'Z')
                })
            
            tag_entry['samples'] = samples
            total_samples += len(samples)
        else:
            total_samples += 1
        
        values.append(tag_entry)
    
    # Create payload with correct structure
    payload = {
        'timestamp': now.isoformat().replace('+00:00', 'Z'),
        'publishIntervalMs': 1000,
        'tagCount': len(values),
        'totalSamples': total_samples,
        'values': values
    }
    
    # Optionally add alarm_summary if needed
    if random.random() < ALARM_PROBABILITY:
        alarm_detail = {
            'tag': random.choice(list(tag_configs.keys())),
            'severity': random.choice(['warning', 'alarm']),
            'message': 'Value exceeded threshold',
            'timestamp': now.isoformat().replace('+00:00', 'Z')
        }
        payload['alarm_summary'] = [alarm_detail]
        plc_stats['alarms_sent'] += 1
    
    return payload

def save_to_file(plc_config, payload):
    """Save payload to JSON file in spool directory (CURRENTLY DISABLED - function not called)"""
    try:
        # Ensure spool directory exists
        plc_config['spool_dir'].mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')[:-3]
        filename = f"{timestamp}.json"
        filepath = plc_config['spool_dir'] / filename
        
        # Write JSON file
        with open(filepath, 'w') as f:
            json.dump(payload, f, indent=2)
        
        return filename
    except Exception as e:
        print(f"❌ Error saving file: {e}")
        return None

def publish_message(client, plc_config, payload):
    """Publish message to MQTT broker"""
    try:
        topic = plc_config['topic']
        qos = plc_config['qos']
        
        # Convert payload to JSON string
        payload_json = json.dumps(payload)
        
        # Publish to MQTT
        result = client.publish(topic, payload_json, qos=qos)
        
        return result.rc == mqtt.MQTT_ERR_SUCCESS
    except Exception as e:
        print(f"❌ Error publishing message: {e}")
        return False

def print_statistics():
    """Print final statistics"""
    elapsed = (datetime.now(timezone.utc) - stats['start_time']).total_seconds()
    total_messages = sum(s['messages_sent'] for s in stats['plc_stats'].values())
    
    print("\n" + "="*80)
    print("📊 STATISTICS")
    print("="*80)
    print(f"Runtime: {int(elapsed)} seconds | Total Messages: {total_messages} | Rate: {total_messages/elapsed:.2f} msg/sec")
    print()
    
    for plc_config in plc_configs:
        plc_name = plc_config['plc_name']
        plc_stats = stats['plc_stats'][plc_name]
        success_rate = (plc_stats['messages_sent'] / (plc_stats['messages_sent'] + plc_stats['messages_failed']) * 100) if (plc_stats['messages_sent'] + plc_stats['messages_failed']) > 0 else 0
        
        print(f"{plc_name} ({plc_config['topic']}):")
        print(f"  Messages: {plc_stats['messages_sent']} | Failed: {plc_stats['messages_failed']} | Success: {success_rate:.1f}% | Alarms: {plc_stats['alarms_sent']}")
    
    print("="*80)

def continuous_publisher():
    """Continuously publish data for all PLCs"""
    global running
    
    print("\n" + "="*80)
    print("🔄 DATABASE-DRIVEN MULTI-PLC MQTT TEST DATA GENERATOR")
    print("="*80)
    print(f"MQTT Broker:     {MQTT_BROKER}:{MQTT_PORT}")
    print(f"Interval:        {PUBLISH_INTERVAL} seconds")
    print(f"Alarm Probability: {ALARM_PROBABILITY*100:.0f}%")
    print("="*80)
    
    # Load PLC configurations from database
    if not load_plc_configs_from_db():
        print("❌ Failed to load PLC configurations. Exiting.")
        return
    
    if not plc_configs:
        print("⚠️  No active PLC configurations found in database. Exiting.")
        return
    
    print("\nPLC Configurations:")
    for i, config in enumerate(plc_configs, 1):
        print(f"  {i}. {config['plc_name']}")
        print(f"     Topic: {config['topic']}")
        print(f"     QoS: {config['qos']}")
        print(f"     Spool: {config['spool_dir']}")
        print(f"     Plant: {config['plant']} / {config['area']}")
    
    print("="*80)
    print("\n⌨️  Press Ctrl+C to stop...\n")
    
    # Create spool directories
    for config in plc_configs:
        config['spool_dir'].mkdir(parents=True, exist_ok=True)
    
    print("✅ All spool directories ready\n")
    
    # Connect to MQTT broker
    client = mqtt.Client(f"db_driven_publisher_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")
    
    print("📡 Connecting to MQTT broker...")
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        print("✅ Connected to MQTT broker\n")
    except Exception as e:
        print(f"❌ Failed to connect to MQTT broker: {e}")
        return
    
    # Start publishing
    stats['start_time'] = datetime.now(timezone.utc)
    sequence = 0
    
    try:
        while running:
            sequence += 1
            
            for plc_config in plc_configs:
                plc_name = plc_config['plc_name']
                plc_stats = stats['plc_stats'][plc_name]
                
                # Generate payload
                payload = generate_mqtt_payload(plc_config, sequence)
                
                # Save to file (DISABLED - not creating JSON files)
                # filename = save_to_file(plc_config, payload)
                filename = "N/A"
                
                # Publish to MQTT
                success = publish_message(client, plc_config, payload)
                
                if success:
                    plc_stats['messages_sent'] += 1
                    
                    # Print status
                    timestamp = datetime.now(timezone.utc).strftime('%H:%M:%S.%f')[:-3]
                    payload_size = len(json.dumps(payload))
                    alarm_icon = f"🚨 {len(payload.get('alarm_summary', []))}" if 'alarm_summary' in payload else ""
                    topic_short = plc_config['topic'].split('/')[-1]
                    
                    # Get key values from the values array
                    pressure = next((t['value'] for t in payload['values'] if t['tag'] == 'Blastfurnace_Tuyer1_Pressure'), 0)
                    temp = next((t['value'] for t in payload['values'] if t['tag'] == 'Boiler_Inlet_Temp'), 0)
                    flow = next((t['value'] for t in payload['values'] if t['tag'] == 'Cooling_FAN_SPEED'), 0)
                    
                    print(f"[{timestamp}] 📤 {plc_name[-4:]} # {sequence:2d} | {payload_size:6d}b | P:{pressure:.2f} T:{temp:.1f} F:{flow:.1f} {alarm_icon:15s} | {topic_short:15s} | 📁 {filename}")
                else:
                    plc_stats['messages_failed'] += 1
            
            # Wait for next interval
            time.sleep(PUBLISH_INTERVAL)
            
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping data generation...")
    finally:
        # Cleanup
        print("\n🔌 Disconnecting from MQTT broker...")
        client.loop_stop()
        client.disconnect()
        
        # Print final statistics
        print_statistics()
        
        print("\n✅ Data generation stopped cleanly")
        # print("\n📁 JSON files saved to:")
        # for config in plc_configs:
        #     print(f"   {config['plc_name']}: {config['spool_dir']}")
        print("\n📝 Next Steps:")
        print("   1. Check MQTT Subscriber Service logs")
        print("   2. Query database:")
        print("      SELECT topic_name, plc_name, COUNT(*) FROM historian_raw.mqtt_audit_main GROUP BY topic_name, plc_name;")
        print("      SELECT tag_id, time, value_num, quality")
        print("      FROM historian_raw.timeseries_data")
        print("      ORDER BY time DESC LIMIT 20;")
        print("")

def main():
    """Main execution"""
    continuous_publisher()

if __name__ == "__main__":
    main()
