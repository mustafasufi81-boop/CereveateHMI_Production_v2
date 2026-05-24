"""
History Loader Service - Loads historical data on-demand
Only loads data for tags that user is viewing
Keeps limited data in memory (1 day per tag maximum)
"""
import logging
import psycopg2
from datetime import datetime, timedelta
from collections import OrderedDict
import threading

logger = logging.getLogger(__name__)


class HistoryLoaderService:
    """
    On-demand historical data loader
    Keeps only 1 day of data per tag in memory
    LRU cache evicts least recently used tags
    """
    
    def __init__(self, db_config, max_tags_in_cache=50):
        self.db_config = db_config
        self.max_tags_in_cache = max_tags_in_cache
        self.cache = OrderedDict()  # LRU cache: tag_id -> list of (timestamp, value)
        self.lock = threading.Lock()
        
    def get_history(self, tag_id, hours=24):
        """
        Get historical data for a tag (last N hours)
        Loads from DB if not in cache
        
        Args:
            tag_id: Tag ID to load
            hours: Number of hours of history (max 24)
            
        Returns:
            List of (timestamp, value, quality) tuples
        """
        hours = min(hours, 24)  # Maximum 1 day
        
        with self.lock:
            # Check if in cache
            if tag_id in self.cache:
                # Move to end (most recently used)
                self.cache.move_to_end(tag_id)
                cached_data = self.cache[tag_id]
                
                # Check if cache is still valid (within time range)
                if cached_data and len(cached_data) > 0:
                    oldest_time = cached_data[0][0]
                    cutoff_time = datetime.now() - timedelta(hours=hours)
                    
                    if oldest_time <= cutoff_time:
                        # Cache is good, return filtered data
                        filtered = [d for d in cached_data if d[0] >= cutoff_time]
                        logger.debug(f"📊 Cache HIT for {tag_id}: {len(filtered)} points")
                        return filtered
            
            # Cache miss or invalid - load from database
            logger.info(f"📊 Loading history for {tag_id} (last {hours}h)")
            data = self._load_from_db(tag_id, hours)
            
            # Store in cache
            self.cache[tag_id] = data
            self.cache.move_to_end(tag_id)
            
            # Evict oldest if cache is full
            if len(self.cache) > self.max_tags_in_cache:
                evicted_tag = self.cache.popitem(last=False)
                logger.debug(f"🗑️ Evicted {evicted_tag[0]} from history cache")
                
            return data
            
    def _load_from_db(self, tag_id, hours):
        """Load historical data from database"""
        try:
            conn = psycopg2.connect(
                host=self.db_config['host'],
                port=self.db_config['port'],
                database=self.db_config['database'],
                user=self.db_config['user'],
                password=self.db_config['password']
            )
            
            cur = conn.cursor()
            
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            cur.execute("""
                SELECT time, value_num, quality
                FROM historian_raw.historian_timeseries
                WHERE tag_id = %s
                  AND time >= %s
                ORDER BY time ASC
            """, (tag_id, cutoff_time))
            
            rows = cur.fetchall()
            data = [(row[0], row[1], row[2]) for row in rows]
            
            cur.close()
            conn.close()
            
            logger.info(f"✅ Loaded {len(data)} historical points for {tag_id}")
            return data
            
        except Exception as e:
            logger.error(f"❌ Failed to load history for {tag_id}: {e}")
            return []
            
    def clear_cache(self):
        """Clear all cached historical data"""
        with self.lock:
            self.cache.clear()
            logger.info("🗑️ History cache cleared")
            
    def get_cache_stats(self):
        """Get cache statistics"""
        with self.lock:
            return {
                'cached_tags': len(self.cache),
                'max_tags': self.max_tags_in_cache,
                'tags': list(self.cache.keys())
            }
