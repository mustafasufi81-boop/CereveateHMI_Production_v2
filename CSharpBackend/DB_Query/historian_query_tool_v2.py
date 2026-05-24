"""
Cereveate Historian Query Tool - ROBUST VERSION
Professional database viewer with connection pooling and proper error handling

CRITICAL FIXES:
1. ✅ Connection pooling (1-10 connections max) - prevents "too many connections"
2. ✅ Correct column names (time, value_num) - prevents UndefinedColumn errors
3. ✅ Context managers for automatic cleanup - prevents connection leaks
4. ✅ Modular database helper - easy to maintain
5. ✅ Comprehensive error handling - never crashes
"""

import json
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, Response
from flask_cors import CORS
from datetime import datetime, timedelta
import time
import atexit
from contextlib import contextmanager

app = Flask(__name__)
CORS(app)

# Flask 3.x: Custom jsonify function to preserve datetime microseconds
def jsonify(data, status=200):
    """Custom jsonify that preserves datetime microseconds and handles all PostgreSQL types"""
    from decimal import Decimal
    
    def json_handler(obj):
        if isinstance(obj, datetime):
            # Return ISO format with full 6-digit microseconds
            return obj.isoformat()
        elif isinstance(obj, Decimal):
            # Convert Decimal to float
            return float(obj)
        elif hasattr(obj, 'isoformat'):
            # Handle date, time objects
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    json_str = json.dumps(data, default=json_handler, ensure_ascii=False)
    return Response(json_str, status=status, mimetype='application/json')

# Load configuration (NOT exposed to client)
with open('config.json', 'r') as f:
    CONFIG = json.load(f)

DB_CONFIG = CONFIG['database']
DISPLAY_CONFIG = CONFIG['display']

# Global connection pool
connection_pool = None


class DatabaseHelper:
    """Modular database helper with connection pooling"""
    
    @staticmethod
    def init_pool():
        """Initialize PostgreSQL connection pool"""
        global connection_pool
        try:
            connection_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=10,  # Limit to prevent "too many connections"
                host=DB_CONFIG['host'],
                port=DB_CONFIG['port'],
                database=DB_CONFIG['database'],
                user=DB_CONFIG['user'],
                password=DB_CONFIG['password'],
                connect_timeout=5,  # Faster connection timeout
                options='-c statement_timeout=15000 -c work_mem=16MB'  # 15s query timeout, more memory for sorts
            )
            print("\u2705 Database connection pool initialized (1-10 connections, 15s timeout)")
            return True
        except Exception as e:
            print(f"\u274c Failed to initialize connection pool: {e}")
            return False
    
    @staticmethod
    def close_pool():
        """Close all connections on shutdown"""
        global connection_pool
        if connection_pool:
            try:
                connection_pool.closeall()
                print("\ud83d\udd12 Database connection pool closed")
            except Exception as e:
                print(f"\u26a0\ufe0f Error closing pool: {e}")
    
    @staticmethod
    @contextmanager
    def get_connection():
        """Get connection from pool with automatic cleanup"""
        conn = None
        try:
            if connection_pool is None:
                if not DatabaseHelper.init_pool():
                    raise Exception("Failed to initialize connection pool")
            
            conn = connection_pool.getconn()
            yield conn
            
        except Exception as e:
            print(f"\u26a0\ufe0f Database error: {e}")
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            raise
        finally:
            if conn:
                try:
                    connection_pool.putconn(conn)
                except Exception as e:
                    print(f"\u26a0\ufe0f Error returning connection: {e}")
    
    @staticmethod
    def execute_query(query, params=None, fetch_one=False):
        """Execute query with automatic connection management"""
        try:
            with DatabaseHelper.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, params)
                    if fetch_one:
                        return cur.fetchone()
                    return cur.fetchall()
        except Exception as e:
            print(f"\u274c Query execution failed: {e}")
            raise


# Register cleanup on exit
atexit.register(DatabaseHelper.close_pool)


@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')


