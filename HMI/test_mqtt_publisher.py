"""
MQTT Test Publisher - Reads tags from database and publishes realistic turbine data with alarms
Publishes to topics configured in mqtt_topic_config table
Features:
- Realistic turbine operational patterns
- Critical and Warning alarm generation
- Trend-based value changes (smooth transitions)
- Alarm state persistence and recovery
"""
import psycopg2
import paho.mqtt.client as mqtt
import json
import os
import time
import random
import math
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from enum import Enum
from zoneinfo import ZoneInfo

# Database Configuration (prefer project config.json to keep values in sync with app)
def load_db_config():
    default_config = {
        'host': 'localhost',
        'port': 5432,
        'database': 'Cereveate',
        'user': 'postgres',
        'password': 'cereveate@222'
    }

    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        db = cfg.get('database', {})
        if db:
            return {
                'host': db.get('host', default_config['host']),
                'port': db.get('port', default_config['port']),
                'database': db.get('database', default_config['database']),
                'user': db.get('user', default_config['user']),
                'password': db.get('password', default_config['password']),
            }
    except Exception as e:
        print(f"⚠️  Could not read config.json database settings: {e}")

    return default_config


DB_CONFIG = load_db_config()

try:
    IST_TZ = ZoneInfo('Asia/Kolkata')
except Exception:
    IST_TZ = timezone(timedelta(hours=5, minutes=30))


def now_ist():
    return datetime.now(IST_TZ)


def get_db_connection():
    conn = psycopg2.connect(**DB_CONFIG)
    with conn.cursor() as cursor:
        cursor.execute("SET TIME ZONE 'Asia/Kolkata'")
    return conn

# Helper function to format datetime with milliseconds (3 decimal places)
def format_timestamp_with_ms():
    """Generate ISO 8601 IST timestamp with milliseconds (e.g., 2026-01-26T10:23:58.200+05:30)."""
    return now_ist().isoformat(timespec='milliseconds')

# MQTT Configuration
MQTT_BROKER = "127.0.0.1"
MQTT_PORT = 1883
PUBLISH_INTERVAL = 0.5  # seconds (500 ms)
ALARM_GENERATION_INTERVAL_SECONDS = 60  # Generate alarm conditions every 1 minute
FORCE_TRIP_EVERY_CYCLES = 20  # Keep forced trip cadence independent from alarm interval
FORCE_TRIP_DURATION_CYCLES = 8  # Trip duration in cycles before auto-restart

class AlarmLevel(Enum):
    """Alarm severity levels"""
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"

class TurbineProfile:
    """Realistic turbine parameter profiles with alarm thresholds"""
    
    PROFILES = {
        # Speed parameters (rpm)
        'speed': {
            'normal_range': (1450, 1550),
            'warning_low': 1400, 'warning_high': 1600,
            'critical_low': 1350, 'critical_high': 1650,
            'trend_rate': 5.0,  # max change per second
            'noise': 2.0
        },
        # Temperature parameters (°C)
        'temperature': {
            'normal_range': (60, 85),
            'warning_low': 50, 'warning_high': 90,
            'critical_low': 40, 'critical_high': 100,
            'trend_rate': 1.5,
            'noise': 0.8
        },
        # Pressure parameters (bar)
        'pressure': {
            'normal_range': (8.0, 12.0),
            'warning_low': 7.0, 'warning_high': 13.0,
            'critical_low': 6.0, 'critical_high': 14.5,
            'trend_rate': 0.5,
            'noise': 0.2
        },
        # Vibration parameters (mm/s)
        'vibration': {
            'normal_range': (0.5, 2.5),
            'warning_low': 0.0, 'warning_high': 4.5,
            'critical_low': 0.0, 'critical_high': 7.0,
            'trend_rate': 0.3,
            'noise': 0.15
        },
        # Flow parameters (m³/h)
        'flow': {
            'normal_range': (100, 200),
            'warning_low': 80, 'warning_high': 220,
            'critical_low': 60, 'critical_high': 250,
            'trend_rate': 10.0,
            'noise': 5.0
        },
        # Power parameters (kW)
        'power': {
            'normal_range': (800, 1200),
            'warning_low': 700, 'warning_high': 1300,
            'critical_low': 600, 'critical_high': 1400,
            'trend_rate': 20.0,
            'noise': 10.0
        }
    }
    
    @staticmethod
    def get_profile_for_tag(tag_name: str) -> Optional[Dict]:
        """Determine profile type based on tag name"""
        tag_lower = tag_name.lower()
        
        if any(kw in tag_lower for kw in ['speed', 'rpm', 'fan']):
            return TurbineProfile.PROFILES['speed']
        elif any(kw in tag_lower for kw in ['temp', 'temperature']):
            return TurbineProfile.PROFILES['temperature']
        elif any(kw in tag_lower for kw in ['pressure', 'press']):
            return TurbineProfile.PROFILES['pressure']
        elif any(kw in tag_lower for kw in ['vibration', 'vib']):
            return TurbineProfile.PROFILES['vibration']
        elif any(kw in tag_lower for kw in ['flow', 'rate']):
            return TurbineProfile.PROFILES['flow']
        elif any(kw in tag_lower for kw in ['power', 'kw', 'mw']):
            return TurbineProfile.PROFILES['power']
        
        return None

