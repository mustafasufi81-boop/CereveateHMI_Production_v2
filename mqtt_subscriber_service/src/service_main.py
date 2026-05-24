"""
MQTT Subscriber Service
Main service orchestrator
"""

import json
import signal
import sys
import time
from datetime import datetime
from src.utils.config_loader import ConfigLoader
from src.monitoring.logger import ServiceLogger, get_logger
from src.database.db_connection import DatabaseConnection
from src.database.audit_dao import AuditDAO
from src.database.historian_dao import HistorianDAO
from src.mqtt.mqtt_client import MQTTClient
from src.cache.topic_cache import TopicCache
from src.cache.tag_master_cache import TagMasterCache
from src.processing.thread_manager import ThreadPoolManager
from src.processing.message_processor import MessageProcessor
from src.validation.validator import MessageValidator
from src.validation.input_sanitizer import InputSanitizer
from src.monitoring.health_check import HealthCheck
from src.monitoring.metrics import MetricsCollector
from src.models.message_models import MQTTMessage

logger = None  # Will be initialized after logger setup


class MQTTSubscriberService:
    """Main MQTT Subscriber Service"""
    
    def __init__(self, config_path: str = 'config/service_config.yaml'):
        """
        Initialize MQTT Subscriber Service
        
        Args:
            config_path: Path to configuration file
        """
        # Load configuration
        config_loader = ConfigLoader(config_path)
        self.config = config_loader.load()
        
        # Initialize logger
        ServiceLogger.initialize()
        global logger
        logger = get_logger(__name__)
        
        logger.info("=" * 60)
        logger.info("MQTT Subscriber Service Starting...")
        logger.info("=" * 60)
        
        # Initialize components
        self.db = None
        self.mqtt_client = None
        self.topic_cache = None
        self.tag_master_cache = None
        self.thread_pool = None
        self.message_processor = None
        self.health_check = None
        self.metrics = MetricsCollector()
        
        self.running = False
        
        # Setup signal handlers (only if running as standalone, not as Windows service)
        try:
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
        except ValueError:
            # Signal only works in main thread - skip for Windows service
            logger.info("Running as Windows Service - signal handlers skipped")
    
    def initialize(self):
        """Initialize all service components"""
        try:
            logger.info("Initializing service components...")
            
            # 1. Initialize database connection
            logger.info("1/8 Initializing database connection...")
            self.db = DatabaseConnection(self.config['database'])
            self.db.initialize()
            
            if not self.db.test_connection():
                raise RuntimeError("Database connection test failed")
            logger.info("✓ Database connected")
            
            # 2. Initialize DAOs
            logger.info("2/8 Initializing Data Access Objects...")
            self.audit_dao = AuditDAO(self.db)
            self.historian_dao = HistorianDAO(self.db)
            
            # Import trip detection DAOs
            from src.database.trip_dao import TripDAO
            from src.database.interlock_dao import InterlockDAO
            
            self.trip_dao = TripDAO(self.db)
            self.interlock_dao = InterlockDAO(self.db)
            logger.info("✓ DAOs initialized (including Trip and Interlock DAOs)")
            
            # 3. Initialize caches
            logger.info("3/8 Initializing caches...")
            cache_refresh_interval = self.config['service']['topic_cache_refresh_interval']
            
            self.topic_cache = TopicCache(self.db, cache_refresh_interval)
            self.topic_cache.load()
            
            self.tag_master_cache = TagMasterCache(self.db, cache_refresh_interval)
            self.tag_master_cache.load()
            logger.info("✓ Caches loaded")
            
            # 4. Initialize validator and sanitizer
            logger.info("4/8 Initializing validator and sanitizer...")
            self.validator = MessageValidator(self.config)
            self.sanitizer = InputSanitizer(self.config)
            logger.info("✓ Validator and sanitizer initialized")
            
            # 5. Initialize message processor
            logger.info("5/8 Initializing message processor...")
            self.message_processor = MessageProcessor(
                self.config,
                self.topic_cache,
                self.tag_master_cache,
                self.audit_dao,
                self.historian_dao,
                self.validator
            )
            logger.info("✓ Message processor initialized")
            
            # 6. Initialize thread pool
            logger.info("6/8 Initializing thread pool...")
            num_workers = self.config['service']['worker_threads']
            self.thread_pool = ThreadPoolManager(num_workers)
            self.thread_pool.start(self._process_mqtt_message)
            logger.info(f"✓ Thread pool started with {num_workers} workers")
            
            # 7. Initialize MQTT client
            logger.info("7/8 Initializing MQTT client...")
            self.mqtt_client = MQTTClient(self.config)
            self.mqtt_client.initialize(self._on_mqtt_message)
            self.mqtt_client.connect()
            
            # Subscribe to topics
            time.sleep(2)  # Wait for connection
            topics = self.topic_cache.get_all_topics()
            for topic in topics:
                qos = self.topic_cache.get_qos(topic)
                self.mqtt_client.subscribe(topic, qos)
            
            logger.info(f"✓ MQTT client connected and subscribed to {len(topics)} topics")
            
            # 8. Initialize health check
            logger.info("8/9 Initializing health check...")
            self.health_check = HealthCheck(
                self.db,
                self.mqtt_client,
                self.topic_cache,
                self.tag_master_cache,
                self.thread_pool
            )
            
            # 9. Initialize trip detection service (if enabled)
            logger.info("9/9 Initializing trip detection service...")
            trip_config = self.config.get('trip_detection', {})
            if trip_config.get('enabled', False):
                from src.processing.trip_detection import TripDetectionService
                
                self.trip_detector = TripDetectionService(
                    self.trip_dao,
                    self.historian_dao,
                    trip_config
                )
                logger.info("✓ Trip detection service initialized")
            else:
                self.trip_detector = None
                logger.info("✓ Trip detection service disabled")
            logger.info("✓ Health check initialized")
            
            logger.info("=" * 60)
            logger.info("All components initialized successfully")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"Failed to initialize service: {e}")
            raise
    
    def start(self):
        """Start the service"""
        self.running = True
        logger.info("MQTT Subscriber Service is running...")
        logger.info("Press Ctrl+C to stop")
        
        try:
            # Main loop - monitor health and log metrics
            metrics_interval = self.config['monitoring'].get('metrics_log_interval', 60)
            last_metrics_time = time.time()
            
            while self.running:
                time.sleep(1)  # Shorter sleep to respond faster to stop requests
                
                # Log metrics periodically
                current_time = time.time()
                if current_time - last_metrics_time >= metrics_interval:
                    logger.info(self.metrics.get_summary())
                    last_metrics_time = current_time
                    
        except KeyboardInterrupt:
            logger.info("Shutdown signal received")
        finally:
            self.shutdown()
    
    def stop(self):
        """Stop the service (called by Windows Service)"""
        logger.info("Stop command received")
        self.running = False
        # Give it a moment to exit the loop
        time.sleep(2)
        self.shutdown()
    
    def shutdown(self):
        """Shutdown the service gracefully"""
        if not self.running:
            return
        
        logger.info("=" * 60)
        logger.info("Shutting down MQTT Subscriber Service...")
        logger.info("=" * 60)
        
        self.running = False
        
        try:
            # Stop MQTT client
            if self.mqtt_client:
                logger.info("Disconnecting MQTT client...")
                self.mqtt_client.disconnect()
            
            # Stop thread pool
            if self.thread_pool:
                logger.info("Stopping thread pool...")
                self.thread_pool.stop(wait=True)
            
            # Stop caches
            if self.topic_cache:
                logger.info("Stopping topic cache...")
                self.topic_cache.shutdown()
            
            if self.tag_master_cache:
                logger.info("Stopping tag master cache...")
                self.tag_master_cache.shutdown()
            
            # Close database connection
            if self.db:
                logger.info("Closing database connection...")
                self.db.close()
            
            # Log final metrics
            logger.info("Final Metrics:")
            logger.info(self.metrics.get_summary())
            
            logger.info("=" * 60)
            logger.info("MQTT Subscriber Service stopped")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    def _on_mqtt_message(self, topic: str, payload: bytes, qos: int):
        """
        Callback for MQTT message received
        
        Args:
            topic: MQTT topic
            payload: Message payload
            qos: Quality of Service level
        """
        try:
            self.metrics.record_message_received()
            
            # Create MQTT message object
            mqtt_msg = MQTTMessage(
                topic=topic,
                payload=payload,
                qos=qos
            )
            
            # Submit to thread pool for processing
            submitted = self.thread_pool.submit_task(mqtt_msg)
            
            if not submitted:
                logger.warning(f"Failed to submit message to queue (queue full)")
                self.metrics.record_message_processed(0, False)
                
        except Exception as e:
            logger.error(f"Error handling MQTT message: {e}")
            self.metrics.record_message_processed(0, False)
    
    def _process_mqtt_message(self, mqtt_msg: MQTTMessage):
        """
        Process MQTT message (called by worker thread)
        
        Args:
            mqtt_msg: MQTTMessage object
        """
        try:
            # Process trip detection BEFORE standard processing (parallel)
            if self.trip_detector:
                self._process_trip_detection(mqtt_msg)
            
            # Standard message processing
            result = self.message_processor.process_message(mqtt_msg)
            
            self.metrics.record_message_processed(result.processing_time_ms, result.success)
            
            if not result.success:
                if 'validation' in result.error_message.lower():
                    self.metrics.record_validation_error()
            else:
                self.metrics.record_database_insert(result.records_inserted, True)
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            self.metrics.record_message_processed(0, False)
    
    def _process_trip_detection(self, mqtt_msg):
        """
        Process trip detection from MQTT message
        
        Args:
            mqtt_msg: MQTTMessage object with raw payload
        """
        if not self.trip_detector:
            logger.debug("⚠️ Trip detector not initialized, skipping")
            return
            
        try:
            # Parse JSON payload
            try:
                payload = json.loads(mqtt_msg.payload)
                logger.debug(f"🔍 Trip detection processing message on topic: {mqtt_msg.topic}")
            except Exception as parse_err:
                logger.debug(f"⚠️ Failed to parse JSON for trip detection: {parse_err}")
                return  # Not JSON, skip
            
            timestamp_str = payload.get('timestamp', datetime.utcnow().isoformat())
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            
            # Process alarm events from alarm_summary
            alarm_summary = payload.get('alarm_summary', {})
            alarms = alarm_summary.get('alarms', [])
            logger.debug(f"📋 Found {len(alarms)} alarms in alarm_summary")
            
            for alarm in alarms:
                # Map severity to priority (1=CRITICAL → priority 5, 2=WARNING → priority 4)
                severity = alarm.get('severity', 3)
                priority = 5 if severity == 1 else (4 if severity == 2 else 1)
                
                # Only process high-priority alarms (priority >= 4)
                if priority >= 4:
                    # Build alarm event dictionary matching expected format
                    alarm_event = {
                        'event_id': alarm.get('tag_id', 'UNKNOWN'),
                        'tag_id': alarm.get('tag_id', 'UNKNOWN'),
                        'event_type': alarm.get('event_type', 'UNKNOWN'),
                        'alarm_priority': priority,
                        'alarm_state': 'ACTIVE',
                        'time': timestamp,
                        'message': alarm.get('message', ''),
                        'metadata': alarm.get('metadata', {})  # Include equipment metadata
                    }
                    logger.debug(f"🚨 Processing critical alarm: tag={alarm_event['tag_id']}, priority={priority}, severity={severity}")
                    self.trip_detector.process_alarm_event(alarm_event)
            
            # Process equipment status from special RUN_STATUS tags
            values = payload.get('values', [])
            run_status_count = 0
            for value_entry in values:
                tag = value_entry.get('tag', '')
                
                # Check if this is a RUN_STATUS tag (includes TURBINE_STATUS, *_RUN_STATUS, etc.)
                if 'RUN_STATUS' in tag or 'RUNNING' in tag or tag == 'TURBINE_STATUS':
                    # Get value - supports both integer (0/1) and boolean (false/true)
                    run_value = value_entry.get('value', 0)
                    
                    # Convert boolean to float (true→1.0, false→0.0) for trip detector
                    if isinstance(run_value, bool):
                        run_value = 1.0 if run_value else 0.0
                    else:
                        run_value = float(run_value)
                    
                    run_status_count += 1
                    logger.debug(f"⚙️ RUN_STATUS detected: tag={tag}, value={run_value} ({'RUNNING' if run_value else 'STOPPED'})")
                    
                    # Call with correct signature: tag_id, value, timestamp
                    self.trip_detector.process_equipment_status_change(
                        tag_id=tag,
                        value=run_value,
                        timestamp=timestamp
                    )
            
            if run_status_count > 0:
                logger.debug(f"✅ Processed {run_status_count} RUN_STATUS tags")
                    
        except Exception as e:
            logger.error(f"Error processing trip detection: {e}", exc_info=True)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}")
        self.running = False
    
    def get_health(self):
        """Get service health status"""
        if self.health_check:
            return self.health_check.check_health()
        return {'status': 'not_initialized'}
    
    def get_metrics(self):
        """Get service metrics"""
        return self.metrics.get_metrics()


def main():
    """Main entry point"""
    try:
        service = MQTTSubscriberService()
        service.initialize()
        service.start()
    except Exception as e:
        if logger:
            logger.error(f"Service error: {e}")
        else:
            print(f"Service error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
