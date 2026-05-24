"""
Generate MQTT Test Data - Multi-PLC Version
Creates realistic test data files with current timestamps and publishes to MQTT broker
Enhanced: Continuous data generation every 1 second with dynamic values
Features:
- 3 PLC streams (PLC_001, PLC_002, PLC_003)
- Separate spool directories and MQTT topics
- Random alarm generation (not always included)
"""
import json
import random
import paho.mqtt.client as mqtt
from datetime import datetime, timedelta
from pathlib import Path
import time
import signal
import sys

# Configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
QOS = 1
PUBLISH_INTERVAL = 1.0  # seconds
ALARM_PROBABILITY = 0.4  # 40% chance to include alarm_summary when thresholds exceeded

# Multi-PLC Configuration
PLC_CONFIGS = [
    {
        'plc_id': 'Rockwel_PLC_001',
        'spool_dir': Path(__file__).parent / "spool" / "pending",
        'topic': 'test/gateway/data',
        'plant': 'Steel_Plant_A',
        'area': 'Test_Area'
    },
    {
        'plc_id': 'Rockwel_PLC_002',
        'spool_dir': Path(__file__).parent / "spool2" / "pending",
        'topic': 'production/plant_b/gateway_002',
        'plant': 'Steel_Plant_B',
        'area': 'Production_Area'
    },
    {
        'plc_id': 'Rockwell_PLC01',
        'spool_dir': Path(__file__).parent / "spool3" / "pending",
        'topic': 'production/plant_b/gateway_001',
        'plant': 'Steel_Plant_B',
        'area': 'Assembly_Area'
    }
]

# Global state for continuous operation
running = True
stats = {
    'start_time': None,
    'plc_stats': {}  # Per-PLC statistics
}

# Initialize per-PLC stats
for plc_config in PLC_CONFIGS:
    plc_id = plc_config['plc_id']
    stats['plc_stats'][plc_id] = {
        'messages_sent': 0,
        'messages_failed': 0,
        'alarms_sent': 0,
        'last_values': {}  # Track last values for realistic changes
    }

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    global running
    print("\n\n🛑 Stopping data generation...")
    running = False

def generate_realistic_value(tag_name, last_value=None, base_value=None, variance=0.1):
    """
    Generate realistic values that change gradually over time
    
    Args:
        tag_name: Name of the tag
        last_value: Previous value (for smooth transitions)
        base_value: Base/normal operating value
        variance: Maximum percentage change per update
    
    Returns:
        New value with realistic variation
    """
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

def should_include_alarm():
    """
    Randomly decide if alarm_summary should be included
    Returns True with ALARM_PROBABILITY chance
    """
    return random.random() < ALARM_PROBABILITY