class DBBasedMQTTPublisher:
    def __init__(self):
        self.mqtt_client = None
        self.topics_and_tags = {}  # topic_name -> {plc_name, tags[]}
        self.tag_states = {}  # tag_name -> {current_value, alarm_level, trend_direction}
        self.cycle_count = 0
        self.alarm_simulation_mode = True  # Enable periodic alarm simulation
        self.force_trip_every_cycles = FORCE_TRIP_EVERY_CYCLES
        self.force_trip_remaining = 0
        self.force_trip_active = False
        self.last_alarm_generation_time = time.time() - ALARM_GENERATION_INTERVAL_SECONDS
        
        # Equipment state tracking for trip simulation - LOADED FROM TAG_MASTER
        self.equipment_states = {}  # Will be populated from database
        self.equipment_metadata = {}  # Store equipment details from tag_master
        
        # Track critical alarms that may cause trips
        self.critical_alarm_buffer = []  # Store recent critical alarms
        self.trip_simulation_probability = 0.85  # 85% chance per critical alarm (ENHANCED FOR TESTING)
        self.trip_generation_mode = 'frequent'  # 'frequent' or 'normal'
        
        # Interlock state tracking for automated interlock management
        self.interlock_states = {
            'TURBINE_START_PERMISSIVE': {
                'tag_id': 'TURBINE_START_PERMISSIVE',
                'equipment': 'TURBINE',
                'type': 'PERMISSIVE',
                'state': 'SATISFIED',
                'change_probability': 0.05  # 5% chance to change state per cycle
            },
            'BOILER_IGNITION_PERMISSIVE': {
                'tag_id': 'BOILER_IGNITION_PERMISSIVE',
                'equipment': 'Boiler_01',
                'type': 'PERMISSIVE',
                'state': 'SATISFIED',
                'change_probability': 0.08
            },
            'PUMP_SEQUENTIAL_START': {
                'tag_id': 'PUMP_SEQUENTIAL_START',
                'equipment': 'PUMP',
                'type': 'SEQUENTIAL',
                'state': 'SATISFIED',
                'change_probability': 0.03
            },
            'EMERGENCY_SHUTDOWN_PROTECTIVE': {
                'tag_id': 'EMERGENCY_SHUTDOWN_PROTECTIVE',
                'equipment': 'TURBINE',
                'type': 'PROTECTIVE',
                'state': 'SATISFIED',
                'change_probability': 0.02,  # Less likely to bypass
                'bypass_duration_minutes': 120  # 2 hours
            },
            'COMPRESSOR_CONDITIONAL': {
                'tag_id': 'COMPRESSOR_CONDITIONAL',
                'equipment': 'COMPRESSOR',
                'type': 'CONDITIONAL',
                'state': 'SATISFIED',
                'change_probability': 0.06
            }
        }
        self.last_interlock_update = 0
        
    def connect_mqtt(self):
        """Connect to MQTT broker"""
        try:
            self.mqtt_client = mqtt.Client(client_id="db_test_publisher")
            self.mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            self.mqtt_client.loop_start()
            print(f"✅ Connected to MQTT broker: {MQTT_BROKER}:{MQTT_PORT}")
            return True
        except Exception as e:
            print(f"❌ Failed to connect to MQTT broker: {e}")
            return False
    
    def load_equipment_from_tag_master(self):
        """Load unique equipment from tag_master with their metadata"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get unique equipment with their properties
            cursor.execute("""
                SELECT 
                    equipment,
                    MAX(equipment_criticality) as criticality,
                    STRING_AGG(DISTINCT trip_category, ', ') as trip_categories,
                    STRING_AGG(DISTINCT interlock_type, ', ') as interlock_types,
                    COUNT(*) as tag_count,
                    MAX(plant) as plant,
                    MAX(area) as area,
                    MAX(is_trip_initiator::int) as has_trip_initiator
                FROM historian_meta.tag_master
                WHERE equipment IS NOT NULL 
                  AND equipment != ''
                  AND enabled = true
                GROUP BY equipment
                ORDER BY MAX(equipment_criticality) DESC, equipment
            """)
            
            equipment_rows = cursor.fetchall()
            
            print(f"\n✅ Found {len(equipment_rows)} unique equipment in tag_master:")
            print(f"  {'Equipment':<25} {'Criticality':<12} {'Trip Categories':<25} {'Tags':<6}")
            print(f"  {'-'*25} {'-'*12} {'-'*25} {'-'*6}")
            
            for row in equipment_rows:
                equipment, criticality, trip_cats, interlock_types, tag_count, plant, area, has_trip_init = row
                
                # Initialize equipment state
                self.equipment_states[equipment] = {
                    'running': True,
                    'trip_cooldown': 0
                }
                
                # Store equipment metadata for trip generation
                self.equipment_metadata[equipment] = {
                    'criticality': criticality or 3,
                    'trip_categories': trip_cats or 'PROCESS_TRIP',
                    'interlock_types': interlock_types or 'CONDITIONAL',
                    'tag_count': tag_count,
                    'plant': plant or 'Plant1',
                    'area': area or 'Area1',
                    'is_trip_initiator': bool(has_trip_init)
                }
                
                print(f"  {equipment:<25} {str(criticality or 'N/A'):<12} {str(trip_cats or 'N/A'):<25} {tag_count:<6}")
            
            cursor.close()
            conn.close()
            
            return len(self.equipment_states) > 0
            
        except Exception as e:
            print(f"❌ Failed to load equipment from tag_master: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def load_topics_and_tags_from_db(self):
        """Load MQTT topics and their associated tags from database"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get active MQTT topics
            cursor.execute("""
                SELECT topic_name, plc_name 
                FROM historian_raw.mqtt_topic_config 
                WHERE is_active = true
                ORDER BY topic_name
            """)
            topics = cursor.fetchall()
            
            print(f"\n✅ Found {len(topics)} active MQTT topics:")
            
            # For each topic, get tags associated with its PLC
            for topic_name, plc_name in topics:
                # Get ALL tags with matching server_progid (includes both regular and turbine tags)
                # IMPORTANT: Use tag_id as the primary identifier for MQTT messages
                cursor.execute("""
                    SELECT tag_id, tag_name, data_type, eng_unit, description, equipment
                    FROM historian_meta.tag_master 
                    WHERE server_progid = %s 
                        AND enabled = true
                    ORDER BY tag_id
                """, (plc_name,))
                
                tags = cursor.fetchall()
                
                if tags:
                    self.topics_and_tags[topic_name] = {
                        'plc_name': plc_name,
                        'tags': [
                            {
                                'tag_id': tag[0],     # Primary identifier (e.g., "TURBINE_SPEED")
                                'tag_name': tag[1],   # Display name (e.g., "Turbine Speed")
                                'data_type': tag[2] or 'Double',
                                'eng_unit': tag[3] or '',
                                'description': tag[4] or '',
                                'equipment': tag[5] or 'Equipment'
                            }
                            for tag in tags
                        ]
                    }
                    print(f"  📍 {topic_name} -> PLC: {plc_name} ({len(tags)} tags)")
            
            cursor.close()
            conn.close()
            
            return len(self.topics_and_tags) > 0
            
        except Exception as e:
            print(f"❌ Failed to load topics/tags from database: {e}")
            return False
    
    def generate_realistic_value(self, tag_info: Dict, tag_name: str) -> tuple:
        """
        Generate realistic turbine value with trending and alarm detection
        Returns: (value, alarm_level, alarm_message)
        """
        profile = TurbineProfile.get_profile_for_tag(tag_name)
        
        # Initialize tag state if not exists
        if tag_name not in self.tag_states:
            if profile:
                # Start in normal range
                min_val, max_val = profile['normal_range']
                initial_value = random.uniform(min_val, max_val)
            else:
                initial_value = random.uniform(20.0, 100.0)
            
            self.tag_states[tag_name] = {
                'current_value': initial_value,
                'alarm_level': AlarmLevel.NORMAL,
                'trend_direction': random.choice([-1, 1]),
                'cycles_in_alarm': 0,
                'alarm_threshold': None  # Store current threshold for metadata
            }
        
        state = self.tag_states[tag_name]
        current_value = state['current_value']
        
        # Handle different data types
        data_type = tag_info.get('data_type', 'float').lower()
        
        if 'bool' in data_type or 'bit' in data_type:
            # For boolean, occasionally flip
            if random.random() < 0.1:
                current_value = not current_value
            return (current_value, AlarmLevel.NORMAL, None)
        
        elif 'string' in data_type or 'text' in data_type:
            # String values based on alarm state
            if state['alarm_level'] == AlarmLevel.CRITICAL:
                value = random.choice(['CRITICAL', 'FAULT', 'ALARM'])
            elif state['alarm_level'] == AlarmLevel.WARNING:
                value = random.choice(['WARNING', 'CAUTION', 'CHECK'])
            else:
                value = random.choice(['NORMAL', 'OK', 'RUNNING'])
            return (value, state['alarm_level'], None)
        
        # Simulate alarm conditions periodically
        if profile:
            # Generate simulated alarm conditions on a fixed schedule (every 5 minutes)
            if self.alarm_simulation_mode:
                current_time = time.time()
                if current_time - self.last_alarm_generation_time >= ALARM_GENERATION_INTERVAL_SECONDS:
                    self.last_alarm_generation_time = current_time
                    if random.random() < 0.4:  # 40% chance of warning (reduced from 70%)
                        # Force value toward warning threshold
                        if random.random() < 0.5:
                            state['target_value'] = profile['warning_high'] + random.uniform(0, 5)
                        else:
                            state['target_value'] = profile['warning_low'] - random.uniform(0, 5)
                    else:  # 60% chance of critical (increased from 30%)
                        # Force value toward critical threshold
                        if random.random() < 0.5:
                            state['target_value'] = profile['critical_high'] + random.uniform(0, 3)
                        else:
                            state['target_value'] = profile['critical_low'] - random.uniform(0, 3)
            
            # Trend toward target or recover to normal
            if 'target_value' in state:
                # Move toward target
                if abs(current_value - state['target_value']) < profile['trend_rate']:
                    current_value = state['target_value']
                    del state['target_value']
                else:
                    direction = 1 if state['target_value'] > current_value else -1
                    current_value += direction * profile['trend_rate'] * random.uniform(0.5, 1.0)
            else:
                # Normal trending within range
                trend_change = state['trend_direction'] * profile['trend_rate'] * random.uniform(0.3, 0.8)
                current_value += trend_change
                
                # Add noise
                current_value += random.uniform(-profile['noise'], profile['noise'])
                
                # Reverse trend at boundaries or randomly
                min_val, max_val = profile['normal_range']
                if current_value >= max_val or random.random() < 0.05:
                    state['trend_direction'] = -1
                elif current_value <= min_val or random.random() < 0.05:
                    state['trend_direction'] = 1
            
            # Determine alarm level
            alarm_level = AlarmLevel.NORMAL
            alarm_message = None
            alarm_threshold = None
            
            if current_value >= profile['critical_high']:
                alarm_level = AlarmLevel.CRITICAL
                alarm_message = f"{tag_name}: Value {current_value:.2f} exceeds CRITICAL HIGH limit {profile['critical_high']}"
                alarm_threshold = profile['critical_high']
            elif current_value <= profile['critical_low']:
                alarm_level = AlarmLevel.CRITICAL
                alarm_message = f"{tag_name}: Value {current_value:.2f} below CRITICAL LOW limit {profile['critical_low']}"
                alarm_threshold = profile['critical_low']
            elif current_value >= profile['warning_high']:
                alarm_level = AlarmLevel.WARNING
                alarm_message = f"{tag_name}: Value {current_value:.2f} exceeds WARNING HIGH limit {profile['warning_high']}"
                alarm_threshold = profile['warning_high']
            elif current_value <= profile['warning_low']:
                alarm_level = AlarmLevel.WARNING
                alarm_message = f"{tag_name}: Value {current_value:.2f} below WARNING LOW limit {profile['warning_low']}"
                alarm_threshold = profile['warning_low']
            
            # Track alarm persistence
            if alarm_level != AlarmLevel.NORMAL:
                state['cycles_in_alarm'] += 1
                
                # Store critical alarms for trip simulation
                if alarm_level == AlarmLevel.CRITICAL:
                    equipment_id = tag_name.split('_')[0] if '_' in tag_name else 'UNKNOWN'
                    self.critical_alarm_buffer.append({
                        'equipment': equipment_id,
                        'tag_name': tag_name,
                        'alarm_message': alarm_message,
                        'timestamp': time.time(),
                        'priority': 5  # P5 = Critical priority for trip detection
                    })
                
                # ENHANCED: Faster auto-recovery (5-8 cycles instead of 10-20)
                if state['cycles_in_alarm'] > random.randint(5, 8):
                    min_val, max_val = profile['normal_range']
                    state['target_value'] = random.uniform(min_val, max_val)
                    state['cycles_in_alarm'] = 0
            else:
                state['cycles_in_alarm'] = 0
            
            state['current_value'] = current_value
            state['alarm_level'] = alarm_level
            state['alarm_threshold'] = alarm_threshold
            
            # Round based on profile magnitude
            if profile['normal_range'][1] > 100:
                current_value = round(current_value, 1)
            else:
                current_value = round(current_value, 2)
            
            return (current_value, alarm_level, alarm_message)
        
        else:
            # Generic numeric without profile - simple random
            trend_change = random.uniform(-5, 5)
            current_value = max(0, current_value + trend_change)
            state['current_value'] = current_value
            return (round(current_value, 2), AlarmLevel.NORMAL, None)
    
    def insert_trip_event_to_db(self, equipment_id: str, alarm_info: Dict) -> Optional[int]:
        """
        Insert trip event into database (historian_raw.trip_event_tracking)
        Returns trip_event_id or None
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get equipment metadata
            equipment_meta = self.equipment_metadata.get(equipment_id, {})
            
            # Determine trip category based on criticality
            criticality = equipment_meta.get('criticality', 3)
            if criticality >= 5:
                trip_category = 'SAFETY_TRIP'
            elif criticality >= 4:
                trip_category = 'EMERGENCY_TRIP'
            else:
                trip_category = 'PROCESS_TRIP'
            
            # Get trip categories from tag_master (may have multiple)
            trip_categories_str = equipment_meta.get('trip_categories', 'PROCESS_TRIP')
            if trip_categories_str and ',' in trip_categories_str:
                # Use the first one, prioritizing SAFETY > EMERGENCY > PROCESS
                if 'SAFETY' in trip_categories_str:
                    trip_category = 'SAFETY_TRIP'
                elif 'EMERGENCY' in trip_categories_str:
                    trip_category = 'EMERGENCY_TRIP'
            elif trip_categories_str and trip_categories_str.strip():
                trip_category = trip_categories_str.strip().split(',')[0].strip()
            
            # Find root cause tag from tag_master
            cursor.execute("""
                SELECT tag_id FROM historian_meta.tag_master
                WHERE equipment = %s AND enabled = true
                ORDER BY is_trip_initiator DESC, equipment_criticality DESC
                LIMIT 1
            """, (equipment_id,))
            root_cause_tag = cursor.fetchone()
            root_cause_tag_id = root_cause_tag[0] if root_cause_tag else alarm_info.get('tag_name')

            # Resolve a valid tag_id for FK fk_trip_tag (must exist in historian_meta.tag_master)
            candidate_tag_ids = [
                alarm_info.get('tag_id'),
                alarm_info.get('tag_name'),
                root_cause_tag_id
            ]
            candidate_tag_ids = [tag_id for tag_id in candidate_tag_ids if tag_id]

            trip_tag_id = None
            if candidate_tag_ids:
                cursor.execute("""
                    SELECT tag_id
                    FROM historian_meta.tag_master
                    WHERE enabled = true
                      AND tag_id = ANY(%s)
                    LIMIT 1
                """, (candidate_tag_ids,))
                valid_tag_row = cursor.fetchone()
                if valid_tag_row:
                    trip_tag_id = valid_tag_row[0]

            if not trip_tag_id:
                print(f"      ❌ Failed to insert trip event: no valid trip_tag_id found in tag_master for equipment={equipment_id}")
                cursor.close()
                conn.close()
                return None
            
            # Calculate production loss based on equipment criticality
            production_loss_mw = (criticality or 3) * random.uniform(35, 75)
            
            # Build structured diagnosis payload for JSON/JSONB column
            automated_diagnosis_payload = {
                'equipment': equipment_id,
                'trip_category': trip_category,
                'criticality': criticality,
                'root_cause_tag_id': root_cause_tag_id,
                'alarm_message': alarm_info.get('alarm_message', 'Critical alarm'),
                'alarm_priority': alarm_info.get('priority', 5),
                'generated_by': 'test_mqtt_publisher'
            }
            
            # Insert trip event
            cursor.execute("""
                INSERT INTO historian_raw.trip_event_tracking (
                    trip_time,
                    trip_tag_id,
                    trip_category,
                    equipment_affected,
                    trip_duration_seconds,
                    production_loss_mw,
                    root_cause_tag_id,
                    operator_notes,
                    automated_diagnosis
                ) VALUES (
                    NOW(), %s, %s, %s, NULL, %s, %s, %s, %s
                )
                RETURNING trip_event_id
            """, (
                trip_tag_id,
                trip_category,
                equipment_id,
                production_loss_mw,
                root_cause_tag_id,
                f"Automated trip event generated during test. Cause: {alarm_info.get('alarm_message', 'Critical alarm')[:100]}",
                json.dumps(automated_diagnosis_payload)
            ))
            
            result = cursor.fetchone()
            trip_event_id = result[0] if result else None
            
            conn.commit()
            cursor.close()
            conn.close()
            
            if trip_event_id:
                print(f"      ✓ Trip event saved to DB: trip_event_id={trip_event_id}, category={trip_category}")
            
            return trip_event_id
            
        except Exception as e:
            print(f"      ❌ Failed to insert trip event: {e}")
            return None
    
    def update_trip_event_cleared(self, equipment_id: str):
        """Update the most recent trip event for equipment when it restarts"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Update the most recent unclosed trip for this equipment
            cursor.execute("""
                UPDATE historian_raw.trip_event_tracking
                SET trip_cleared_at = NOW(),
                    trip_duration_seconds = EXTRACT(EPOCH FROM (NOW() - trip_time))::INTEGER
                WHERE equipment_affected = %s
                  AND trip_cleared_at IS NULL
                  AND trip_event_id = (
                      SELECT trip_event_id 
                      FROM historian_raw.trip_event_tracking
                      WHERE equipment_affected = %s AND trip_cleared_at IS NULL
                      ORDER BY trip_time DESC
                      LIMIT 1
                  )
            """, (equipment_id, equipment_id))
            
            if cursor.rowcount > 0:
                print(f"      ✓ Trip event marked as cleared in DB for {equipment_id}")
            
            conn.commit()
            cursor.close()
            conn.close()
            
        except Exception as e:
            print(f"      ❌ Failed to update trip cleared: {e}")
    
    def check_and_simulate_trips(self):
        """
        ENHANCED: Check for critical alarms and simulate equipment trips based on tag_master data
        Inserts trip events into database
        Returns dict of equipment_id -> trip_occurred (bool)
        """
        trips = {}
        
        # Clean up old alarms from buffer (older than 3 seconds - tighter window)
        current_time = time.time()
        self.critical_alarm_buffer = [
            alarm for alarm in self.critical_alarm_buffer 
            if current_time - alarm['timestamp'] < 3.0
        ]
        
        # Process each equipment from tag_master
        for equipment_id, state in self.equipment_states.items():
            # Decrease cooldown
            if state['trip_cooldown'] > 0:
                state['trip_cooldown'] -= 1
            
            # Check for critical alarms affecting this equipment
            equipment_alarms = [
                alarm for alarm in self.critical_alarm_buffer
                if equipment_id in alarm['equipment'] or alarm['equipment'] in equipment_id
            ]
            
            # ENHANCED: Accept ANY critical alarm as potential trip cause (system-wide)
            # This matches real industrial behavior where any critical condition can trip equipment
            if not equipment_alarms and self.critical_alarm_buffer:
                equipment_alarms = self.critical_alarm_buffer  # Use any critical alarm
            
            # Get equipment metadata
            equipment_meta = self.equipment_metadata.get(equipment_id, {})
            
            # Simulate trip if:
            # 1. Equipment is running
            # 2. Has critical alarms (equipment-specific OR system-wide)
            # 3. Not in cooldown
            # 4. Random probability met (85% chance - ENHANCED)
            if (state['running'] and 
                equipment_alarms and 
                state['trip_cooldown'] == 0 and
                random.random() < self.trip_simulation_probability):
                
                # TRIP OCCURRED
                state['running'] = False
                state['trip_cooldown'] = random.randint(15, 25)  # 15-25 cycles (reduced from 20-40)
                trips[equipment_id] = True
                
                print(f"\n🚨 TRIP SIMULATED: {equipment_id} stopped due to critical alarm!")
                print(f"   Equipment: {equipment_id} | Criticality: {equipment_meta.get('criticality', 'N/A')}")
                print(f"   Cause: {equipment_alarms[0]['alarm_message'][:80]}")
                print(f"   Priority: P{equipment_alarms[0].get('priority', 5)}")
                print(f"   Equipment will restart in {state['trip_cooldown']} seconds")
                
                # Insert trip event to database
                trip_event_id = self.insert_trip_event_to_db(equipment_id, equipment_alarms[0])
                if trip_event_id:
                    state['last_trip_event_id'] = trip_event_id
                
            # Auto-restart after cooldown
            elif not state['running'] and state['trip_cooldown'] == 0:
                state['running'] = True
                trips[equipment_id] = False
                print(f"\n✅ EQUIPMENT RESTARTED: {equipment_id} back online")
                
                # Update trip event in database as cleared
                self.update_trip_event_cleared(equipment_id)
        
        return trips
    
    def generate_equipment_status_tags(self) -> List[Dict]:
        """
        Generate RUN_STATUS and TRIP_STATUS tags for equipment from tag_master
        These tags are required for trip detection system
        
        ENHANCED: Handles all equipment types dynamically
        """
        status_tags = []
        timestamp = format_timestamp_with_ms()
        
        for equipment_id, state in self.equipment_states.items():
            # Normalize equipment name for tag creation
            equipment_tag_prefix = equipment_id.upper().replace(' ', '_').replace('-', '_')
            
            # Determine tag name based on equipment
            # Use boolean for specific equipment types (Turbine1, TURBINE, Turbine)
            if 'TURBINE' in equipment_tag_prefix or equipment_id in ['Turbine1']:
                # Turbine uses boolean STATUS tag
                run_status_tag = {
                    'plcId': 'Equipment_Monitor',
                    'tag': f'{equipment_tag_prefix}_STATUS',
                    'address': f'{equipment_tag_prefix}_STATUS',
                    'dataType': 'bool',  # Boolean type
                    'value': state['running'],  # true/false
                    'quality': 'Good',
                    'timestamp': timestamp
                }
            else:
                # Other equipment: Uses {EQUIPMENT}_RUN_STATUS (integer)
                run_status_tag = {
                    'plcId': 'Equipment_Monitor',
                    'tag': f'{equipment_tag_prefix}_RUN_STATUS',
                    'address': f'{equipment_tag_prefix}_RUN_STATUS',
                    'dataType': 'int',
                    'value': 1 if state['running'] else 0,
                    'quality': 'Good',
                    'timestamp': timestamp
                }
            status_tags.append(run_status_tag)
            
            # TRIP_STATUS tag (0=NORMAL, 1=TRIPPED) - always integer
            trip_status_tag = {
                'plcId': 'Equipment_Monitor',
                'tag': f'{equipment_tag_prefix}_TRIP_STATUS',
                'address': f'{equipment_tag_prefix}_TRIP_STATUS',
                'dataType': 'int',
                'value': 0 if state['running'] else 1,
                'quality': 'Good',
                'timestamp': timestamp
            }
            status_tags.append(trip_status_tag)
        
        return status_tags

    def maybe_force_trip(self) -> Optional[Dict]:
        """
        Force a TURBINE trip periodically to create trip events with revenue data.
        Returns a forced alarm dict to inject into alarm_summary when active.
        """
        if self.force_trip_remaining > 0:
            self.force_trip_remaining -= 1
            self.force_trip_active = True
        elif self.force_trip_every_cycles > 0 and self.cycle_count % self.force_trip_every_cycles == 0:
            self.force_trip_remaining = FORCE_TRIP_DURATION_CYCLES
            self.force_trip_active = True
            print("\n⚠️  FORCED TRIP: TURBINE (test mode)")
        else:
            self.force_trip_active = False

        if self.force_trip_active:
            # Ensure TURBINE is stopped during forced trip window
            if 'TURBINE' in self.equipment_states:
                self.equipment_states['TURBINE']['running'] = False
                self.equipment_states['TURBINE']['trip_cooldown'] = 0

            return {
                'tag_id': 'TURBINE_SPEED',
                'event_type': 'ALARM_HIGH_CRITICAL',
                'severity': 1,
                'message': 'TURBINE_SPEED exceeds CRITICAL HIGH limit (forced trip)',
                'time': format_timestamp_with_ms(),
                'metadata': {
                    'alarm_value': 1700,
                    'setpoint': 1650,
                    'unit': 'rpm',
                    'plant': 'Industrial_Plant_A',
                    'area': 'Production',
                    'equipment': 'TURBINE',
                    'acknowledged': False,
                    'state': 'ACTIVE',
                    'alarm_priority': 5
                }
            }

        # Auto-restart TURBINE when forced trip ends
        if 'TURBINE' in self.equipment_states:
            self.equipment_states['TURBINE']['running'] = True

        return None
    
    def publish_test_data(self):
        """Publish test data for all topics with embedded alarm summary and equipment status"""
        message_count = 0
        
        print(f"\n{'='*80}")
        print(f"📤 Starting MQTT test publisher with ENHANCED TRIP DETECTION")
        print(f"   Publishing every {PUBLISH_INTERVAL}s")
        print(f"   ⚡ Alarm schedule: every {ALARM_GENERATION_INTERVAL_SECONDS // 60} minutes")
        print(f"   Features:")
        print(f"     ✓ Alarm generation interval: {ALARM_GENERATION_INTERVAL_SECONDS}s")
        print(f"     ✓ More critical alarms (60% instead of 30%)")
        print(f"     ✓ High trip probability (85% instead of 15%)")
        print(f"     ✓ Fast alarm recovery (5-8 cycles instead of 10-20)")
        print(f"     ✓ Quick equipment restart (15-25 cycles instead of 20-40)")
        print(f"     ✓ TURBINE_STATUS uses boolean type (matches DB schema)")
        print(f"     ✓ Priority P5/P4 alarms for trip detection")
        print(f"{'='*80}\n")
        
        try:
            while True:
                message_count += 1
                self.cycle_count += 1
                
                # Check for trips based on critical alarms
                self.check_and_simulate_trips()
                forced_alarm = self.maybe_force_trip()
                
                forced_alarm_injected = False

                for topic_name, topic_info in self.topics_and_tags.items():
                    plc_name = topic_info['plc_name']
                    tags = topic_info['tags']
                    
                    # Generate values and collect alarms for all tags
                    values = []
                    alarms_in_topic = []
                    
                    for tag in tags:
                        # Use tag_id for value generation and as the key identifier
                        value, alarm_level, alarm_message = self.generate_realistic_value(tag, tag['tag_id'])
                        
                        values.append({
                            'plcId': plc_name,
                            'tag': tag['tag_id'],  # Use tag_id (e.g., "TURBINE_SPEED")
                            'value': value,
                            'quality': 'Good' if random.random() > 0.02 else 'Bad',
                            'timestamp': format_timestamp_with_ms(),
                            'dataType': tag['data_type'],
                            'unit': tag.get('eng_unit', '')
                        })
                        
                        # Collect alarm if present
                        if alarm_message and alarm_level != AlarmLevel.NORMAL:
                            # Map AlarmLevel to severity number (1=CRITICAL, 2=WARNING, 3=INFO)
                            severity = 1 if alarm_level == AlarmLevel.CRITICAL else 2
                            
                            # Determine event type based on alarm message
                            if 'above' in alarm_message.lower() or 'exceeds' in alarm_message.lower():
                                event_type = f"ALARM_HIGH_{alarm_level.value}"
                            elif 'below' in alarm_message.lower():
                                event_type = f"ALARM_LOW_{alarm_level.value}"
                            else:
                                event_type = f"ALARM_{alarm_level.value}"
                            
                            # ENHANCED: Map to ISA-18.2 priority levels for trip detection
                            # P5 (Critical) = severity 1, P4 (Urgent) = severity 2
                            alarm_priority = 5 if alarm_level == AlarmLevel.CRITICAL else 4
                            
                            alarms_in_topic.append({
                                'tag_id': tag['tag_id'],  # Use tag_id
                                'event_type': event_type,
                                'severity': severity,
                                'message': alarm_message,
                                'time': format_timestamp_with_ms(),
                                'metadata': {
                                    'alarm_value': value,
                                    'setpoint': self.tag_states[tag['tag_id']].get('alarm_threshold'),
                                    'unit': tag.get('eng_unit', ''),
                                    'plant': self.equipment_metadata.get(tag.get('equipment', 'Equipment'), {}).get('plant', 'Industrial_Plant_A'),
                                    'area': self.equipment_metadata.get(tag.get('equipment', 'Equipment'), {}).get('area', 'Production'),
                                    'equipment': tag.get('equipment') or (tag['tag_id'].split('_')[0] if '_' in tag['tag_id'] else 'Equipment'),
                                    'acknowledged': False,
                                    'state': 'ACTIVE',
                                    'alarm_priority': alarm_priority  # P5 or P4
                                }
                            })
                    
                    # Add equipment status tags (RUN_STATUS and TRIP_STATUS)
                    equipment_status_tags = self.generate_equipment_status_tags()
                    values.extend(equipment_status_tags)
                    
                    # Log equipment status for debugging
                    if self.cycle_count % 10 == 0:  # Every 10 cycles
                        for eq_id, state in self.equipment_states.items():
                            print(f"      🔧 {eq_id}: {'RUNNING' if state['running'] else 'STOPPED'} (cooldown={state['trip_cooldown']})")
                    
                    # Update interlock states periodically
                    self.update_interlock_states()
                    
                    # Create MQTT message with embedded alarm_summary
                    message = {
                        'timestamp': format_timestamp_with_ms(),
                        'publishIntervalMs': PUBLISH_INTERVAL * 1000,
                        'tagCount': len(values),
                        'totalSamples': len(values),
                        'values': values
                    }
                    
                    # Inject forced trip alarm once per cycle (if active)
                    if forced_alarm and not forced_alarm_injected:
                        alarms_in_topic.append(forced_alarm)
                        forced_alarm_injected = True

                    # Add alarm_summary if there are alarms
                    if alarms_in_topic:
                        critical_count = sum(1 for a in alarms_in_topic if a['severity'] == 1)
                        warning_count = sum(1 for a in alarms_in_topic if a['severity'] == 2)
                        
                        message['alarm_summary'] = {
                            'total_alarms': len(alarms_in_topic),
                            'critical_count': critical_count,
                            'warning_count': warning_count,
                            'info_count': 0,
                            'alarms': alarms_in_topic
                        }
                    
                    # Publish to MQTT
                    payload = json.dumps(message)
                    result = self.mqtt_client.publish(topic_name, payload, qos=1)
                    
                    if result.rc == mqtt.MQTT_ERR_SUCCESS:
                        timestamp = now_ist().strftime('[%H:%M:%S.%f')[:-3] + ']'
                        
                        # Build alarm status string
                        alarm_str = ""
                        if alarms_in_topic:
                            critical_count = sum(1 for a in alarms_in_topic if a['severity'] == 1)
                            warning_count = sum(1 for a in alarms_in_topic if a['severity'] == 2)
                            if critical_count > 0:
                                alarm_str = f" | 🔴 CRITICAL:{critical_count}"
                            if warning_count > 0:
                                alarm_str += f" | ⚠️  WARNING:{warning_count}"
                        
                        print(f"{timestamp} 📤 {topic_name:15} #{message_count:04} | {len(payload):5}b | {len(values):2} tags{alarm_str}")
                        
                        # Print detailed alarm info
                        if alarms_in_topic:
                            for alarm in alarms_in_topic:
                                level_icon = "🔴" if alarm['severity'] == 1 else "⚠️ "
                                severity_name = "CRITICAL" if alarm['severity'] == 1 else "WARNING"
                                equipment = alarm.get('metadata', {}).get('equipment', 'N/A')
                                print(f"         {level_icon} {severity_name:8} | {alarm['tag_id']:30} | {equipment:15} | {alarm['message'][:50]}")
                        
                        # Print equipment status changes
                        equipment_status_count = sum(1 for v in values if 'RUN_STATUS' in v.get('tag', '') or v.get('tag') == 'TURBINE1_STATUS' or 'TRIP_STATUS' in v.get('tag', ''))
                        if equipment_status_count > 0:
                            print(f"         📊 Equipment status tags: {equipment_status_count}")
                    else:
                        print(f"❌ Failed to publish to {topic_name}")
                    
                    # Add delay between topic publishes to reduce message rate
                    time.sleep(0.2)  # 200ms delay between each topic
                
                time.sleep(PUBLISH_INTERVAL)
                
        except KeyboardInterrupt:
            print(f"\n\n{'='*80}")
            print(f"⏹️  Stopped. Published {message_count} messages")
            
            # Print alarm statistics
            total_alarms = sum(1 for state in self.tag_states.values() 
                             if state['alarm_level'] != AlarmLevel.NORMAL)
            critical_alarms = sum(1 for state in self.tag_states.values() 
                                 if state['alarm_level'] == AlarmLevel.CRITICAL)
            warning_alarms = sum(1 for state in self.tag_states.values() 
                                if state['alarm_level'] == AlarmLevel.WARNING)
            
            print(f"📊 Final Alarm Status:")
            print(f"   🔴 CRITICAL: {critical_alarms}")
            print(f"   ⚠️  WARNING:  {warning_alarms}")
            print(f"   ✅ NORMAL:   {len(self.tag_states) - total_alarms}")
            print(f"{'='*80}")
    
    def update_interlock_states(self):
        """
        REMOVED: historian_raw.interlock_state_tracking writes are owned exclusively by the
        C# InterlockEvaluationService. This method previously inserted random/simulated
        interlock states using random.choice() — a violation of the no-simulation-code policy
        (see copilot-instructions.md) AND a duplication of C# process ownership.

        Interlock DB ownership rule:
          - C# InterlockEvaluationService evaluates OPC tag values (value > 0.5 = SATISFIED,
            value <= 0.5 = VIOLATED) and writes every state transition to interlock_state_tracking.
          - HMI test publisher must NOT write to this table.
          - Operator BYPASS/DISABLE actions are still written by the HMI alarm_controller
            via the /api/alarms/interlocks/bypass endpoint (UPDATE path only, not INSERT).
        """
        # No-op — C# InterlockEvaluationService owns interlock_state_tracking
        pass
    
    def run(self):
        """Main execution"""
        print("\n🚀 DB-Based MQTT Test Publisher - ENHANCED TRIP GENERATION MODE")
        print("="*80)
        print("⚡ ENHANCEMENTS FOR FREQUENT TRIP TESTING:")
        print("  ✓ Load equipment dynamically from tag_master")
        print("  ✓ Generate trip events based on actual equipment data")
        print("  ✓ Insert trip events to historian_raw.trip_event_tracking")
        print(f"  ✓ Alarm generation interval: Every {ALARM_GENERATION_INTERVAL_SECONDS // 60} minutes")
        print("  ✓ Critical alarm rate: 60% (was 30%)")
        print("  ✓ Trip probability: 85% (was 15%)")
        print("  ✓ Alarm recovery: 5-8 cycles (was 10-20 cycles)")
        print("  ✓ Equipment restart: 15-25 seconds (was 20-40 seconds)")
        print("  ✓ TURBINE_STATUS: Boolean true/false (matches DB schema)")
        print("  ✓ Alarm priorities: P5 (Critical) and P4 (Urgent) for trip detection")
        print("="*80)
        
        # Connect to MQTT
        if not self.connect_mqtt():
            return
        
        # Load equipment from tag_master (MUST BE FIRST)
        print("\n📦 Loading equipment from tag_master...")
        if not self.load_equipment_from_tag_master():
            print("❌ No equipment found in tag_master")
            return
        
        # Load topics and tags from database
        if not self.load_topics_and_tags_from_db():
            print("❌ No topics/tags found in database")
            return
        
        print("\n📋 Equipment Monitored for Trips:")
        for equipment_id in self.equipment_states.keys():
            equipment_meta = self.equipment_metadata.get(equipment_id, {})
            criticality = equipment_meta.get('criticality', 'N/A')
            trip_cats = equipment_meta.get('trip_categories', 'N/A')
            if equipment_id == 'Turbine1' or equipment_id == 'TURBINE':
                print(f"  • {equipment_id}_STATUS (true=RUNNING, false=STOPPED) - Boolean")
            else:
                print(f"  • {equipment_id}_RUN_STATUS (0=STOPPED, 1=RUNNING) - Integer")
            print(f"    └─ {equipment_id}_TRIP_STATUS (0=NORMAL, 1=TRIPPED)")
            print(f"    └─ Criticality: {criticality}, Categories: {trip_cats}")
        print("="*80)
        
        # Start publishing
        self.publish_test_data()

if __name__ == '__main__':
    publisher = DBBasedMQTTPublisher()
    publisher.run()
