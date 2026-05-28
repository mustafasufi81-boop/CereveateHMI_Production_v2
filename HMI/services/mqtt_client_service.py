"""
MQTT Client Service for HMI Backend
Subscribes to MQTT broker for real-time tag data
Filters tags based on plc_name/server_progid relationship
"""

import json
import logging
import random
import threading
import time
from typing import Callable, Dict, List, Optional
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


def _is_numeric_string(s: str) -> bool:
    """Return True if string s represents a valid number (int or float)."""
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False

class MQTTClientService:
    """
    MQTT Client for receiving real-time tag data
    Subscribes to topics and forwards filtered data to callback
    """
    
    def __init__(self, mqtt_config: dict, topic_tag_mapper, on_message_callback: Callable):
        """
        Initialize MQTT Client Service
        
        Args:
            mqtt_config: MQTT configuration dict with broker, port, etc.
            topic_tag_mapper: TopicTagMapper instance for filtering
            on_message_callback: Function to call with filtered tag updates
        """
        self.broker_host = mqtt_config.get('broker_host', 'localhost')
        self.broker_port = mqtt_config.get('broker_port', 1883)
        self.username = mqtt_config.get('username')
        self.password = mqtt_config.get('password')
        self.client_id = mqtt_config.get('client_id', 'hmi_backend')
        self.keepalive = mqtt_config.get('keepalive', 60)
        
        self.topic_tag_mapper = topic_tag_mapper
        self.on_message_callback = on_message_callback
        
        self.client: Optional[mqtt.Client] = None
        self.is_connected = False
        self.subscribed_topics: List[str] = []
        
        # Reconnect state — exponential backoff forever, never permanently stops
        self._reconnect_attempts = 0
        self._reconnect_stopped = False   # kept for API compat but never set True permanently
        self._reconnect_thread: Optional[threading.Thread] = None
        # Backoff schedule: attempt 0→5s, 1→10s, 2→30s, 3+→60s, each +jitter(0..3s)
        self._backoff_delays = [5, 10, 30, 60]

        # Threading
        self._lock = threading.RLock()
        self._connect_thread = None
        
        logger.info(f"MQTTClientService initialized for broker: {self.broker_host}:{self.broker_port}")
    
    def connect(self):
        """Connect to MQTT broker in background thread"""
        if self._connect_thread and self._connect_thread.is_alive():
            logger.warning("MQTT connection already in progress")
            return
        
        self._connect_thread = threading.Thread(target=self._connect_async, daemon=True)
        self._connect_thread.start()
    
    def _connect_async(self):
        """Establish MQTT connection (runs in background thread)"""
        try:
            logger.info(f"[MQTT] Connecting to MQTT broker: {self.broker_host}:{self.broker_port}")
            
            # Create MQTT client with clean session
            self.client = mqtt.Client(
                client_id=self.client_id, 
                clean_session=False,
                protocol=mqtt.MQTTv311
            )
            
            # Set username/password if provided
            if self.username and self.password:
                self.client.username_pw_set(self.username, self.password)
            
            # Set callbacks
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            
            # Enable automatic reconnection
            self.client.reconnect_delay_set(min_delay=1, max_delay=30)
            
            # Connect to broker with longer keepalive
            self.client.connect(
                self.broker_host, 
                self.broker_port, 
                keepalive=self.keepalive
            )
            
            # Start network loop in background (non-blocking)
            self.client.loop_start()
            
            logger.info("[OK] MQTT connection initiated")
        
        except Exception as e:
            logger.error(f"[ERROR] Failed to connect to MQTT broker: {e}")
            self.is_connected = False
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback when connected to MQTT broker"""
        if rc == 0:
            self.is_connected = True
            logger.info("[OK] MQTT connected successfully")
            
            # Subscribe to all active topics
            self._subscribe_to_active_topics()
        else:
            self.is_connected = False
            error_messages = {
                1: "Connection refused - incorrect protocol version",
                2: "Connection refused - invalid client identifier",
                3: "Connection refused - server unavailable",
                4: "Connection refused - bad username or password",
                5: "Connection refused - not authorized"
            }
            error_msg = error_messages.get(rc, f"Unknown error code: {rc}")
            logger.error(f"[ERROR] MQTT connection failed: {error_msg}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback when disconnected from MQTT broker"""
        self.is_connected = False
        if rc != 0:
            self._reconnect_attempts += 1
            delay_base = self._backoff_delays[min(self._reconnect_attempts - 1, len(self._backoff_delays) - 1)]
            delay = delay_base + random.uniform(0, 3)
            logger.warning(
                f"[MQTT] DEGRADED+RETRYING — unexpected disconnect (code: {rc}), "
                f"attempt #{self._reconnect_attempts}, next retry in {delay:.1f}s"
            )
            # Spawn reconnect thread — never give up
            if not (self._reconnect_thread and self._reconnect_thread.is_alive()):
                self._reconnect_thread = threading.Thread(
                    target=self._reconnect_with_backoff,
                    args=(delay,),
                    daemon=True
                )
                self._reconnect_thread.start()
        else:
            logger.info("[MQTT] Disconnected cleanly")

    def _reconnect_with_backoff(self, initial_delay: float):
        """Retry MQTT connection forever with exponential backoff + jitter"""
        time.sleep(initial_delay)
        attempt = self._reconnect_attempts
        while True:
            try:
                logger.info(f"[MQTT] DEGRADED+RETRYING — reconnect attempt #{attempt}...")
                self.client.reconnect()
                logger.info("[MQTT] Reconnect succeeded — back to CONNECTED")
                self._reconnect_attempts = 0
                return
            except Exception as e:
                attempt += 1
                delay_base = self._backoff_delays[min(attempt - 1, len(self._backoff_delays) - 1)]
                delay = delay_base + random.uniform(0, 3)
                logger.warning(
                    f"[MQTT] DEGRADED+RETRYING — reconnect #{attempt} failed: {e}. "
                    f"Next retry in {delay:.1f}s"
                )
                time.sleep(delay)
    
    def _on_message(self, client, userdata, msg):
        """
        Callback when MQTT message received
        Filters tags based on topic-plc-tag relationship
        Supports multiple payload formats
        """
        # Increment message counter
        if not hasattr(self, '_message_count'):
            self._message_count = 0
            self._last_log_time = time.time()
        
        self._message_count += 1
        
        # Log message count every 5 seconds
        current_time = time.time()
        if current_time - self._last_log_time >= 5:
            logger.info(f"[MQTT] Received {self._message_count} MQTT messages in last 5 seconds")
            self._message_count = 0
            self._last_log_time = current_time
        
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            
            logger.info(f"[MQTT] Message received on topic: {topic} (size: {len(payload)} bytes)")
            
            # Parse JSON payload
            try:
                data = json.loads(payload)
                # Pretty print the JSON for better readability
                logger.info(f"[MQTT] Raw JSON payload (formatted):\n{json.dumps(data, indent=2)}")
                logger.info(f"[MQTT] Parsed JSON: file_id={data.get('file_id', 'N/A')}, tag_count={data.get('tag_count', len(data))}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse MQTT payload as JSON: {e}")
                return
            
            # Get tags array from payload - support multiple formats
            tags = data.get('tags', [])
            
            # Format 2: "data" array (used by mqtt_topic_test_generator.py)
            if not tags and 'data' in data:
                tags = data.get('data', [])
            
            # Format 3: "values" array — C# sends {tagId, value, quality, timestamp} (standard OPC bulk format)
            if not tags and 'values' in data:
                raw_values = data.get('values', [])
                logger.info(f"[MQTT] Processing {len(raw_values)} values from MQTT message")
                
                # Transform to standard format
                tags = []
                for item in raw_values:
                    # C# MqttPublisher sends 'tagId'; older generators may send 'tag' — support both
                    tag_name = item.get('tagId') or item.get('tag')
                    value = item.get('value')
                    data_type = item.get('dataType', '').lower()
                    
                    tag = {
                        'tag_id': tag_name,
                        'value': value,
                        'quality': 'G' if item.get('quality', 'Good').lower() == 'good' else 'B',
                        'time': item.get('timestamp'),
                        'plcId': item.get('plcId'),
                        'samples': item.get('samples', [])  # Include samples array if present
                    }
                    
                    # Map data types to correct value fields
                    # Numeric OPC data types: real4, real8, float, double, int1/2/4/8, uint1/2/4/8, number, word, dword
                    NUMERIC_DATA_TYPES = {
                        'float', 'double', 'int', 'int1', 'int2', 'int4', 'int8',
                        'uint', 'uint1', 'uint2', 'uint4', 'uint8',
                        'real4', 'real8', 'number', 'word', 'dword', 'byte', 'short', 'long'
                    }
                    is_numeric_type = data_type in NUMERIC_DATA_TYPES
                    # Also treat string values that look like numbers as numeric (unless explicitly 'string')
                    is_numeric_value = isinstance(value, (int, float)) or (
                        isinstance(value, str) and data_type != 'string' and _is_numeric_string(value)
                    )

                    if data_type == 'boolean' or isinstance(value, bool):
                        tag['value_bool'] = bool(value) if value is not None else None
                        tag['value_num'] = None
                        tag['value_text'] = None
                    elif data_type == 'string':
                        tag['value_text'] = str(value) if value is not None else None
                        tag['value_num'] = None
                        tag['value_bool'] = None
                    elif is_numeric_type or is_numeric_value:
                        try:
                            tag['value_num'] = float(value) if value is not None else None
                        except (ValueError, TypeError):
                            tag['value_num'] = None
                        tag['value_text'] = None
                        tag['value_bool'] = None
                    elif isinstance(value, str):
                        # Unknown type with string value — store as text
                        tag['value_text'] = value
                        tag['value_num'] = None
                        tag['value_bool'] = None
                    else:
                        # Fallback: try numeric
                        try:
                            tag['value_num'] = float(value) if value is not None else None
                        except (ValueError, TypeError):
                            tag['value_num'] = None
                        tag['value_text'] = None
                        tag['value_bool'] = None
                    
                    tags.append(tag)
                    
                logger.info(f"[MQTT] Transformed {len(tags)} tags: {', '.join([t['tag_id'] for t in tags[:5]])}{'...' if len(tags) > 5 else ''}")
            
            if not tags:
                logger.warning(f"No tags/values found in MQTT payload for topic: {topic}")
                return
            
            # Filter tags based on topic-plc-tag mapping
            filtered_tags = self.topic_tag_mapper.filter_tags_for_topic(topic, tags)
            
            if not filtered_tags:
                logger.info(f"[WARN] No matching tags for topic: {topic} (received {len(tags)} tags)")
                logger.info(f"📋 Tag IDs received: {', '.join([str(t.get('tag_id')) for t in tags[:10]])}")
                return
            
            logger.info(f"[MQTT] Filtered {len(filtered_tags)}/{len(tags)} tags for topic: {topic}")
            logger.info(f"[MQTT] Broadcasting {len(filtered_tags)} tags to WebSocket:")
            for tag in filtered_tags[:5]:  # Log first 5 tags
                logger.info(f"   - {tag.get('tag_id')}: value={tag.get('value_num') or tag.get('value_text') or tag.get('value_bool')}, quality={tag.get('quality')}")
            
            # Call callback with filtered tags
            if self.on_message_callback:
                try:
                    self.on_message_callback(topic, filtered_tags, data)
                except Exception as e:
                    logger.error(f"Error in MQTT message callback: {e}")
            
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")
    
    def _subscribe_to_active_topics(self):
        """Subscribe to all active MQTT topics from configuration"""
        try:
            # Get active topics from mapper
            active_topics = self.topic_tag_mapper.get_active_topics()
            
            if not active_topics:
                logger.warning("No active MQTT topics found in configuration")
                return
            
            # Reset list on each connect/reconnect to avoid growing duplicates
            self.subscribed_topics = []

            # Subscribe to each topic
            for topic_info in active_topics:
                topic_name = topic_info['topic_name']
                qos = topic_info.get('qos', 1)
                
                try:
                    result, mid = self.client.subscribe(topic_name, qos=qos)
                    
                    if result == mqtt.MQTT_ERR_SUCCESS:
                        self.subscribed_topics.append(topic_name)
                        logger.info(f"[MQTT] Subscribed to topic: {topic_name} (QoS: {qos})")
                    else:
                        logger.error(f"Failed to subscribe to topic: {topic_name}")
                        
                except Exception as e:
                    logger.error(f"Error subscribing to topic {topic_name}: {e}")
            
            logger.info(f"[OK] Subscribed to {len(self.subscribed_topics)} MQTT topics")
            
        except Exception as e:
            logger.error(f"Error subscribing to topics: {e}")
    
    def disconnect(self):
        """Disconnect from MQTT broker"""
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
                logger.info("MQTT client disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting MQTT client: {e}")
    
    def get_subscribed_topics(self) -> List[str]:
        """Get list of currently subscribed topics"""
        with self._lock:
            return self.subscribed_topics.copy()
    
    def is_topic_subscribed(self, topic: str) -> bool:
        """Check if a topic is subscribed"""
        with self._lock:
            return topic in self.subscribed_topics
