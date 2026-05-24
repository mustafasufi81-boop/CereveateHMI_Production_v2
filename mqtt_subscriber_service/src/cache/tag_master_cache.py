"""
Tag Master Cache
Loads and caches tag configurations from tag_master (READ-ONLY)
"""

import threading
from typing import Dict, Optional, List
from datetime import datetime
from src.monitoring.logger import get_logger

logger = get_logger(__name__)


class TagMasterCache:
    """In-memory cache for tag_master data (READ-ONLY validation)"""
    
    def __init__(self, db_connection, refresh_interval: int = 300):
        """
        Initialize Tag Master Cache
        
        Args:
            db_connection: DatabaseConnection instance
            refresh_interval: Cache refresh interval in seconds
        """
        self.db = db_connection
        self.refresh_interval = refresh_interval
        
        self._cache: Dict[str, dict] = {}  # Key: tag_id
        self._lock = threading.RLock()
        self._last_refresh = None
        self._refresh_timer = None
        
        logger.info(f"TagMasterCache initialized with {refresh_interval}s refresh interval")
    
    def load(self):
        """Load tag configurations from historian_meta.tag_master (READ-ONLY)"""
        with self._lock:
            try:
                query = """
                    SELECT 
                        tag_id,
                        tag_name,
                        data_type,
                        description,
                        eng_unit,
                        min_value,
                        max_value,
                        enabled,
                        COALESCE(db_logging_interval_ms, 5000) AS db_logging_interval_ms,
                        COALESCE(deadband_value, 0.0) AS deadband_value
                    FROM historian_meta.tag_master
                    WHERE enabled = true
                    ORDER BY tag_id
                """
                
                rows = self.db.execute_query(query, fetch=True)
                
                new_cache = {}
                for row in rows:
                    tag_id, tag_name, data_type, description, eng_unit, min_value, max_value, enabled, db_logging_interval_ms, deadband_value = row
                    
                    new_cache[tag_id] = {
                        'tag_id': tag_id,
                        'tag_name': tag_name,
                        'data_type': data_type,
                        'description': description,
                        'eng_unit': eng_unit,
                        'min_value': min_value,
                        'max_value': max_value,
                        'enabled': enabled,
                        'db_logging_interval_ms': int(db_logging_interval_ms),
                        'deadband_value': float(deadband_value)
                    }
                
                self._cache = new_cache
                self._last_refresh = datetime.utcnow()
                
                logger.info(f"Loaded {len(self._cache)} active tags from tag_master")
                
                # Schedule next refresh
                self._schedule_refresh()
                
            except Exception as e:
                logger.error(f"Failed to load tag_master data: {e}")
                raise
    
    def _schedule_refresh(self):
        """Schedule automatic cache refresh"""
        if self._refresh_timer:
            self._refresh_timer.cancel()
        
        self._refresh_timer = threading.Timer(self.refresh_interval, self.load)
        self._refresh_timer.daemon = True
        self._refresh_timer.start()
    
    def get(self, tag_id: str) -> Optional[dict]:
        """
        Get tag configuration
        
        Args:
            tag_id: Tag identifier
            
        Returns:
            Tag configuration dict or None if not found
        """
        with self._lock:
            return self._cache.get(tag_id)
    
    def exists(self, tag_id: str) -> bool:
        """
        Check if tag exists in tag_master
        
        Args:
            tag_id: Tag identifier
            
        Returns:
            True if tag exists and is active
        """
        return self.get(tag_id) is not None
    
    def validate_tag(self, tag_id: str) -> tuple[bool, Optional[str]]:
        """
        Validate tag exists in tag_master
        
        Args:
            tag_id: Tag identifier
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        tag = self.get(tag_id)
        
        if tag is None:
            return False, f"Tag '{tag_id}' not found in tag_master"
        
        if not tag.get('is_active', False):
            return False, f"Tag '{tag_id}' is not active"
        
        return True, None
    
    def validate_value_range(self, tag_id: str, value: float) -> tuple[bool, Optional[str]]:
        """
        Validate numeric value against tag's min/max range
        
        Args:
            tag_id: Tag identifier
            value: Numeric value to validate
            
        Returns:
            Tuple of (is_valid, warning_message)
        """
        tag = self.get(tag_id)
        
        if tag is None:
            return False, f"Tag '{tag_id}' not found"
        
        min_value = tag.get('min_value')
        max_value = tag.get('max_value')
        
        if min_value is not None and value < min_value:
            return False, f"Value {value} below minimum {min_value} for tag '{tag_id}'"
        
        if max_value is not None and value > max_value:
            return False, f"Value {value} above maximum {max_value} for tag '{tag_id}'"
        
        return True, None
    
    def get_data_type(self, tag_id: str) -> Optional[str]:
        """
        Get data type for tag
        
        Args:
            tag_id: Tag identifier
            
        Returns:
            Data type string or None
        """
        tag = self.get(tag_id)
        return tag.get('data_type') if tag else None
    
    def get_all_tag_ids(self) -> List[str]:
        """
        Get all cached tag IDs
        
        Returns:
            List of tag IDs
        """
        with self._lock:
            return list(self._cache.keys())
    
    def get_random_tags(self, count: int = 10) -> List[dict]:
        """
        Get random sample of tags (for test data generation)
        
        Args:
            count: Number of tags to return
            
        Returns:
            List of tag configuration dicts
        """
        import random
        
        with self._lock:
            all_tags = list(self._cache.values())
            return random.sample(all_tags, min(count, len(all_tags)))
    
    def shutdown(self):
        """Stop cache refresh timer"""
        if self._refresh_timer:
            self._refresh_timer.cancel()
            logger.info("TagMasterCache refresh timer stopped")
    
    def get_stats(self) -> dict:
        """Get cache statistics"""
        with self._lock:
            return {
                'cached_tags': len(self._cache),
                'last_refresh': self._last_refresh.isoformat() if self._last_refresh else None,
                'refresh_interval_seconds': self.refresh_interval
            }
