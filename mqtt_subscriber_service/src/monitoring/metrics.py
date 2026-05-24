"""
Metrics Collection Module
Tracks service performance metrics
"""

import threading
from datetime import datetime
from typing import Dict, Any
from src.monitoring.logger import get_logger

logger = get_logger(__name__)


class MetricsCollector:
    """Collects and tracks service metrics"""
    
    def __init__(self):
        """Initialize Metrics Collector"""
        self._lock = threading.Lock()
        self._metrics = {
            'messages': {
                'received': 0,
                'processed': 0,
                'failed': 0,
                'validation_errors': 0
            },
            'processing': {
                'total_time_ms': 0.0,
                'avg_time_ms': 0.0,
                'min_time_ms': float('inf'),
                'max_time_ms': 0.0
            },
            'database': {
                'inserts': 0,
                'insert_errors': 0,
                'total_records': 0
            },
            'audit': {
                'audit_records': 0,
                'audit_errors': 0
            },
            'cache': {
                'topic_cache_hits': 0,
                'topic_cache_misses': 0,
                'tag_cache_hits': 0,
                'tag_cache_misses': 0
            }
        }
        
        self._start_time = datetime.utcnow()
        
        logger.info("MetricsCollector initialized")
    
    def record_message_received(self):
        """Record message received"""
        with self._lock:
            self._metrics['messages']['received'] += 1
    
    def record_message_processed(self, processing_time_ms: float, success: bool):
        """
        Record message processing result
        
        Args:
            processing_time_ms: Processing time in milliseconds
            success: Whether processing was successful
        """
        with self._lock:
            if success:
                self._metrics['messages']['processed'] += 1
            else:
                self._metrics['messages']['failed'] += 1
            
            # Update processing time metrics
            proc = self._metrics['processing']
            proc['total_time_ms'] += processing_time_ms
            proc['min_time_ms'] = min(proc['min_time_ms'], processing_time_ms)
            proc['max_time_ms'] = max(proc['max_time_ms'], processing_time_ms)
            
            total_processed = self._metrics['messages']['processed'] + self._metrics['messages']['failed']
            if total_processed > 0:
                proc['avg_time_ms'] = proc['total_time_ms'] / total_processed
    
    def record_validation_error(self):
        """Record validation error"""
        with self._lock:
            self._metrics['messages']['validation_errors'] += 1
    
    def record_database_insert(self, records_count: int, success: bool):
        """
        Record database insert operation
        
        Args:
            records_count: Number of records inserted
            success: Whether insert was successful
        """
        with self._lock:
            if success:
                self._metrics['database']['inserts'] += 1
                self._metrics['database']['total_records'] += records_count
            else:
                self._metrics['database']['insert_errors'] += 1
    
    def record_audit_operation(self, success: bool):
        """
        Record audit operation
        
        Args:
            success: Whether audit operation was successful
        """
        with self._lock:
            if success:
                self._metrics['audit']['audit_records'] += 1
            else:
                self._metrics['audit']['audit_errors'] += 1
    
    def record_cache_hit(self, cache_type: str):
        """
        Record cache hit
        
        Args:
            cache_type: Type of cache ('topic' or 'tag')
        """
        with self._lock:
            if cache_type == 'topic':
                self._metrics['cache']['topic_cache_hits'] += 1
            elif cache_type == 'tag':
                self._metrics['cache']['tag_cache_hits'] += 1
    
    def record_cache_miss(self, cache_type: str):
        """
        Record cache miss
        
        Args:
            cache_type: Type of cache ('topic' or 'tag')
        """
        with self._lock:
            if cache_type == 'topic':
                self._metrics['cache']['topic_cache_misses'] += 1
            elif cache_type == 'tag':
                self._metrics['cache']['tag_cache_misses'] += 1
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get all metrics
        
        Returns:
            Metrics dictionary
        """
        with self._lock:
            uptime = (datetime.utcnow() - self._start_time).total_seconds()
            
            # Calculate rates
            messages_per_second = self._metrics['messages']['received'] / uptime if uptime > 0 else 0
            success_rate = 0
            total_messages = self._metrics['messages']['processed'] + self._metrics['messages']['failed']
            if total_messages > 0:
                success_rate = (self._metrics['messages']['processed'] / total_messages) * 100
            
            # Calculate cache hit rates
            topic_total = (self._metrics['cache']['topic_cache_hits'] + 
                          self._metrics['cache']['topic_cache_misses'])
            topic_hit_rate = 0
            if topic_total > 0:
                topic_hit_rate = (self._metrics['cache']['topic_cache_hits'] / topic_total) * 100
            
            tag_total = (self._metrics['cache']['tag_cache_hits'] + 
                        self._metrics['cache']['tag_cache_misses'])
            tag_hit_rate = 0
            if tag_total > 0:
                tag_hit_rate = (self._metrics['cache']['tag_cache_hits'] / tag_total) * 100
            
            return {
                'timestamp': datetime.utcnow().isoformat(),
                'uptime_seconds': uptime,
                'metrics': {
                    **self._metrics,
                    'rates': {
                        'messages_per_second': round(messages_per_second, 2),
                        'success_rate_percent': round(success_rate, 2),
                        'topic_cache_hit_rate_percent': round(topic_hit_rate, 2),
                        'tag_cache_hit_rate_percent': round(tag_hit_rate, 2)
                    }
                }
            }
    
    def reset_metrics(self):
        """Reset all metrics to zero"""
        with self._lock:
            self._metrics = {
                'messages': {
                    'received': 0,
                    'processed': 0,
                    'failed': 0,
                    'validation_errors': 0
                },
                'processing': {
                    'total_time_ms': 0.0,
                    'avg_time_ms': 0.0,
                    'min_time_ms': float('inf'),
                    'max_time_ms': 0.0
                },
                'database': {
                    'inserts': 0,
                    'insert_errors': 0,
                    'total_records': 0
                },
                'audit': {
                    'audit_records': 0,
                    'audit_errors': 0
                },
                'cache': {
                    'topic_cache_hits': 0,
                    'topic_cache_misses': 0,
                    'tag_cache_hits': 0,
                    'tag_cache_misses': 0
                }
            }
            
            self._start_time = datetime.utcnow()
            logger.info("Metrics reset")
    
    def get_summary(self) -> str:
        """
        Get formatted metrics summary
        
        Returns:
            Formatted string summary
        """
        metrics = self.get_metrics()
        m = metrics['metrics']
        
        summary = f"""
=== MQTT Subscriber Service Metrics ===
Uptime: {metrics['uptime_seconds']:.0f} seconds

Messages:
  - Received: {m['messages']['received']}
  - Processed: {m['messages']['processed']}
  - Failed: {m['messages']['failed']}
  - Validation Errors: {m['messages']['validation_errors']}
  - Rate: {m['rates']['messages_per_second']:.2f} msg/s
  - Success Rate: {m['rates']['success_rate_percent']:.2f}%

Processing:
  - Avg Time: {m['processing']['avg_time_ms']:.2f} ms
  - Min Time: {m['processing']['min_time_ms']:.2f} ms
  - Max Time: {m['processing']['max_time_ms']:.2f} ms

Database:
  - Inserts: {m['database']['inserts']}
  - Insert Errors: {m['database']['insert_errors']}
  - Total Records: {m['database']['total_records']}

Cache:
  - Topic Hit Rate: {m['rates']['topic_cache_hit_rate_percent']:.2f}%
  - Tag Hit Rate: {m['rates']['tag_cache_hit_rate_percent']:.2f}%
"""
        return summary
