"""
MQTT Topic Configuration Cache
Loads and caches topic configurations from database
"""

import threading
from typing import Dict, Optional, List
from datetime import datetime
from src.monitoring.logger import get_logger

logger = get_logger(__name__)


class TopicCache:
    """In-memory cache for MQTT topic configurations"""
    
    def __init__(self, db_connection, refresh_interval: int = 300):
        """
        Initialize Topic Cache
        
        Args:
            db_connection: DatabaseConnection instance
            refresh_interval: Cache refresh interval in seconds
        """
        self.db = db_connection
        self.refresh_interval = refresh_interval
        
        self._cache: Dict[str, dict] = {}
        self._lock = threading.RLock()
        self._last_refresh = None
        self._refresh_timer = None
        
        logger.info(f"TopicCache initialized with {refresh_interval}s refresh interval")
    
    def load(self):
        """Load topic configurations from database"""
        with self._lock:
            try:
                query = """
                    SELECT 
                        topic_id,
                        topic_name,
                        plc_name,
                        qos,
                        is_active,
                        processing_rules
                    FROM historian_raw.mqtt_topic_config
                    WHERE is_active = true
                    ORDER BY topic_name
                """
                
                rows = self.db.execute_query(query, fetch=True)
                
                new_cache = {}
                for row in rows:
                    topic_id, topic_name, plc_name, qos, is_active, processing_rules = row
                    
                    new_cache[topic_name] = {
                        'topic_id': topic_id,
                        'topic_name': topic_name,
                        'plc_name': plc_name,
                        'qos': qos,
                        'is_active': is_active,
                        'processing_rules': processing_rules
                    }
                
                self._cache = new_cache
                self._last_refresh = datetime.utcnow()
                
                logger.info(f"Loaded {len(self._cache)} active topics from database")
                
                # Schedule next refresh
                self._schedule_refresh()
                
            except Exception as e:
                logger.error(f"Failed to load topic configurations: {e}")
                raise
    
    def _schedule_refresh(self):
        """Schedule automatic cache refresh"""
        if self._refresh_timer:
            self._refresh_timer.cancel()
        
        self._refresh_timer = threading.Timer(self.refresh_interval, self.load)
        self._refresh_timer.daemon = True
        self._refresh_timer.start()
    
    def get(self, topic_name: str) -> Optional[dict]:
        """
        Get topic configuration
        
        Args:
            topic_name: MQTT topic name
            
        Returns:
            Topic configuration dict or None if not found
        """
        with self._lock:
            return self._cache.get(topic_name)
    
    def get_all_topics(self) -> List[str]:
        """
        Get all cached topic names
        
        Returns:
            List of topic names
        """
        with self._lock:
            return list(self._cache.keys())
    
    def is_topic_enabled(self, topic_name: str) -> bool:
        """
        Check if topic is enabled
        
        Args:
            topic_name: MQTT topic name
            
        Returns:
            True if enabled, False otherwise
        """
        config = self.get(topic_name)
        return config is not None and config.get('is_active', False)
    
    def get_qos(self, topic_name: str) -> int:
        """
        Get QoS level for topic
        
        Args:
            topic_name: MQTT topic name
            
        Returns:
            QoS level (0, 1, or 2), default 0
        """
        config = self.get(topic_name)
        return config.get('qos', 0) if config else 0
    
    def get_data_schema(self, topic_name: str) -> Optional[dict]:
        """
        Get data schema for topic
        
        Args:
            topic_name: MQTT topic name
            
        Returns:
            Data schema dict or None
        """
        config = self.get(topic_name)
        return config.get('data_schema') if config else None
    
    def get_validation_rules(self, topic_name: str) -> Optional[dict]:
        """
        Get validation rules for topic
        
        Args:
            topic_name: MQTT topic name
            
        Returns:
            Validation rules dict or None
        """
        config = self.get(topic_name)
        return config.get('validation_rules') if config else None
    
    def shutdown(self):
        """Stop cache refresh timer"""
        if self._refresh_timer:
            self._refresh_timer.cancel()
            logger.info("TopicCache refresh timer stopped")
    
    def get_stats(self) -> dict:
        """Get cache statistics"""
        with self._lock:
            return {
                'cached_topics': len(self._cache),
                'last_refresh': self._last_refresh.isoformat() if self._last_refresh else None,
                'refresh_interval_seconds': self.refresh_interval
            }