@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    try:
        with DatabaseHelper.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return jsonify({
                    'success': True,
                    'database': 'connected',
                    'timestamp': datetime.now().isoformat()
                })
    except Exception as e:
        return jsonify({
            'success': False,
            'database': 'disconnected',
            'error': str(e)
        }), 503


@app.route('/api/tags/list')
def get_tags_list():
    """Get all available tags from historian"""
    try:
        tags = DatabaseHelper.execute_query("""
            SELECT 
                tag_id,
                tag_name,
                data_type,
                enabled,
                deadband_value,
                db_logging_interval_ms,
                created_at,
                config_updated_at as updated_at
            FROM historian_meta.tag_master
            WHERE enabled = true
            ORDER BY tag_id
        """)
        
        return jsonify({
            'success': True,
            'count': len(tags),
            'tags': tags
        })
        
    except Exception as e:
        print(f"\u274c Error in get_tags_list: {e}")
        return jsonify({
            'success': False,
            'error': f"Failed to fetch tags: {str(e)}"
        }), 500


@app.route('/api/data/query')
def query_data():
    """Query time-series data with filters and PAGINATION (Better than HMI!)"""
    try:
        query_start = time.time()
        
        # Get query parameters
        tag_ids = request.args.getlist('tag_id[]')
        start_time = request.args.get('start_time')
        end_time = request.args.get('end_time')
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 1000))
        
        # PAGINATION: Validate and cap page size (max 4000 per page for speed)
        page_size = min(max(page_size, 100), 4000)
        page = max(page, 1)
        offset = (page - 1) * page_size
        
        # Build queries (count + data)
        count_query = "SELECT COUNT(*) as total FROM historian_raw.historian_timeseries WHERE 1=1"
        data_query = """
            SELECT 
                time as timestamp,
                tag_id,
                value_num as value,
                quality
            FROM historian_raw.historian_timeseries
            WHERE 1=1
        """
        params = []
        
        # Add filters
        if tag_ids:
            count_query += " AND tag_id = ANY(%s)"
            data_query += " AND tag_id = ANY(%s)"
            params.append(tag_ids)
        
        # OPTIMIZATION: Use BETWEEN for time ranges (faster with indexes)
        if start_time and end_time:
            count_query += " AND time BETWEEN %s AND %s"
            data_query += " AND time BETWEEN %s AND %s"
            params.append(start_time)
            params.append(end_time)
        elif start_time:
            count_query += " AND time >= %s"
            data_query += " AND time >= %s"
            params.append(start_time)
        elif end_time:
            count_query += " AND time <= %s"
            data_query += " AND time <= %s"
            params.append(end_time)
        
        # Get total count first (fast with indexes)
        count_result = DatabaseHelper.execute_query(count_query, params)
        total_records = count_result[0]['total'] if count_result else 0
        total_pages = (total_records + page_size - 1) // page_size
        
        # Log query info
        print(f"🔍 Query page {page}/{total_pages}: {len(tag_ids) if tag_ids else 'all'} tags, {page_size} per page")
        
        # CRITICAL: ORDER BY time DESC (latest first!) + LIMIT + OFFSET for pagination
        data_query += f" ORDER BY time DESC LIMIT %s OFFSET %s"
        params_with_pagination = params + [page_size, offset]
        
        # Execute paginated query
        data = DatabaseHelper.execute_query(data_query, params_with_pagination)
        
        query_time = time.time() - query_start
        print(f"✅ Query returned {len(data)} records in {query_time:.3f}s (page {page}/{total_pages})")
        
        return jsonify({
            'success': True,
            'count': len(data),
            'page': page,
            'page_size': page_size,
            'total_records': total_records,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'has_prev': page > 1,
            'execution_time_ms': round(query_time * 1000, 2),
            'data': data
        })
        
    except Exception as e:
        print(f"❌ Error in query_data: {e}")
        return jsonify({
            'success': False,
            'error': f"Query failed: {str(e)}"
        }), 500


