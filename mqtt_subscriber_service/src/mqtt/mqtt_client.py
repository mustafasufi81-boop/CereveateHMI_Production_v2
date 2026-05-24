"""
MQTT Client Manager
Handles MQTT broker connections and message subscriptions
"""

import paho.mqtt.client as mqtt
import ssl
import threading
from typing import Callable, Optional
from src.monitoring.logger import get_logger

logger = get_logger(__name__)


class MQTTClient:
    """MQTT Client with TLS support and connection management"""
    
    def __init__(self, config: dict):
        """
        Initialize MQTT Client
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.mqtt_config = config['mqtt']
        self.security_config = config.get('security', {})
        
        self.client = None
        self.is_connected = False
        self.lock = threading.Lock()
        self.message_callback = None
        
        # Statistics
        self.stats = {
            'messages_received': 0,
            'bytes_received': 0,
            'connection_attempts': 0,
            'reconnections': 0
        }
    
    def initialize(self, message_callback: Callable):
        """
        Initialize MQTT client
        
        Args:
            message_callback: Callback function for received messages
        """
        self.message_callback = message_callback
        
        # Create client
        client_id = self.mqtt_config.get('client_id', 'mqtt_subscriber_service')
        clean_session = self.mqtt_config.get('clean_session', False)
        
        self.client = mqtt.Client(client_id=client_id, clean_session=clean_session)
        
        # Set callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        
        # Set credentials if provided
        if self.mqtt_config.get('username'):
            self.client.username_pw_set(
                username=self.mqtt_config['username'],
                password=self.mqtt_config.get('password', '')
            )
        
        # Configure TLS if enabled
        if self.security_config.get('enable_tls', False):
            self._configure_tls()
        
        logger.info(f"MQTT Client initialized with client_id: {client_id}")
    
    def _configure_tls(self):
        """Configure TLS/mTLS connection"""
        try:
            tls_config = self.security_config.get('tls', {})
            
            # Prepare TLS context
            tls_kwargs = {
                'ca_certs': tls_config.get('ca_cert'),
                'certfile': tls_config.get('client_cert'),
                'keyfile': tls_config.get('client_key'),
                'tls_version': ssl.PROTOCOL_TLSv1_2
            }
            
            # Remove None values
            tls_kwargs = {k: v for k, v in tls_kwargs.items() if v is not None}
            
            if tls_kwargs:
                self.client.tls_set(**tls_kwargs)
                logger.info("TLS configured for MQTT connection")
            else:
                logger.warning("TLS enabled but no certificates provided")
                
        except Exception as e:
            logger.error(f"Failed to configure TLS: {e}")
            raise
    
    def connect(self):
        """Connect to MQTT broker"""
        with self.lock:
            try:
                broker = self.mqtt_config.get('broker_host', self.mqtt_config.get('broker', 'localhost'))
                port = self.mqtt_config.get('broker_port', self.mqtt_config.get('port', 1883))
                keepalive = self.mqtt_config.get('keep_alive', self.mqtt_config.get('keepalive', 60))
                
                self.stats['connection_attempts'] += 1
                
                logger.info(f"Connecting to MQTT broker: {broker}:{port}")
                self.client.connect(broker, port, keepalive)
                
                # Start network loop in separate thread
                self.client.loop_start()
                
            except Exception as e:
                logger.error(f"Failed to connect to MQTT broker: {e}")
                raise
    
    def subscribe(self, topic: str, qos: int = 0):
        """
        Subscribe to MQTT topic
        
        Args:
            topic: MQTT topic to subscribe
            qos: Quality of Service level (0, 1, or 2)
        """
        try:
            result, mid = self.client.subscribe(topic, qos)
            if result == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"Subscribed to topic: {topic} (QoS {qos})")
            else:
                logger.error(f"Failed to subscribe to {topic}: {result}")
        except Exception as e:
            logger.error(f"Error subscribing to {topic}: {e}")
    
    def unsubscribe(self, topic: str):
        """
        Unsubscribe from MQTT topic
        
        Args:
            topic: MQTT topic to unsubscribe
        """
        try:
            result, mid = self.client.unsubscribe(topic)
            if result == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"Unsubscribed from topic: {topic}")
            else:
                logger.error(f"Failed to unsubscribe from {topic}: {result}")
        except Exception as e:
            logger.error(f"Error unsubscribing from {topic}: {e}")
    
    def disconnect(self):
        """Disconnect from MQTT broker"""
        with self.lock:
            if self.client:
                logger.info("Disconnecting from MQTT broker")
                self.client.loop_stop()
                self.client.disconnect()
                self.is_connected = False
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback when connected to broker"""
        if rc == 0:
            self.is_connected = True
            logger.info(f"Connected to MQTT broker (rc={rc})")
        else:
            self.is_connected = False
            error_messages = {
                1: "Incorrect protocol version",
                2: "Invalid client identifier",
                3: "Server unavailable",
                4: "Bad username or password",
                5: "Not authorized"
            }
            error_msg = error_messages.get(rc, f"Unknown error ({rc})")
            logger.error(f"Failed to connect to MQTT broker: {error_msg}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback when disconnected from broker"""
        self.is_connected = False
        if rc != 0:
            logger.warning(f"Unexpected disconnection from MQTT broker (rc={rc})")
        else:
            logger.info("Disconnected from MQTT broker (graceful shutdown)")
    
    def _on_message(self, client, userdata, msg):
        """Callback when message received"""
        try:
            self.stats['messages_received'] += 1
            self.stats['bytes_received'] += len(msg.payload)
            
            logger.debug(f"Message received - Topic: {msg.topic}, QoS: {msg.qos}, Payload size: {len(msg.payload)} bytes")
            
            # Call user-defined message callback
            if self.message_callback:
                self.message_callback(msg.topic, msg.payload, msg.qos)
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def get_stats(self) -> dict:
        """Get connection statistics"""
        return {
            **self.stats,
            'is_connected': self.is_connected
        }
