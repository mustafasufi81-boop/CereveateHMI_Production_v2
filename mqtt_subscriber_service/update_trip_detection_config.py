"""
Update Trip Detection Configuration from tag_master
Dynamically loads equipment from database and updates service_config.yaml
"""

import psycopg2
import yaml
import os
from pathlib import Path

# Database Configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'Historian_data',
    'user': 'postgres',
    'password': 'Database@19c'
}

def load_equipment_from_tag_master():
    """Load all equipment with trip-related tags from tag_master"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Get unique equipment with their properties
        cursor.execute("""
            SELECT 
                equipment,
                MAX(equipment_criticality) as criticality,
                STRING_AGG(DISTINCT trip_category, ', ') as trip_categories,
                MAX(plant) as plant,
                MAX(area) as area,
                COUNT(*) as tag_count
            FROM historian_meta.tag_master
            WHERE equipment IS NOT NULL 
              AND equipment != ''
              AND enabled = true
            GROUP BY equipment
            ORDER BY MAX(equipment_criticality) DESC NULLS LAST, equipment
        """)
        
        equipment_rows = cursor.fetchall()
        
        equipment_mappings = []
        
        print(f"\n✅ Found {len(equipment_rows)} unique equipment in tag_master:")
        print(f"  {'Equipment':<30} {'Criticality':<12} {'Trip Categories':<30} {'Tags'}")
        print(f"  {'-'*30} {'-'*12} {'-'*30} {'-'*6}")
        
        for row in equipment_rows:
            equipment, criticality, trip_cats, plant, area, tag_count = row
            
            # Normalize equipment name for tag IDs
            equipment_normalized = equipment.upper().replace(' ', '_').replace('-', '_')
            
            # Determine run_status_tag_id based on equipment name
            # Special case for Turbine variants
            if 'TURBINE' in equipment_normalized:
                run_status_tag = f"{equipment_normalized}_STATUS"  # Boolean
            else:
                run_status_tag = f"{equipment_normalized}_RUN_STATUS"  # Integer
            
            # Estimate rated capacity based on criticality and equipment type
            if 'TURBINE' in equipment.upper():
                rated_capacity = 270.0
            elif 'GENERATOR' in equipment.upper():
                rated_capacity = 300.0
            elif 'BOILER' in equipment.upper():
                rated_capacity = 500.0
            elif 'COMPRESSOR' in equipment.upper():
                rated_capacity = 80.0
            elif 'PUMP' in equipment.upper():
                rated_capacity = 30.0
            else:
                rated_capacity = (criticality or 3) * 50.0
            
            mapping = {
                'equipment_id': equipment,
                'equipment_name': equipment,
                'run_status_tag_id': run_status_tag,
                'trip_tag_id': f"{equipment_normalized}_TRIP_STATUS",
                'rated_capacity_mw': rated_capacity,
                'revenue_per_mwh': 60.0,
                'criticality': criticality or 3
            }
            
            equipment_mappings.append(mapping)
            
            print(f"  {equipment:<30} {str(criticality or 'N/A'):<12} {str(trip_cats or 'N/A'):<30} {tag_count}")
        
        cursor.close()
        conn.close()
        
        return equipment_mappings
        
    except Exception as e:
        print(f"❌ Failed to load equipment from tag_master: {e}")
        import traceback
        traceback.print_exc()
        return []

def update_config_file(equipment_mappings):
    """Update service_config.yaml with equipment mappings"""
    try:
        config_path = Path(__file__).parent / 'config' / 'service_config.yaml'
        
        if not config_path.exists():
            print(f"❌ Config file not found: {config_path}")
            return False
        
        # Read existing config
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Update equipment mappings
        if 'trip_detection' not in config:
            config['trip_detection'] = {}
        
        config['trip_detection']['equipment_mappings'] = equipment_mappings
        
        # Backup original config
        backup_path = config_path.with_suffix('.yaml.backup')
        with open(backup_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        
        # Write updated config
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        
        print(f"\n✅ Updated config file: {config_path}")
        print(f"✅ Backup saved to: {backup_path}")
        print(f"✅ Added {len(equipment_mappings)} equipment mappings")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to update config file: {e}")
        import traceback
        traceback.print_exc()
        return False

def verify_trip_detection_enabled(config_path):
    """Verify trip detection is enabled in config"""
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        trip_config = config.get('trip_detection', {})
        enabled = trip_config.get('enabled', False)
        
        print(f"\n📋 Trip Detection Configuration:")
        print(f"  Enabled: {enabled}")
        print(f"  Alarm window: {trip_config.get('alarm_to_trip_window_seconds', 'N/A')}s")
        print(f"  Min alarm priority: {trip_config.get('minimum_alarm_priority', 'N/A')}")
        print(f"  Equipment count: {len(trip_config.get('equipment_mappings', []))}")
        
        if not enabled:
            print("\n⚠️  WARNING: Trip detection is DISABLED in config!")
            print("   Set 'trip_detection.enabled: true' to enable")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to verify config: {e}")
        return False

def main():
    print("=" * 80)
    print("UPDATE TRIP DETECTION CONFIGURATION FROM TAG_MASTER")
    print("=" * 80)
    
    # Step 1: Load equipment from tag_master
    print("\n📦 Step 1: Loading equipment from tag_master...")
    equipment_mappings = load_equipment_from_tag_master()
    
    if not equipment_mappings:
        print("❌ No equipment loaded. Exiting.")
        return
    
    # Step 2: Update config file
    print("\n📝 Step 2: Updating service_config.yaml...")
    success = update_config_file(equipment_mappings)
    
    if not success:
        print("❌ Failed to update config. Exiting.")
        return
    
    # Step 3: Verify configuration
    config_path = Path(__file__).parent / 'config' / 'service_config.yaml'
    print("\n✅ Step 3: Verifying configuration...")
    verify_trip_detection_enabled(config_path)
    
    print("\n" + "=" * 80)
    print("✨ Configuration update complete!")
    print("=" * 80)
    print("\n📌 Next Steps:")
    print("  1. Review the updated config:")
    print(f"     {config_path}")
    print("  2. Restart MQTT Subscriber Service")
    print("  3. Run MQTT Publisher to generate trips:")
    print("     python HMI/test_mqtt_publisher_from_db.py")
    print("  4. Monitor trip events in database:")
    print("     SELECT * FROM historian_raw.trip_event_tracking ORDER BY trip_time DESC;")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
