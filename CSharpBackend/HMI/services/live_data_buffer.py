"""
Live Data Buffer - Keeps latest values for all subscribed tags
Memory efficient - only stores last value per tag
"""
import logging
import threading
from datetime import datetime

logger = logging.getLogger(__name__)


class LiveDataBuffer:
    """
    Stores the latest value for each tag
    Thread-safe for concurrent access
    """
    
    def __init__(self):
        self.data = {}  # tag_id -> {value, quality, timestamp}
        self.lock = threading.Lock()
        
    def update(self, tag_id, value, quality, timestamp=None):
        """
        Update tag value
        
        Args:
            tag_id: Tag ID
            value: Tag value
            quality: Quality code (e.g., 'GOOD', 'BAD')
            timestamp: Timestamp (defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.now()
            
        with self.lock:
            self.data[tag_id] = {
                'value': value,
                'quality': quality,
                'timestamp': timestamp
            }
            
    def update_batch(self, tags_data):
        """
        Update multiple tags at once
        
        Args:
            tags_data: List of dicts with {tagId, value, quality, timestamp}
        """
        timestamp = datetime.now()
        
        with self.lock:
            for tag in tags_data:
                tag_id = tag.get('tagId')
                if tag_id:
                    self.data[tag_id] = {
                        'value': tag.get('value'),
                        'quality': tag.get('quality', 'GOOD'),
                        'timestamp': tag.get('timestamp', timestamp)
                    }
                    
    def get(self, tag_id):
        """Get latest value for a tag"""
        with self.lock:
            return self.data.get(tag_id)
            
    def get_all(self):
        """Get all latest values (copy)"""
        with self.lock:
            return self.data.copy()
            
    def get_stats(self):
        """Get buffer statistics"""
        with self.lock:
            return {
                'total_tags': len(self.data),
                'memory_kb': len(str(self.data)) / 1024
            }
