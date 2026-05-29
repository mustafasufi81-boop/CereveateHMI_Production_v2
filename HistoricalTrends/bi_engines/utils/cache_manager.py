"""
Result caching system for expensive BI calculations
Uses checksum-based invalidation
"""

import hashlib
import json
import pickle
from datetime import datetime, timedelta
from typing import Any, Optional, Dict
import logging

logger = logging.getLogger(__name__)


class CacheManager:
    """
    In-memory cache with TTL and checksum-based invalidation
    """
    
    def __init__(self, ttl_seconds: int = 3600, max_size: int = 1000):
        """
        Initialize cache manager
        
        Args:
            ttl_seconds: Time to live for cached items
            max_size: Maximum number of cached items
        """
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self.cache = {}
        self.access_times = {}
        
        logger.info(f"Cache initialized: TTL={ttl_seconds}s, max_size={max_size}")
    
    def _generate_key(self, operation: str, **kwargs) -> str:
        """
        Generate cache key from operation and parameters
        
        Args:
            operation: Operation name
            **kwargs: Operation parameters
            
        Returns:
            Cache key string
        """
        # Sort kwargs for consistent key generation
        sorted_params = json.dumps(kwargs, sort_keys=True)
        key_string = f"{operation}:{sorted_params}"
        
        # Hash for shorter keys
        key_hash = hashlib.md5(key_string.encode()).hexdigest()
        
        return key_hash
    
    def get(self, operation: str, **kwargs) -> Optional[Any]:
        """
        Get cached result if available and not expired
        
        Args:
            operation: Operation name
            **kwargs: Operation parameters
            
        Returns:
            Cached result or None if not found/expired
        """
        key = self._generate_key(operation, **kwargs)
        
        if key not in self.cache:
            return None
        
        cached_item = self.cache[key]
        
        # Check expiration
        if datetime.now() > cached_item['expires_at']:
            logger.debug(f"Cache expired for {operation}")
            del self.cache[key]
            del self.access_times[key]
            return None
        
        # Update access time
        self.access_times[key] = datetime.now()
        
        logger.debug(f"✓ Cache hit for {operation}")
        return cached_item['result']
    
    def set(self, operation: str, result: Any, **kwargs):
        """
        Cache a result
        
        Args:
            operation: Operation name
            result: Result to cache
            **kwargs: Operation parameters
        """
        key = self._generate_key(operation, **kwargs)
        
        # Evict oldest if at max size
        if len(self.cache) >= self.max_size:
            self._evict_oldest()
        
        self.cache[key] = {
            'result': result,
            'created_at': datetime.now(),
            'expires_at': datetime.now() + timedelta(seconds=self.ttl_seconds)
        }
        
        self.access_times[key] = datetime.now()
        
        logger.debug(f"Cached result for {operation}")
    
    def invalidate(self, operation: str = None, **kwargs):
        """
        Invalidate cache entries
        
        Args:
            operation: If specified, only invalidate this operation
            **kwargs: If specified, only invalidate exact match
        """
        if operation and kwargs:
            # Invalidate specific entry
            key = self._generate_key(operation, **kwargs)
            if key in self.cache:
                del self.cache[key]
                del self.access_times[key]
                logger.info(f"Invalidated cache for {operation}")
        elif operation:
            # Invalidate all entries for operation (requires prefix matching)
            keys_to_delete = [
                k for k in self.cache.keys()
                if self.cache[k].get('operation') == operation
            ]
            for key in keys_to_delete:
                del self.cache[key]
                del self.access_times[key]
            logger.info(f"Invalidated {len(keys_to_delete)} entries for {operation}")
        else:
            # Clear all
            self.cache.clear()
            self.access_times.clear()
            logger.info("Cache cleared")
    
    def _evict_oldest(self):
        """Evict least recently accessed item"""
        if not self.access_times:
            return
        
        oldest_key = min(self.access_times.items(), key=lambda x: x[1])[0]
        
        del self.cache[oldest_key]
        del self.access_times[oldest_key]
        
        logger.debug("Evicted oldest cache entry")
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        total_items = len(self.cache)
        
        expired_count = sum(
            1 for item in self.cache.values()
            if datetime.now() > item['expires_at']
        )
        
        return {
            'total_items': total_items,
            'expired_items': expired_count,
            'active_items': total_items - expired_count,
            'max_size': self.max_size,
            'utilization': f"{(total_items / self.max_size * 100):.1f}%"
        }


# Global cache instance
_global_cache = None


def get_cache(ttl_seconds: int = 3600, max_size: int = 1000) -> CacheManager:
    """
    Get global cache instance
    
    Args:
        ttl_seconds: TTL for new instance
        max_size: Max size for new instance
        
    Returns:
        CacheManager instance
    """
    global _global_cache
    
    if _global_cache is None:
        _global_cache = CacheManager(ttl_seconds, max_size)
    
    return _global_cache
