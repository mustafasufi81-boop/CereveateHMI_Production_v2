"""
Health Check Module
Monitors service health and component status
"""

from datetime import datetime
from typing import Dict, Any
from src.monitoring.logger import get_logger

logger = get_logger(__name__)


class HealthCheck:
    """Health check for MQTT Subscriber Service"""
    
    def __init__(self, db_connection, mqtt_client, topic_cache, tag_master_cache, thread_pool):
        """
        Initialize Health Check
        
        Args:
            db_connection: DatabaseConnection instance
            mqtt_client: MQTTClient instance
            topic_cache: TopicCache instance
            tag_master_cache: TagMasterCache instance
            thread_pool: ThreadPoolManager instance
        """
        self.db = db_connection
        self.mqtt_client = mqtt_client
        self.topic_cache = topic_cache
        self.tag_master_cache = tag_master_cache
        self.thread_pool = thread_pool
        
        self.startup_time = datetime.utcnow()
        
        logger.info("HealthCheck initialized")
    
    def check_health(self) -> Dict[str, Any]:
        """
        Perform comprehensive health check
        
        Returns:
            Health status dictionary
        """
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'uptime_seconds': (datetime.utcnow() - self.startup_time).total_seconds(),
            'components': {}
        }
        
        # Check database connection
        try:
            db_healthy = self.db.test_connection()
            health_status['components']['database'] = {
                'status': 'healthy' if db_healthy else 'unhealthy',
                'message': 'Connected' if db_healthy else 'Connection failed'
            }
            if not db_healthy:
                health_status['status'] = 'degraded'
        except Exception as e:
            health_status['components']['database'] = {
                'status': 'unhealthy',
                'message': str(e)
            }
            health_status['status'] = 'degraded'
        
        # Check MQTT connection
        try:
            mqtt_stats = self.mqtt_client.get_stats()
            mqtt_healthy = mqtt_stats['is_connected']
            health_status['components']['mqtt'] = {
                'status': 'healthy' if mqtt_healthy else 'unhealthy',
                'message': 'Connected' if mqtt_healthy else 'Not connected',
                'stats': mqtt_stats
            }
            if not mqtt_healthy:
                health_status['status'] = 'degraded'
        except Exception as e:
            health_status['components']['mqtt'] = {
                'status': 'unhealthy',
                'message': str(e)
            }
            health_status['status'] = 'degraded'
        
        # Check topic cache
        try:
            topic_stats = self.topic_cache.get_stats()
            topic_healthy = topic_stats['cached_topics'] > 0
            health_status['components']['topic_cache'] = {
                'status': 'healthy' if topic_healthy else 'warning',
                'message': f"{topic_stats['cached_topics']} topics loaded",
                'stats': topic_stats
            }
            if not topic_healthy:
                health_status['status'] = 'degraded'
        except Exception as e:
            health_status['components']['topic_cache'] = {
                'status': 'unhealthy',
                'message': str(e)
            }
            health_status['status'] = 'degraded'
        
        # Check tag master cache
        try:
            tag_stats = self.tag_master_cache.get_stats()
            tag_healthy = tag_stats['cached_tags'] > 0
            health_status['components']['tag_master_cache'] = {
                'status': 'healthy' if tag_healthy else 'warning',
                'message': f"{tag_stats['cached_tags']} tags loaded",
                'stats': tag_stats
            }
            if not tag_healthy:
                health_status['status'] = 'degraded'
        except Exception as e:
            health_status['components']['tag_master_cache'] = {
                'status': 'unhealthy',
                'message': str(e)
            }
            health_status['status'] = 'degraded'
        
        # Check thread pool
        try:
            thread_stats = self.thread_pool.get_stats()
            thread_healthy = thread_stats['is_running']
            health_status['components']['thread_pool'] = {
                'status': 'healthy' if thread_healthy else 'unhealthy',
                'message': f"{thread_stats['num_workers']} workers running" if thread_healthy else 'Not running',
                'stats': thread_stats
            }
            if not thread_healthy:
                health_status['status'] = 'unhealthy'
        except Exception as e:
            health_status['components']['thread_pool'] = {
                'status': 'unhealthy',
                'message': str(e)
            }
            health_status['status'] = 'unhealthy'
        
        return health_status
    
    def check_database(self) -> bool:
        """
        Check database connectivity
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            return self.db.test_connection()
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    def check_mqtt(self) -> bool:
        """
        Check MQTT connectivity
        
        Returns:
            True if connected, False otherwise
        """
        try:
            return self.mqtt_client.is_connected
        except Exception:
            return False
    
    def get_component_status(self, component_name: str) -> Dict[str, Any]:
        """
        Get status of specific component
        
        Args:
            component_name: Component name (database, mqtt, topic_cache, tag_master_cache, thread_pool)
            
        Returns:
            Component status dictionary
        """
        health = self.check_health()
        return health['components'].get(component_name, {'status': 'unknown'})
