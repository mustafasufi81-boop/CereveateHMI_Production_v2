"""
Historical Data Service - Queries PostgreSQL TimescaleDB for historical trends
Reads from EXISTING historian_raw.historian_timeseries table
"""
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

def _to_utc_aware(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware UTC so PostgreSQL comparisons work correctly"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

class HistoricalDataService:
    """Query historical tag data from PostgreSQL TimescaleDB"""
    
    def __init__(self, db_config: Dict):
        """
        Args:
            db_config: Database connection config
                {host, port, database, user, password}
        """
        self.db_config = db_config
        self._connection = None

    @property
    def connection(self):
        """Always return a live connection, auto-reconnecting if needed.
        
        psycopg2 sets connection.closed to non-zero when the server drops
        the connection, so no SELECT 1 round-trip is required.
        """
        try:
            if self._connection is None or self._connection.closed:
                self.connect()
        except Exception:
            pass
        return self._connection

    @connection.setter
    def connection(self, value):
        self._connection = value

    def connect(self):
        """Establish database connection"""
        try:
            self._connection = psycopg2.connect(
                host=self.db_config['host'],
                port=self.db_config['port'],
                database=self.db_config['database'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                cursor_factory=RealDictCursor
            )
            with self._connection.cursor() as cursor:
                cursor.execute("SET TIME ZONE 'Asia/Kolkata'")
            logger.info(f"✅ Connected to PostgreSQL: {self.db_config['database']}")
            logger.info("🕒 PostgreSQL session timezone set to Asia/Kolkata")
            return True
            
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            return False
    
    def _ensure_connection(self):
        """Auto-connect / reconnect if needed (delegates to property)."""
        return self.connection is not None

    def disconnect(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()
            logger.info("✅ Database connection closed")
    
    def get_historical_trend(
        self, 
        tag_id: str, 
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        max_points: int = 1000
    ) -> List[Dict]:
        """
        OPTIMIZED: Get historical trend data for a tag with intelligent downsampling
        
        Args:
            tag_id: Tag identifier (e.g., "Random.Real4")
            start_time: Start of time range (default: 1 hour ago)
            end_time: End of time range (default: now)
            max_points: Maximum data points to return
            
        Returns:
            List of {timestamp, value, quality}
        """
        if not self._ensure_connection():
            logger.error("❌ No database connection")
            return []

        # Default time range: last 1 hour
        if not end_time:
            end_time = datetime.now(timezone.utc)
        if not start_time:
            start_time = end_time - timedelta(hours=1)
        end_time = _to_utc_aware(end_time)
        start_time = _to_utc_aware(start_time)

        try:
            with self.connection.cursor() as cursor:
                # PERFORMANCE: Calculate total data points first
                count_query = """
                    SELECT COUNT(*) as total
                    FROM historian_raw.historian_timeseries
                    WHERE tag_id = %s
                    AND time BETWEEN %s AND %s
                """
                cursor.execute(count_query, (tag_id, start_time, end_time))
                total_count = cursor.fetchone()['total']
                
                # Intelligent downsampling decision
                if total_count <= max_points:
                    # Return all data - no downsampling needed
                    query = """
                        SELECT 
                            time as timestamp,
                            value_num as value,
                            quality
                        FROM historian_raw.historian_timeseries
                        WHERE tag_id = %s
                        AND time BETWEEN %s AND %s
                        ORDER BY time ASC
                    """
                    cursor.execute(query, (tag_id, start_time, end_time))
                else:
                    # Downsample using epoch-bucket (standard PostgreSQL)
                    time_diff_seconds = max(1, int((end_time - start_time).total_seconds()))
                    interval_seconds = max(1, int(time_diff_seconds / max_points))

                    query = """
                        SELECT
                            MIN(time) AS timestamp,
                            AVG(value_num) AS value,
                            MAX(quality) AS quality
                        FROM historian_raw.historian_timeseries
                        WHERE tag_id = %s
                        AND time BETWEEN %s AND %s
                        GROUP BY (EXTRACT(EPOCH FROM time)::bigint / %s)
                        ORDER BY timestamp ASC
                    """
                    cursor.execute(query, (tag_id, start_time, end_time, interval_seconds))
                
                results = cursor.fetchall()
                
                logger.info(f"📊 Retrieved {len(results)}/{total_count} points for {tag_id} (downsampled: {total_count > max_points})")
                
                # Convert to JSON-friendly format
                return [
                    {
                        'timestamp': row['timestamp'].isoformat(),
                        'value': float(row['value']) if row['value'] is not None else None,
                        'quality': row['quality']
                    }
                    for row in results
                ]
                
        except Exception as e:
            logger.error(f"❌ Historical query failed: {e}")
            return []
    
    def get_multiple_trends(
        self,
        tag_ids: List[str],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        max_points: int = 1000,
        sampling_interval: Optional[int] = None  # NEW: Explicit sampling interval in seconds
    ) -> Dict[str, List[Dict]]:
        """
        OPTIMIZED: Get historical trends for multiple tags in SINGLE query
        Returns RAW data at exact user-selected sampling intervals
        
        Args:
            sampling_interval: Explicit interval in seconds (5, 10, 30, etc.)
                              If provided, returns ONLY data at exact intervals
                              If None, falls back to time_bucket downsampling
        
        Returns:
            Dict mapping tag_id -> trend data
        """
        if not self._ensure_connection():
            logger.error("❌ No database connection")
            return {}

        # Default time range: last 1 hour
        if not end_time:
            end_time = datetime.now(timezone.utc)
        if not start_time:
            start_time = end_time - timedelta(hours=1)
        end_time = _to_utc_aware(end_time)
        start_time = _to_utc_aware(start_time)

        if not tag_ids:
            return {}
        
        try:
            with self.connection.cursor() as cursor:
                # NEW BEHAVIOR: If sampling_interval provided, return RAW data at exact intervals
                if sampling_interval is not None:
                    logger.info(f"\U0001f4ca Using EXACT sampling: {sampling_interval}s intervals (raw data)")
                    query = """
                        SELECT DISTINCT ON (tag_id, (EXTRACT(EPOCH FROM time)::bigint / %s))
                            tag_id,
                            time as timestamp,
                            value_num as value,
                            quality
                        FROM historian_raw.historian_timeseries
                        WHERE tag_id = ANY(%s)
                        AND time BETWEEN %s AND %s
                        ORDER BY tag_id, (EXTRACT(EPOCH FROM time)::bigint / %s), time
                    """
                    cursor.execute(query, (sampling_interval, tag_ids, start_time, end_time, sampling_interval))
                    rows = cursor.fetchall()
                    
                else:
                    logger.info(f"\U0001f4ca Using epoch-bucket downsampling: {max_points} max points")
                    time_diff_seconds = max(1, int((end_time - start_time).total_seconds()))
                    interval_seconds = max(1, int(time_diff_seconds / max_points))
                    query = """
                        SELECT
                            tag_id,
                            MIN(time) AS timestamp,
                            AVG(value_num) AS value,
                            MAX(quality) AS quality
                        FROM historian_raw.historian_timeseries
                        WHERE tag_id = ANY(%s)
                        AND time BETWEEN %s AND %s
                        GROUP BY tag_id, (EXTRACT(EPOCH FROM time)::bigint / %s)
                        ORDER BY tag_id, timestamp
                    """
                    cursor.execute(query, (tag_ids, start_time, end_time, interval_seconds))
                    rows = cursor.fetchall()
                
                # Group results by tag_id
                results = {tag_id: [] for tag_id in tag_ids}
                
                for row in rows:
                    tag_id = row['tag_id']
                    if tag_id in results:
                        results[tag_id].append({
                            'timestamp': row['timestamp'].isoformat(),
                            'value': float(row['value']) if row['value'] is not None else None,
                            'quality': row['quality']
                        })
                
                total_points = sum(len(v) for v in results.values())
                logger.info(f"📊 Retrieved {total_points} historical points for {len(tag_ids)} tags (avg {total_points//max(1,len(tag_ids))} pts/tag)")
                
                return results
                
        except Exception as e:
            logger.error(f"❌ Optimized historical query failed: {e}")
            # Fallback to individual queries
            logger.info("⚠️ Falling back to individual queries...")
            results = {}
            for tag_id in tag_ids:
                results[tag_id] = self.get_historical_trend(
                    tag_id, start_time, end_time, max_points
                )
            return results
    
    def get_latest_value(self, tag_id: str) -> Optional[Dict]:
        """Get most recent value for a tag from database"""
        if not self.connection:
            return None
        
        try:
            with self.connection.cursor() as cursor:
                query = """
                    SELECT time as timestamp, value_num as value, quality
                    FROM historian_raw.historian_timeseries
                    WHERE tag_id = %s
                    ORDER BY time DESC
                    LIMIT 1
                """
                
                cursor.execute(query, (tag_id,))
                row = cursor.fetchone()
                
                if row:
                    return {
                        'timestamp': row['timestamp'].isoformat(),
                        'value': float(row['value']) if row['value'] is not None else None,
                        'quality': row['quality']
                    }
                
        except Exception as e:
            logger.error(f"❌ Latest value query failed: {e}")
        
        return None
    
    def get_tag_statistics(
        self,
        tag_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict:
        """Get statistical summary for a tag"""
        if not self.connection:
            return {}
        
        if not end_time:
            end_time = datetime.now()
        if not start_time:
            start_time = end_time - timedelta(hours=24)
        
        try:
            with self.connection.cursor() as cursor:
                query = """
                    SELECT 
                        COUNT(*) as count,
                        AVG(value_num) as avg,
                        MIN(value_num) as min,
                        MAX(value_num) as max,
                        STDDEV(value_num) as stddev
                    FROM historian_raw.historian_timeseries
                    WHERE tag_id = %s
                    AND time BETWEEN %s AND %s
                """
                
                cursor.execute(query, (tag_id, start_time, end_time))
                row = cursor.fetchone()
                
                if row:
                    return {
                        'count': row['count'],
                        'average': float(row['avg']) if row['avg'] else 0,
                        'min': float(row['min']) if row['min'] else 0,
                        'max': float(row['max']) if row['max'] else 0,
                        'stddev': float(row['stddev']) if row['stddev'] else 0
                    }
                
        except Exception as e:
            logger.error(f"❌ Statistics query failed: {e}")
        
        return {}