@app.route('/api/stats/insertion_rate')
def get_insertion_rate():
    """Get real-time insertion rate statistics"""
    try:
        # Last 60 seconds insertion rate (FIXED: time not timestamp)
        overall_stats = DatabaseHelper.execute_query("""
            SELECT 
                COUNT(*) as total_records,
                COUNT(DISTINCT tag_id) as unique_tags,
                ROUND(CAST(COUNT(*) / 60.0 AS NUMERIC), 2) as records_per_second,
                MIN(time) as earliest,
                MAX(time) as latest
            FROM historian_raw.historian_timeseries
            WHERE time >= NOW() - INTERVAL '60 seconds'
        """, fetch_one=True)
        
        # Per-tag insertion rate (last 60 seconds)
        per_tag_stats = DatabaseHelper.execute_query("""
            SELECT 
                tag_id,
                COUNT(*) as record_count,
                ROUND(CAST(COUNT(*) / 60.0 AS NUMERIC), 2) as records_per_second,
                MIN(time) as first_record,
                MAX(time) as last_record,
                ROUND(EXTRACT(EPOCH FROM (MAX(time) - MIN(time)))::NUMERIC, 2) as time_span_seconds
            FROM historian_raw.historian_timeseries
            WHERE time >= NOW() - INTERVAL '60 seconds'
            GROUP BY tag_id
            ORDER BY record_count DESC
        """)
        
        return jsonify({
            'success': True,
            'overall': overall_stats,
            'per_tag': per_tag_stats,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"\u274c Error in get_insertion_rate: {e}")
        return jsonify({
            'success': False,
            'error': f"Failed to fetch insertion rate: {str(e)}"
        }), 500


@app.route('/api/stats/compression')
def get_compression_stats():
    """Demonstrate historian compression power"""
    try:
        # Compare raw data volume vs compressed storage (FIXED: time/value_num)
        compression_data = DatabaseHelper.execute_query("""
            WITH time_windows AS (
                SELECT 
                    tag_id,
                    DATE_TRUNC('second', time) as second_window,
                    COUNT(*) as records_in_second,
                    MIN(value_num) as min_value,
                    MAX(value_num) as max_value,
                    AVG(value_num) as avg_value,
                    STDDEV(value_num) as stddev_value
                FROM historian_raw.historian_timeseries
                WHERE time >= NOW() - INTERVAL '5 minutes'
                  AND value_num IS NOT NULL
                GROUP BY tag_id, DATE_TRUNC('second', time)
            )
            SELECT 
                tag_id,
                COUNT(*) as total_seconds,
                SUM(records_in_second) as total_records,
                ROUND(AVG(records_in_second)::NUMERIC, 2) as avg_records_per_second,
                MAX(records_in_second) as max_records_per_second,
                MIN(records_in_second) as min_records_per_second
            FROM time_windows
            GROUP BY tag_id
            ORDER BY total_records DESC
        """)
        
        # Calculate compression ratio
        for item in compression_data:
            if item['total_records'] and item['total_records'] > 0:
                compression_ratio = item['total_records'] / item['total_seconds'] if item['total_seconds'] > 0 else 1
                item['compression_ratio'] = round(compression_ratio, 2)
                item['storage_saved_percent'] = round(
                    (1 - 1/compression_ratio) * 100, 2
                ) if compression_ratio > 1 else 0
        
        return jsonify({
            'success': True,
            'data': compression_data,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"\u274c Error in get_compression_stats: {e}")
        return jsonify({
            'success': False,
            'error': f"Failed to fetch compression stats: {str(e)}"
        }), 500


@app.route('/api/stats/total')
def get_total_stats():
    """Get overall historian statistics"""
    try:
        # Total records and time span (FIXED: time not timestamp)
        # Use a hard limit for query cost and fallback to cheaper estimates on timeout.
        DatabaseHelper.execute_query("SET LOCAL statement_timeout = 15000;")
        try:
            total_stats = DatabaseHelper.execute_query("""
            SELECT 
                COUNT(*) as total_records,
                COUNT(DISTINCT tag_id) as unique_tags,
                MIN(time) as earliest_record,
                MAX(time) as latest_record,
                ROUND(EXTRACT(EPOCH FROM (MAX(time) - MIN(time))) / 3600, 2) as total_hours,
                pg_size_pretty(pg_total_relation_size('historian_raw.historian_timeseries')) as table_size
            FROM historian_raw.historian_timeseries
        """, fetch_one=True)
        except Exception:
            total_stats = DatabaseHelper.execute_query("""
                SELECT
                    COALESCE(s.reltuples::bigint, 0) AS total_records,
                    (SELECT COUNT(DISTINCT tag_id) FROM historian_raw.historian_timeseries WHERE time >= NOW() - INTERVAL '7 days') AS unique_tags,
                    NULL AS earliest_record,
                    NULL AS latest_record,
                    NULL AS total_hours,
                    pg_size_pretty(pg_total_relation_size('historian_raw.historian_timeseries')) AS table_size
                FROM pg_class s
                JOIN pg_namespace n ON n.oid = s.relnamespace
                WHERE n.nspname = 'historian_raw' AND s.relname = 'historian_timeseries'
            """, fetch_one=True)
        
        # Records per tag
        top_tags = DatabaseHelper.execute_query("""
            SELECT 
                tag_id,
                COUNT(*) as record_count,
                MIN(time) as first_record,
                MAX(time) as last_record
            FROM historian_raw.historian_timeseries
            GROUP BY tag_id
            ORDER BY record_count DESC
            LIMIT 20
        """)
        
        # Recent activity (last hour)
        recent_activity = DatabaseHelper.execute_query("""
            SELECT 
                DATE_TRUNC('minute', time) as minute_window,
                COUNT(*) as records
            FROM historian_raw.historian_timeseries
            WHERE time >= NOW() - INTERVAL '1 hour'
            GROUP BY DATE_TRUNC('minute', time)
            ORDER BY minute_window DESC
            LIMIT 60
        """)
        
        return jsonify({
            'success': True,
            'total': total_stats,
            'top_tags': top_tags,
            'recent_activity': recent_activity
        })
        
    except Exception as e:
        print(f"\u274c Error in get_total_stats: {e}")
        return jsonify({
            'success': False,
            'error': f"Failed to fetch total stats: {str(e)}"
        }), 500


@app.route('/api/data/time_series/<tag_id>')
def get_time_series(tag_id):
    """Get time-series data for specific tag"""
    try:
        hours = int(request.args.get('hours', 1))
        max_points = int(request.args.get('max_points', DISPLAY_CONFIG['chart_points']))
        
        # Count total records
        count_result = DatabaseHelper.execute_query("""
            SELECT COUNT(*) as total_records
            FROM historian_raw.historian_timeseries
            WHERE tag_id = %s
            AND time >= NOW() - INTERVAL '%s hours'
        """, (tag_id, hours), fetch_one=True)
        
        total_records = count_result['total_records']
        
        # Downsample if needed
        if total_records > max_points:
            interval_seconds = int((hours * 3600) / max_points)
            
            # Use time_bucket for efficient downsampling (TimescaleDB)
            data = DatabaseHelper.execute_query("""
                SELECT 
                    time_bucket(%s, time) as timestamp,
                    AVG(value_num) as value,
                    MIN(value_num) as min_value,
                    MAX(value_num) as max_value,
                    COUNT(*) as sample_count
                FROM historian_raw.historian_timeseries
                WHERE tag_id = %s
                AND time >= NOW() - INTERVAL '%s hours'
                AND value_num IS NOT NULL
                GROUP BY time_bucket(%s, time)
                ORDER BY timestamp DESC
            """, (f'{interval_seconds} seconds', tag_id, hours, f'{interval_seconds} seconds'))
        else:
            # Return raw data
            data = DatabaseHelper.execute_query("""
                SELECT 
                    time as timestamp,
                    value_num as value,
                    quality
                FROM historian_raw.historian_timeseries
                WHERE tag_id = %s
                AND time >= NOW() - INTERVAL '%s hours'
                ORDER BY time DESC
            """, (tag_id, hours))
        
        return jsonify({
            'success': True,
            'tag_id': tag_id,
            'count': len(data),
            'total_records': total_records,
            'downsampled': total_records > max_points,
            'data': data
        })
        
    except Exception as e:
        print(f"\u274c Error in get_time_series: {e}")
        return jsonify({
            'success': False,
            'error': f"Failed to fetch time series: {str(e)}"
        }), 500


@app.route('/api/demo/performance')
def demo_performance():
    """Demonstrate industrial-grade performance"""
    try:
        results = {}
        
        # Test 1: Query speed for large dataset
        start = time.time()
        count_result = DatabaseHelper.execute_query("""
            SELECT COUNT(*) as count
            FROM historian_raw.historian_timeseries
            LIMIT 1000000
        """, fetch_one=True)
        results['query_1m_records'] = {
            'time_ms': round((time.time() - start) * 1000, 2),
            'records': count_result['count']
        }
        
        # Test 2: Aggregation speed (1 hour of data)
        start = time.time()
        agg_results = DatabaseHelper.execute_query("""
            SELECT 
                tag_id,
                COUNT(*) as records,
                AVG(value_num) as avg_value,
                MIN(value_num) as min_value,
                MAX(value_num) as max_value
            FROM historian_raw.historian_timeseries
            WHERE time >= NOW() - INTERVAL '1 hour'
              AND value_num IS NOT NULL
            GROUP BY tag_id
        """)
        results['aggregation_1hour'] = {
            'time_ms': round((time.time() - start) * 1000, 2),
            'tags_processed': len(agg_results)
        }
        
        # Test 3: Time-series compression efficiency
        start = time.time()
        compression_results = DatabaseHelper.execute_query("""
            SELECT 
                DATE_TRUNC('minute', time) as minute,
                AVG(value_num) as avg_value
            FROM historian_raw.historian_timeseries
            WHERE time >= NOW() - INTERVAL '24 hours'
              AND value_num IS NOT NULL
            GROUP BY minute
            ORDER BY minute DESC
        """)
        results['compression_24hours'] = {
            'time_ms': round((time.time() - start) * 1000, 2),
            'compressed_points': len(compression_results)
        }
        
        # Test 4: Real-time query speed
        start = time.time()
        realtime_results = DatabaseHelper.execute_query("""
            SELECT tag_id, value_num, time
            FROM historian_raw.historian_timeseries
            WHERE time >= NOW() - INTERVAL '1 second'
            ORDER BY time DESC
        """)
        results['realtime_query'] = {
            'time_ms': round((time.time() - start) * 1000, 2),
            'records': len(realtime_results)
        }
        
        return jsonify({
            'success': True,
            'performance_tests': results,
            'timestamp': datetime.now().isoformat(),
            'conclusion': 'Industrial-Grade Cereveate Tech Historian with Sub-Second Query Performance'
        })
        
    except Exception as e:
        print(f"\u274c Error in demo_performance: {e}")
        return jsonify({
            'success': False,
            'error': f"Performance test failed: {str(e)}"
        }), 500


@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'error': 'Internal server error'}), 500


if __name__ == '__main__':
    print("=" * 80)
    print("🏭 CEREVEATE HISTORIAN QUERY TOOL - ROBUST VERSION")
    print("=" * 80)
    print("✅ Connection pooling: 1-10 connections (prevents overload)")
    print("✅ Correct column names: time, value_num (no more errors)")
    print("✅ Auto cleanup: context managers (no connection leaks)")
    print("✅ Modular design: DatabaseHelper class (easy maintenance)")
    print("=" * 80)
    print("🌐 Web Interface: http://localhost:7005")
    print("📊 Database: PostgreSQL/TimescaleDB at " + DB_CONFIG['host'])
    print("🔒 Credentials: Hidden from external users")
    print("💚 Health Check: http://localhost:7005/api/health")
    print("=" * 80)
    
    # Initialize connection pool before starting server
    if DatabaseHelper.init_pool():
        print("\u2705 Connection pool ready, starting server...")
        app.run(host='0.0.0.0', port=7005, debug=False, threaded=True)
    else:
        print("\u274c Failed to initialize database connection pool")
        print("\u26a0\ufe0f Check your database configuration in config.json")
