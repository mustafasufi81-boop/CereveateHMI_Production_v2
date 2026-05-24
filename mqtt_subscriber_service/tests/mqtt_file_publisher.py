"""
MQTT File-Based Publisher
Generates JSON files in spool/pending directory and publishes to MQTT broker
"""
import json
import os
import time
from datetime import datetime
from pathlib import Path
import paho.mqtt.client as mqtt

# MQTT Configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "test/gateway/data"

# Spool Directory
SPOOL_DIR = Path(__file__).parent / "spool" / "pending"
PROCESSED_DIR = Path(__file__).parent / "spool" / "processed"
FAILED_DIR = Path(__file__).parent / "spool" / "failed"

def create_directories():
    """Create spool directories"""
    SPOOL_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    FAILED_DIR.mkdir(parents=True, exist_ok=True)
    print(f"✅ Created directories:")
    print(f"   - Pending: {SPOOL_DIR}")
    print(f"   - Processed: {PROCESSED_DIR}")
    print(f"   - Failed: {FAILED_DIR}")

def generate_opc_data_file(count=1):
    """Generate OPC data JSON files in spool/pending directory"""
    print(f"\n{'='*80}")
    print(f"📝 Generating {count} OPC data file(s)")
    print(f"{'='*80}\n")
    
    template_file = Path(__file__).parent.parent / "latest_sample_mqtt_data.json"
    
    if not template_file.exists():
        print(f"❌ Template file not found: {template_file}")
        return []
    
    # Load template
    with open(template_file, 'r') as f:
        template_data = json.load(f)
    
    generated_files = []
    
    for i in range(count):
        # Generate timestamp-based filename: yyyymmddHHMMSSfff.json
        now = datetime.now()
        filename = now.strftime("%Y%m%d%H%M%S%f")[:-3] + ".json"  # Remove last 3 digits, keep milliseconds
        filepath = SPOOL_DIR / filename
        
        # Update template data with current timestamp
        data = template_data.copy()
        data['timestamp'] = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        
        # Update all value timestamps
        for value_entry in data.get('values', []):
            value_entry['timestamp'] = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            for sample in value_entry.get('samples', []):
                sample['timestamp'] = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        
        # Write to file
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        generated_files.append(filepath)
        print(f"  ✅ Generated: {filename}")
        print(f"     Tags: {data.get('tagCount', 0)}")
        print(f"     Samples: {data.get('totalSamples', 0)}")
        
        # Small delay to ensure unique filenames
        if i < count - 1:
            time.sleep(0.01)
    
    print(f"\n✅ Generated {len(generated_files)} file(s) in {SPOOL_DIR}\n")
    return generated_files

def publish_spool_files():
    """Publish all JSON files from spool/pending directory to MQTT"""
    print(f"\n{'='*80}")
    print(f"📤 Publishing files from spool directory to MQTT")
    print(f"{'='*80}\n")
    
    # Get all JSON files in pending directory
    json_files = sorted(SPOOL_DIR.glob("*.json"))
    
    if not json_files:
        print("⚠️  No JSON files found in spool/pending directory")
        return
    
    print(f"Found {len(json_files)} file(s) to publish\n")
    
    # Connect to MQTT broker
    try:
        client = mqtt.Client(f"file_publisher_{datetime.now().strftime('%Y%m%d%H%M%S')}")
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        print(f"✅ Connected to MQTT broker: {MQTT_BROKER}:{MQTT_PORT}\n")
    except Exception as e:
        print(f"❌ Failed to connect to MQTT broker: {e}")
        return
    
    published_count = 0
    failed_count = 0
    
    for json_file in json_files:
        try:
            # Read JSON file
            with open(json_file, 'r') as f:
                data = json.load(f)
            
            payload = json.dumps(data)
            
            # Publish to MQTT
            result = client.publish(MQTT_TOPIC, payload, qos=1)
            result.wait_for_publish()
            
            print(f"  ✅ Published: {json_file.name}")
            print(f"     Topic: {MQTT_TOPIC}")
            print(f"     Size: {len(payload)} bytes")
            print(f"     Tags: {data.get('tagCount', 0)}")
            
            # Move to processed directory
            processed_path = PROCESSED_DIR / json_file.name
            json_file.rename(processed_path)
            print(f"     Moved to: processed/\n")
            
            published_count += 1
            time.sleep(0.5)  # Small delay between publishes
            
        except Exception as e:
            print(f"  ❌ Failed to publish {json_file.name}: {e}")
            # Move to failed directory
            failed_path = FAILED_DIR / json_file.name
            json_file.rename(failed_path)
            print(f"     Moved to: failed/\n")
            failed_count += 1
    
    client.disconnect()
    
    print(f"{'='*80}")
    print(f"✅ Publishing complete!")
    print(f"   Published: {published_count}")
    print(f"   Failed: {failed_count}")
    print(f"{'='*80}\n")

def main():
    """Main execution"""
    print("\n" + "="*80)
    print("🔬 MQTT FILE-BASED PUBLISHER")
    print("="*80)
    print("   This script:")
    print("   1. Generates OPC data JSON files in spool/pending/")
    print("   2. Publishes them to MQTT broker topic: test/gateway/data")
    print("   3. Moves published files to spool/processed/")
    print("="*80 + "\n")
    
    # Create directories
    create_directories()
    
    # Ask user how many files to generate
    print("\nOptions:")
    print("  1. Generate and publish 1 file")
    print("  2. Generate and publish 5 files")
    print("  3. Generate and publish 10 files")
    print("  4. Only publish existing files in spool/pending/")
    print("  5. Exit")
    
    choice = input("\nSelect option (1-5): ").strip()
    
    if choice == "1":
        generate_opc_data_file(count=1)
        publish_spool_files()
    elif choice == "2":
        generate_opc_data_file(count=5)
        publish_spool_files()
    elif choice == "3":
        generate_opc_data_file(count=10)
        publish_spool_files()
    elif choice == "4":
        publish_spool_files()
    elif choice == "5":
        print("\n👋 Exiting...")
        return
    else:
        print("\n❌ Invalid choice")
        return
    
    # Show verification steps
    print("\n📝 Verification Steps:")
    print("="*80)
    print("1. Check service logs:")
    print("   Get-Content C:\\Shakil\\Cerevate\\OPC_REPOS\\mqtt_subscriber_service\\logs\\service_debug.txt -Tail 50")
    print("\n2. Check database for received messages:")
    print("   SELECT * FROM historian_raw.mqtt_audit_main ORDER BY first_received_time DESC LIMIT 10;")
    print("\n3. Check timeseries data:")
    print("   SELECT * FROM historian_raw.historian_timeseries ORDER BY time DESC LIMIT 20;")
    print("\n4. Check processed files:")
    print(f"   {PROCESSED_DIR}")
    print("="*80)

if __name__ == "__main__":
    main()