def generate_timestamp_samples(base_time, count=5, interval_ms=200):
    """Generate timestamp samples going backward from base_time"""
    samples = []
    for i in range(count):
        offset = (count - i) * interval_ms
        ts = base_time - timedelta(milliseconds=offset)
        samples.append(ts.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z")
    return samples

def generate_test_data(plc_config):
    """
    Generate comprehensive test MQTT data with realistic dynamic values
    
    Args:
        plc_config: Dictionary with PLC configuration (plc_id, topic, plant, area)
    
    Returns:
        tuple: (message_dict, base_pressure, base_temp, base_fan_speed, has_alarm_summary)
    """
    plc_id = plc_config['plc_id']
    plant = plc_config['plant']
    area = plc_config['area']
    
    # Current timestamp with milliseconds
    now = datetime.utcnow()
    timestamp = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    
    # Generate sample timestamps (5 samples at 200ms intervals)
    sample_timestamps = generate_timestamp_samples(now, 5, 200)
    
    # Get or initialize last values for smooth transitions (per PLC)
    last_vals = stats['plc_stats'][plc_id]['last_values']
    
    # Generate realistic values that change gradually
    base_pressure = generate_realistic_value(
        'pressure', 
        last_vals.get('pressure'), 
        22.0, 
        0.02  # 2% max change
    )
    base_temp = generate_realistic_value(
        'temperature', 
        last_vals.get('temperature'), 
        71.0, 
        0.015  # 1.5% max change
    )
    base_fan_speed = generate_realistic_value(
        'fan_speed', 
        last_vals.get('fan_speed'), 
        65.0, 
        0.03  # 3% max change
    )
    base_production = generate_realistic_value(
        'production', 
        last_vals.get('production'), 
        150.0, 
        0.05  # 5% max change
    )
    base_tank_level = generate_realistic_value(
        'tank_level', 
        last_vals.get('tank_level'), 
        75.0, 
        0.02
    )
    base_pump_speed = generate_realistic_value(
        'pump_speed', 
        last_vals.get('pump_speed'), 
        1500.0, 
        0.02
    )
    base_flow_rate = generate_realistic_value(
        'flow_rate', 
        last_vals.get('flow_rate'), 
        125.0, 
        0.025
    )
    base_reactor_temp = generate_realistic_value(
        'reactor_temp', 
        last_vals.get('reactor_temp'), 
        185.0, 
        0.01
    )
    base_power = generate_realistic_value(
        'power', 
        last_vals.get('power'), 
        850.0, 
        0.04
    )
    
    # Update last values for this PLC
    stats['plc_stats'][plc_id]['last_values'] = {
        'pressure': base_pressure,
        'temperature': base_temp,
        'fan_speed': base_fan_speed,
        'production': base_production,
        'tank_level': base_tank_level,
        'pump_speed': base_pump_speed,
        'flow_rate': base_flow_rate,
        'reactor_temp': base_reactor_temp,
        'power': base_power
    }
    
    message = {
        "timestamp": timestamp,
        "publishIntervalMs": 1000,
        "tagCount": 15,
        "totalSamples": 75,
        "values": [
            # Tag 1: Blast Furnace Pressure (with samples)
            {
                "plcId": plc_id,
                "tag": "Blastfurnace_Tuyer1_Pressure",
                "address": "Blastfurnace_Tuyer1_Pressure",
                "dataType": "float",
                "scanRateMs": 200,
                "sampleCount": 5,
                "samples": [
                    {"value": round(base_pressure + random.uniform(-0.01, 0.01), 2), 
                     "quality": "Good", 
                     "timestamp": sample_timestamps[i]}
                    for i in range(5)
                ],
                "value": round(base_pressure, 2),
                "quality": "Good",
                "timestamp": timestamp
            },
            # Tag 2: Boiler Inlet Pressure (with samples)
            {
                "plcId": plc_id,
                "tag": "Boiler_Inlet_Pressure",
                "address": "Boiler_Inlet_Pressure",
                "dataType": "float",
                "scanRateMs": 200,
                "sampleCount": 5,
                "samples": [
                    {"value": round(7.9 + random.uniform(-0.01, 0.01), 2),
                     "quality": "Good",
                     "timestamp": sample_timestamps[i]}
                    for i in range(5)
                ],
                "value": round(7.9 + random.uniform(-0.02, 0.02), 2),
                "quality": "Good",
                "timestamp": timestamp
            },
            # Tag 3: Boiler Inlet Temperature (with samples)
            {
                "plcId": plc_id,
                "tag": "Boiler_Inlet_Temp",
                "address": "Boiler_Inlet_Temp",
                "dataType": "float",
                "scanRateMs": 200,
                "sampleCount": 5,
                "samples": [
                    {"value": round(base_temp + random.uniform(-0.02, 0.02), 2),
                     "quality": "Good",
                     "timestamp": sample_timestamps[i]}
                    for i in range(5)
                ],
                "value": round(base_temp, 2),
                "quality": "Good",
                "timestamp": timestamp
            },
            # Tag 4: Cooling Fan Speed (with samples)
            {
                "plcId": plc_id,
                "tag": "Cooling_FAN_SPEED",
                "address": "Cooling_FAN_SPEED",
                "dataType": "float",
                "scanRateMs": 200,
                "sampleCount": 5,
                "samples": [
                    {"value": round(base_fan_speed + random.uniform(-0.01, 0.01), 2),
                     "quality": "Good",
                     "timestamp": sample_timestamps[i]}
                    for i in range(5)
                ],
                "value": round(base_fan_speed, 2),
                "quality": "Good",
                "timestamp": timestamp
            },
            # Tag 5: Production Rate
            {
                "plcId": plc_id,
                "tag": "Production_Rate",
                "address": "Production_Rate",
                "dataType": "float",
                "scanRateMs": 1000,
                "sampleCount": 1,
                "value": round(base_production, 2),
                "quality": "Good",
                "timestamp": timestamp
            },
            # Tag 6: Tank Level
            {
                "plcId": plc_id,
                "tag": "Tank_Level",
                "address": "Tank_Level",
                "dataType": "float",
                "scanRateMs": 500,
                "sampleCount": 2,
                "samples": [
                    {"value": round(base_tank_level + random.uniform(-0.5, 0.5), 2),
                     "quality": "Good",
                     "timestamp": sample_timestamps[i]}
                    for i in range(2)
                ],
                "value": round(base_tank_level, 2),
                "quality": "Good",
                "timestamp": timestamp
            },
            # Tag 7: Valve Position
            {
                "plcId": plc_id,
                "tag": "Valve_Position",
                "address": "Valve_Position",
                "dataType": "float",
                "scanRateMs": 500,
                "value": round(45.0 + random.uniform(-3.0, 3.0), 1),
                "quality": "Good",
                "timestamp": timestamp
            },
            # Tag 8: Motor Running Status
            {
                "plcId": plc_id,
                "tag": "Motor_Running_Status",
                "address": "Motor_Running_Status",
                "dataType": "boolean",
                "scanRateMs": 1000,
                "value": random.random() > 0.05,  # 95% uptime
                "quality": "Good",
                "timestamp": timestamp
            },
            # Tag 9: Pump Speed
            {
                "plcId": plc_id,
                "tag": "Pump_Speed_RPM",
                "address": "Pump_Speed_RPM",
                "dataType": "int",
                "scanRateMs": 500,
                "value": int(base_pump_speed),
                "quality": "Good",
                "timestamp": timestamp
            },
            # Tag 10: Flow Rate
            {
                "plcId": "Siemens_PLC_002",
                "tag": "Flow_Rate_Main",
                "address": "Flow_Rate_Main",
                "dataType": "float",
                "scanRateMs": 200,
                "sampleCount": 5,
                "samples": [
                    {"value": round(base_flow_rate + random.uniform(-1.0, 1.0), 2),
                     "quality": "Good",
                     "timestamp": sample_timestamps[i]}
                    for i in range(5)
                ],
                "value": round(base_flow_rate, 2),
                "quality": "Good",
                "timestamp": timestamp
            },
            # Tag 11: Reactor Temperature
            {
                "plcId": "Siemens_PLC_002",
                "tag": "Reactor_Core_Temp",
                "address": "Reactor_Core_Temp",
                "dataType": "float",
                "scanRateMs": 200,
                "sampleCount": 5,
                "samples": [
                    {"value": round(base_reactor_temp + random.uniform(-0.5, 0.5), 2),
                     "quality": "Good",
                     "timestamp": sample_timestamps[i]}
                    for i in range(5)
                ],
                "value": round(base_reactor_temp, 2),
                "quality": "Good",
                "timestamp": timestamp
            },
            # Tag 12: Conveyor Speed
            {
                "plcId": "Allen_Bradley_PLC_003",
                "tag": "Conveyor_Belt_Speed",
                "address": "Conveyor_Belt_Speed",
                "dataType": "float",
                "scanRateMs": 1000,
                "value": round(2.5 + random.uniform(-0.1, 0.1), 2),
                "quality": "Good",
                "timestamp": timestamp
            },
            # Tag 13: Emergency Stop Status
            {
                "plcId": "Allen_Bradley_PLC_003",
                "tag": "Emergency_Stop_Active",
                "address": "Emergency_Stop_Active",
                "dataType": "boolean",
                "scanRateMs": 100,
                "value": False,
                "quality": "Good",
                "timestamp": timestamp
            },
            # Tag 14: Alarm Status String
            {
                "plcId": plc_id,
                "tag": "System_Alarm_Status",
                "address": "System_Alarm_Status",
                "dataType": "string",
                "scanRateMs": 1000,
                "value": random.choice(["NORMAL", "NORMAL", "NORMAL", "WARNING", "ALERT"]),  # 60% normal
                "quality": "Good",
                "timestamp": timestamp
            },
            # Tag 15: Power Consumption
            {
                "plcId": "Siemens_PLC_002",
                "tag": "Total_Power_Consumption_KW",
                "address": "Total_Power_Consumption_KW",
                "dataType": "float",
                "scanRateMs": 500,
                "sampleCount": 2,
                "samples": [
                    {"value": round(base_power + random.uniform(-20.0, 20.0), 2),
                     "quality": "Good",
                     "timestamp": sample_timestamps[i]}
                    for i in range(2)
                ],
                "value": round(base_power, 2),
                "quality": "Good",
                "timestamp": timestamp
            }
        ]
    }
    
    # Add alarms RANDOMLY if temperature or pressure is high
    alarms = []
    has_threshold_violation = False
    
    if base_pressure > 22.0:
        has_threshold_violation = True
        alarms.append({
            "tag_id": "Blastfurnace_Tuyer1_Pressure",
            "event_type": "ALARM_HIGH_CRITICAL",
            "severity": 1,
            "message": f"Blast furnace pressure exceeded critical threshold ({base_pressure:.2f} Bar > 22.0 Bar)",
            "time": timestamp,
            "metadata": {
                "alarm_value": round(base_pressure, 2),
                "setpoint": 22.0,
                "unit": "Bar",
                "plant": plant,
                "area": area,
                "equipment": "Tuyer_1",
                "acknowledged": False,
                "state": "ACTIVE"
            }
        })
    
    if base_temp > 73.0:
        has_threshold_violation = True
        alarms.append({
            "tag_id": "Boiler_Inlet_Temp",
            "event_type": "ALARM_HIGH_WARNING",
            "severity": 2,
            "message": f"Boiler inlet temperature above normal operating range ({base_temp:.2f}°C > 73.0°C)",
            "time": timestamp,
            "metadata": {
                "alarm_value": round(base_temp, 2),
                "setpoint": 73.0,
                "unit": "Celsius",
                "plant": plant,
                "area": area,
                "equipment": "Boiler_01",
                "acknowledged": False,
                "state": "ACTIVE"
            }
        })
    
    if base_fan_speed > 66.0:
        has_threshold_violation = True
        alarms.append({
            "tag_id": "Cooling_FAN_SPEED",
            "event_type": "ALARM_HIGH_WARNING",
            "severity": 2,
            "message": f"Cooling fan speed above warning threshold ({base_fan_speed:.2f}% > 66.0%)",
            "time": timestamp,
            "metadata": {
                "alarm_value": round(base_fan_speed, 2),
                "setpoint": 66.0,
                "unit": "Percent",
                "plant": plant,
                "area": area,
                "equipment": "Fan_01",
                "acknowledged": False,
                "state": "ACTIVE"
            }
        })
    
    # Only include alarm_summary RANDOMLY when thresholds are exceeded
    has_alarm_summary = False
    if alarms and has_threshold_violation and should_include_alarm():
        message["alarm_summary"] = {
            "total_alarms": len(alarms),
            "critical_count": sum(1 for a in alarms if a["severity"] == 1),
            "warning_count": sum(1 for a in alarms if a["severity"] == 2),
            "info_count": 0,
            "alarms": alarms
        }
        has_alarm_summary = True
    
    return message, base_pressure, base_temp, base_fan_speed, has_alarm_summary

def save_to_file(data, filename, spool_dir):
    """Save data to JSON file"""
    spool_dir.mkdir(parents=True, exist_ok=True)
    filepath = spool_dir / filename
    
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    
    return filepath

def publish_to_mqtt_continuous(client, plc_config):
    """
    Publish data to MQTT broker using persistent connection
    Note: JSON file saving to spool/pending directory is disabled
    
    Args:
        client: Connected MQTT client
        plc_config: PLC configuration dictionary
    
    Returns:
        tuple: (success, payload_size, alarm_count, pressure, temp, fan_speed, filename, has_alarm_summary)
    """
    try:
        test_data, pressure, temp, fan_speed, has_alarm_summary = generate_test_data(plc_config)
        payload = json.dumps(test_data)
        
        # Save to JSON file in PLC-specific spool directory (DISABLED - not creating JSON files)
        now = datetime.utcnow()
        filename = now.strftime("%Y%m%d%H%M%S%f")[:-3] + ".json"  # yyyymmddHHMMSSfff.json
        filepath = save_to_file(test_data, filename, plc_config['spool_dir'])
        filename = "N/A"
        
        # Publish to PLC-specific MQTT topic
        result = client.publish(plc_config['topic'], payload, qos=QOS)
        result.wait_for_publish()
        
        alarm_count = test_data.get('alarm_summary', {}).get('total_alarms', 0) if has_alarm_summary else 0
        
        return True, len(payload), alarm_count, pressure, temp, fan_speed, filename, has_alarm_summary
        
    except Exception as e:
        print(f"❌ Publish failed for {plc_config['plc_id']}: {e}")
        return False, 0, 0, 0, 0, 0, None, False

def print_statistics():
    """Print current statistics for all PLCs"""
    if stats['start_time']:
        elapsed = (datetime.utcnow() - stats['start_time']).total_seconds()
        total_sent = sum(s['messages_sent'] for s in stats['plc_stats'].values())
        total_failed = sum(s['messages_failed'] for s in stats['plc_stats'].values())
        rate = total_sent / elapsed if elapsed > 0 else 0
        
        print(f"\n{'='*80}")
        print(f"📊 STATISTICS")
        print(f"{'='*80}")
        print(f"Runtime: {int(elapsed)} seconds | Total Messages: {total_sent} | Rate: {rate:.2f} msg/sec\n")
        
        for plc_config in PLC_CONFIGS:
            plc_id = plc_config['plc_id']
            plc_stats = stats['plc_stats'][plc_id]
            topic = plc_config['topic']
            success_rate = (plc_stats['messages_sent']/(plc_stats['messages_sent']+plc_stats['messages_failed'])*100 
                           if (plc_stats['messages_sent']+plc_stats['messages_failed']) > 0 else 0)
            
            print(f"{plc_id} ({topic}):")
            print(f"  Messages: {plc_stats['messages_sent']} | Failed: {plc_stats['messages_failed']} | "
                  f"Success: {success_rate:.1f}% | Alarms: {plc_stats['alarms_sent']}")
        
        print(f"{'='*80}\n")

def continuous_publisher():
    """Main continuous publishing loop for all PLCs"""
    global running
    
    print("=" * 80)
    print("🔄 CONTINUOUS MULTI-PLC MQTT TEST DATA GENERATOR")
    print("=" * 80)
    print(f"MQTT Broker:     {MQTT_BROKER}:{MQTT_PORT}")
    print(f"QoS:             {QOS}")
    print(f"Interval:        {PUBLISH_INTERVAL} seconds")
    print(f"Alarm Probability: {ALARM_PROBABILITY*100:.0f}%")
    print(f"{'='*80}")
    print(f"\nPLC Configurations:")
    for idx, plc_config in enumerate(PLC_CONFIGS, 1):
        print(f"  {idx}. {plc_config['plc_id']}")
        print(f"     Topic: {plc_config['topic']}")
        print(f"     Spool: {plc_config['spool_dir']}")
        print(f"     Plant: {plc_config['plant']} / {plc_config['area']}")
    print(f"{'='*80}")
    print(f"\n⌨️  Press Ctrl+C to stop...\n")
    
    # Setup signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    # Create all spool directories
    for plc_config in PLC_CONFIGS:
        plc_config['spool_dir'].mkdir(parents=True, exist_ok=True)
    print(f"✅ All spool directories ready\n")
    
    # Connect to MQTT broker
    try:
        client = mqtt.Client(f"multi_plc_publisher_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}")
        print("📡 Connecting to MQTT broker...")
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        print("✅ Connected to MQTT broker\n")
        time.sleep(1)  # Allow connection to stabilize
    except Exception as e:
        print(f"❌ Failed to connect to MQTT broker: {e}")
        return
    
    stats['start_time'] = datetime.utcnow()
    message_counter = {plc['plc_id']: 0 for plc in PLC_CONFIGS}
    last_stats_print = time.time()
    
    try:
        while running:
            loop_start = time.time()
            
            # Publish message for each PLC
            for plc_config in PLC_CONFIGS:
                plc_id = plc_config['plc_id']
                success, payload_size, alarm_count, pressure, temp, fan_speed, filename, has_alarm_summary = \
                    publish_to_mqtt_continuous(client, plc_config)
                
                if success:
                    stats['plc_stats'][plc_id]['messages_sent'] += 1
                    if has_alarm_summary:
                        stats['plc_stats'][plc_id]['alarms_sent'] += 1
                    message_counter[plc_id] += 1
                    
                    # Print inline status
                    timestamp = datetime.utcnow().strftime('%H:%M:%S.%f')[:-3]
                    alarm_indicator = f" 🚨 {alarm_count}" if has_alarm_summary else ""
                    short_topic = plc_config['topic'].split('/')[-1]
                    
                    print(f"[{timestamp}] 📤 {plc_id[-4:]} #{message_counter[plc_id]:3d} | {payload_size:5d}b | "
                          f"P:{pressure:.2f} T:{temp:.1f} F:{fan_speed:.1f}{alarm_indicator:8s} | {short_topic:15s} | 📁 {filename}")
                else:
                    stats['plc_stats'][plc_id]['messages_failed'] += 1
                    print(f"❌ {plc_id} message failed")
                
                time.sleep(0.01)  # Small delay between PLC publishes
            
            # Print statistics every 30 seconds
            if time.time() - last_stats_print >= 30:
                print_statistics()
                last_stats_print = time.time()
            
            # Calculate sleep time to maintain interval
            elapsed = time.time() - loop_start
            sleep_time = max(0, PUBLISH_INTERVAL - elapsed)
            
            if sleep_time > 0:
                time.sleep(sleep_time)
                
    except KeyboardInterrupt:
        print("\n\n⚠️  Keyboard interrupt received...")
    finally:
        # Cleanup
        print("\n🔌 Disconnecting from MQTT broker...")
        client.loop_stop()
        client.disconnect()
        
        # Print final statistics
        print_statistics()
        
        print("✅ Data generation stopped cleanly")
        print("\n📁 JSON files saved to:")
        for plc_config in PLC_CONFIGS:
            print(f"   {plc_config['plc_id']}: {plc_config['spool_dir']}")
        print("\n📝 Next Steps:")
        print("   1. Check MQTT Subscriber Service logs")
        print("   2. Query database:")
        print("      SELECT COUNT(*) FROM historian_raw.mqtt_audit_main;")
        print("      SELECT tag_id, time, value_num, quality")
        print("      FROM historian_raw.timeseries_data")
        print("      ORDER BY time DESC LIMIT 20;")
        print("")

def main():
    """Main execution"""
    continuous_publisher()

if __name__ == "__main__":
    main()
