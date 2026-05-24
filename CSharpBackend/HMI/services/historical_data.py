"""
Historical Data Service - Queries PostgreSQL TimescaleDB for historical trends
FIXED VERSION: Uses small connection pool for better performance
Prevents "too many clients" while allowing parallel queries
"""
import logging
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class HistoricalDataService:
    """
    FIXED: Uses small connection pool (3 connections) for better performance.
    
    Key improvements:
    - No global lock bottleneck
    - Parallel queries allowed
    - Still prevents "too many clients"
    - Industry-standard approach
    """
    
    def __init__(self, db_config: Dict):
        self.db_config = db_config
        self._pool = None
        self._connected = False
        
    def _create_pool(self):
        """Create connection pool with timeout and performance settings"""
        try:
            pool = ThreadedConnectionPool(
                minconn=1,
                maxconn=10,  # Increased from 3 to 10 - prevents "too many clients" but allows more concurrent usage
                host=self.db_config['host'],
                port=self.db_config['port'],
                database=self.db_config['database'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                options="-c statement_timeout=10s"  # Prevent hanging queries
            )
            return pool
        except Exception as e:
            logger.error(f"❌ DB pool creation failed: {e}")
            return None
    
    def connect(self) -> bool:
        """Initialize connection pool"""
        if self._pool is None:
            self._pool = self._create_pool()
            if self._pool:
                self._connected = True
                logger.info(f"✅ Connected to PostgreSQL: {self.db_config['database']} (pool: 1-10 connections)")
                return True
        return self._connected
    
    def is_connected(self) -> bool:
        """Check if pool is available"""
        return self._connected and self._pool is not None
    
    def disconnect(self):
        """Close connection pool"""
        if self._pool:
            try:
                self._pool.closeall()
            except:
                pass
            self._pool = None
        self._connected = False
        logger.info("✅ Database pool closed")
    
    def _get_connection(self):
        """Get connection from pool - returns context manager for proper cleanup"""
        if not self._pool:
            raise Exception("Pool not initialized")
        
        class ConnectionContext:
            def __init__(ctx_self, pool):
                ctx_self.pool = pool
                ctx_self.conn = None
            
            def __enter__(ctx_self):
                try:
                    ctx_self.conn = ctx_self.pool.getconn()
                    return ctx_self.conn
                except Exception as e:
                    logger.error(f"❌ Failed to get connection from pool: {e}")
                    raise
            
            def __exit__(ctx_self, exc_type, exc_val, exc_tb):
                if ctx_self.conn:
                    try:
                        ctx_self.pool.putconn(ctx_self.conn)
                    except Exception as e:
                        logger.error(f"❌ Failed to return connection to pool: {e}")
                return False
        
        return ConnectionContext(self._pool)
    
    def _return_connection(self, conn):
        """Return connection to pool"""
        if self._pool:
            self._pool.putconn(conn)
    
    def get_historical_trend(
        self, 
        tag_id: str, 
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        max_points: int = 1000
    ) -> List[Dict]:
        """
        FIXED: Get historical trend without expensive COUNT(*)
        """
        if not end_time:
            end_time = datetime.now()
        if not start_time:
            start_time = end_time - timedelta(hours=1)
        
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    # Always use downsampling - no COUNT(*) needed
                    interval_seconds = max(1, int((end_time - start_time).total_seconds() / max_points))
                    interval = f"{interval_seconds} seconds"
                    cursor.execute("""
                        SELECT 
                            time_bucket(%s::interval, time) AS timestamp,
                            AVG(value_num) as value,
                            MAX(quality) as quality
                        FROM historian_raw.historian_timeseries
                        WHERE tag_id = %s AND time >= %s AND time <= %s
                        GROUP BY time_bucket(%s::interval, time)
                        ORDER BY timestamp ASC
                    """, (interval, tag_id, start_time, end_time, interval))
                    
                    results = cursor.fetchall()
                    logger.info(f"📊 Retrieved {len(results)} points for {tag_id}")
                    
                    return [
                        {
                            'timestamp': row['timestamp'].isoformat(),
                            'value': float(row['value']) if row['value'] is not None else None,
                            'quality': row['quality']
                        }
                        for row in results
                    ]
                    
        except Exception as e:
            logger.error(f"❌ Historical query failed for {tag_id}: {e}")
            return []
    
    def get_multiple_trends(
        self,
        tag_ids: List[str],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        max_points: int = 1000,
        sampling_interval: Optional[int] = None
    ) -> Dict[str, List[Dict]]:
        """
        Get historical trends for multiple tags - SIMPLE AND EFFICIENT.
        """
        if not tag_ids:
            return {}
        
        if not end_time:
            # Use timezone-aware datetime - data in DB has +05:30 timezone
            end_time = datetime.now(timezone.utc)
        if not start_time:
            start_time = end_time - timedelta(hours=1)
        
        # Calculate sampling interval if not provided
        if sampling_interval is None:
            total_seconds = (end_time - start_time).total_seconds()
            sampling_interval = max(1, int(total_seconds / max_points))
        
        interval_str = f"{sampling_interval} seconds"
        logger.info(f"📊 Querying {len(tag_ids)} tags: {start_time} to {end_time}, {sampling_interval}s interval")
        
        try:
            # Use direct connection - simplest approach
            conn = self._pool.getconn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    # Simple query without time_bucket first - test basic connection
                    cursor.execute("""
                        SELECT COUNT(*) as count
                        FROM historian_raw.historian_timeseries
                        WHERE tag_id = ANY(%s) 
                          AND time >= %s 
                          AND time <= %s
                    """, (tag_ids, start_time, end_time))
                    
                    count_result = cursor.fetchone()
                    logger.info(f"🔍 Basic count check: {count_result['count']} rows found")
                    
                    if count_result['count'] == 0:
                        logger.warning(f"⚠️ No data in time range - trying without time filter")
                        cursor.execute("SELECT COUNT(*) as count FROM historian_raw.historian_timeseries WHERE tag_id = ANY(%s)", (tag_ids,))
                        total_result = cursor.fetchone()
                        logger.info(f"🔍 Total count for tags: {total_result['count']}")
                        return {tag_id: [] for tag_id in tag_ids}
                    
                    # Now run the time_bucket query
                    cursor.execute("""
                        SELECT 
                            tag_id,
                            time_bucket(%s::interval, time) AS timestamp,
                            AVG(value_num) as value,
                            MAX(quality) as quality
                        FROM historian_raw.historian_timeseries
                        WHERE tag_id = ANY(%s) 
                          AND time >= %s 
                          AND time <= %s
                        GROUP BY tag_id, time_bucket(%s::interval, time)
                        ORDER BY tag_id, timestamp
                    """, (interval_str, tag_ids, start_time, end_time, interval_str))
                    
                    rows = cursor.fetchall()
                    logger.info(f"✅ Time bucket query returned {len(rows)} rows")
                    
                    # Group by tag_id
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
                    logger.info(f"✅ Retrieved {total_points} points for {len(tag_ids)} tags")
                    
                    return results
                    
            finally:
                self._pool.putconn(conn)
                    
        except Exception as e:
            logger.error(f"❌ Multi-trend query failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {tag_id: [] for tag_id in tag_ids}
    
    def get_latest_value(self, tag_id: str) -> Optional[Dict]:
        """Get most recent value for a tag. Thread-safe with pool."""
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT time as timestamp, value_num as value, quality
                        FROM historian_raw.historian_timeseries
                        WHERE tag_id = %s
                        ORDER BY time DESC LIMIT 1
                    """, (tag_id,))
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
        """Get statistical summary for a tag. Thread-safe."""
        if not end_time:
            end_time = datetime.now()
        if not start_time:
            start_time = end_time - timedelta(hours=24)
        
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT 
                        COUNT(*) as count,
                        AVG(value_num) as avg,
                        MIN(value_num) as min,
                        MAX(value_num) as max,
                        STDDEV(value_num) as stddev
                    FROM historian_raw.historian_timeseries
                    WHERE tag_id = %s AND time BETWEEN %s AND %s
                """, (tag_id, start_time, end_time))
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
    
    def ensure_connection(self) -> bool:
        """Legacy compatibility - ensures pool is initialized"""
        return self.connect()
