"""
Comparison HMI Dashboard - API vs MQTT Data Quality & Latency Analysis
Compares data from OPC API (SignalR) and MQTT-stored data side-by-side
"""
import eventlet
eventlet.monkey_patch()

import json
import logging
import time
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'Historian_data',
    'user': 'postgres',
    'password': 'Database@19c'
}

OPC_API_URL = 'http://127.0.0.1:5001'

app = Flask(__name__)
app.config['SECRET_KEY'] = 'comparison-dashboard-key'
CORS(app)

@app.after_request
def add_header(response):
    if request.path.endswith('.js') or request.path.endswith('.css'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

db_connection = None

def get_db_connection():
    global db_connection
    try:
        if db_connection is None or db_connection.closed:
            db_connection = psycopg2.connect(**DB_CONFIG)
            logger.info("✅ Connected to PostgreSQL")
        return db_connection
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return None


@app.route('/')
def index():
    return render_template('comparison_dashboard.html')


@app.route('/api/comparison/tags')
def get_comparison_tags():
    """
    Get tags available in both API and Database for comparison
    """
    try:
        # Get tags from database
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database not connected'}), 503
        
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT DISTINCT ts.tag_id, tm.tag_name
                FROM historian_raw.historian_timeseries ts
                LEFT JOIN historian_meta.tag_master tm ON ts.tag_id = tm.tag_id
                ORDER BY ts.tag_id
                LIMIT 100
            """)
            
            db_tags_data = {row['tag_id']: row['tag_name'] or row['tag_id'] for row in cursor.fetchall()}
            db_tags = list(db_tags_data.keys())
        
        # Get tags from API (for reference, but we'll show all DB tags)
        try:
            api_response = requests.get(f'{OPC_API_URL}/api/opc/live', timeout=5)
            if api_response.status_code == 200:
                api_data = api_response.json()
                api_tags_list = api_data.get('tags', [])
                # Get ALL tag IDs from API
                api_tag_ids = [tag.get('tagId') for tag in api_tags_list if tag.get('tagId')]
                logger.info(f"✅ Fetched {len(api_tag_ids)} LIVE OPC tags from API, showing all {len(db_tags)} database tags")
            else:
                api_tag_ids = []
                logger.warning(f"⚠️ OPC API returned status {api_response.status_code}")
        except Exception as e:
            api_tag_ids = []
            logger.error(f"❌ Failed to fetch from OPC API: {e}")
        
        # Show ALL database tags (not just common ones)
        # Users can compare DB data even if tag is not currently in OPC
        common_tags = db_tags
        
        # Build response with tag names
        tags_with_names = [
            {
                "tag_id": tag_id,
                "tag_name": db_tags_data.get(tag_id, tag_id)
            }
            for tag_id in common_tags[:50]  # Limit to 50 for display
        ]
        
        return jsonify({
            'timestamp': datetime.now().isoformat(),
            'database_tags': len(db_tags),
            'api_tags': len(api_tag_ids),
            'common_tags': len(common_tags),
            'tags': tags_with_names
        })
        
    except Exception as e:
        logger.error(f"❌ Failed to fetch comparison tags: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/comparison/data/<tag_id>')
def get_comparison_data(tag_id):
    """
    Get data from both sources for comparison
    """
    try:
        result = {
            'tag_id': tag_id,
            'tag_name': tag_id,  # Default to tag_id
            'timestamp': datetime.now().isoformat(),
            'api': {},
            'database': {},
            'latency': {}
        }
        
        # Get tag name from database
        conn = get_db_connection()
        if conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT tag_name FROM historian_meta.tag_master WHERE tag_id = %s
                """, (tag_id,))
                tag_row = cursor.fetchone()
                if tag_row and tag_row['tag_name']:
                    result['tag_name'] = tag_row['tag_name']
        
        # Get data from API (Direct OPC Live Data)
        api_start = time.time()
        try:
            # Use the LIVE OPC endpoint for direct reads
            api_response = requests.get(f'{OPC_API_URL}/api/opc/live', timeout=5)
            api_latency = (time.time() - api_start) * 1000  # ms
            
            if api_response.status_code == 200:
                all_data = api_response.json()
                tags_list = all_data.get('tags', [])
                # Find matching tag
                tag_data = next((t for t in tags_list if t.get('tagId') == tag_id), None)
                
                if tag_data:
                    result['api'] = {
                        'value': tag_data.get('value'),
                        'quality': tag_data.get('quality'),
                        'timestamp': tag_data.get('timestamp'),
                        'latency_ms': round(api_latency, 2),
                        'status': 'success'
                    }
                else:
                    result['api'] = {'status': 'not_found', 'latency_ms': round(api_latency, 2)}
            else:
                result['api'] = {'status': 'error', 'latency_ms': round(api_latency, 2)}
        except Exception as e:
            result['api'] = {'status': 'error', 'error': str(e), 'latency_ms': -1}
        
        # Get data from Database
        db_start = time.time()
        try:
            conn = get_db_connection()
            if conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT time, value_num, quality
                        FROM historian_raw.historian_timeseries
                        WHERE tag_id = %s
                        ORDER BY time DESC
                        LIMIT 1
                    """, (tag_id,))
                    
                    row = cursor.fetchone()
                    db_latency = (time.time() - db_start) * 1000
                    
                    if row:
                        result['database'] = {
                            'value': float(row['value_num']) if row['value_num'] is not None else None,
                            'quality': row['quality'],
                            'timestamp': row['time'].isoformat() if row['time'] else None,
                            'latency_ms': round(db_latency, 2),
                            'status': 'success'
                        }
                    else:
                        result['database'] = {'status': 'no_data', 'latency_ms': round(db_latency, 2)}
            else:
                result['database'] = {'status': 'error', 'error': 'No connection'}
        except Exception as e:
            result['database'] = {'status': 'error', 'error': str(e)}
        
        # Calculate comparison metrics
        if result['api'].get('status') == 'success' and result['database'].get('status') == 'success':
            api_val = result['api'].get('value')
            db_val = result['database'].get('value')
            
            if api_val is not None and db_val is not None:
                result['latency'] = {
                    'api_latency': result['api']['latency_ms'],
                    'db_latency': result['database']['latency_ms'],
                    'value_difference': abs(float(api_val) - float(db_val)),
                    'values_match': abs(float(api_val) - float(db_val)) < 0.01
                }
                
                # Timestamp comparison
                if result['api'].get('timestamp') and result['database'].get('timestamp'):
                    api_ts = datetime.fromisoformat(result['api']['timestamp'].replace('Z', '+00:00'))
                    db_ts = datetime.fromisoformat(result['database']['timestamp'].replace('Z', '+00:00'))
                    result['latency']['timestamp_difference_ms'] = abs((api_ts - db_ts).total_seconds() * 1000)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Failed to fetch comparison data: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/comparison/historical/<tag_id>')
def get_comparison_historical(tag_id):
    """
    Get historical data from both sources with latency tracking
    """
    try:
        hours = int(request.args.get('hours', 1))
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        result = {
            'tag_id': tag_id,
            'tag_name': tag_id,  # Default
            'start': start_time.isoformat(),
            'end': end_time.isoformat(),
            'database_data': [],
            'latency_history': []
        }
        
        # Get historical data from database
        conn = get_db_connection()
        if conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Get tag name first
                cursor.execute("""
                    SELECT tag_name FROM historian_meta.tag_master WHERE tag_id = %s
                """, (tag_id,))
                tag_row = cursor.fetchone()
                if tag_row and tag_row['tag_name']:
                    result['tag_name'] = tag_row['tag_name']
                
                # Get historical data
                cursor.execute("""
                    SELECT time, value_num, quality
                    FROM historian_raw.historian_timeseries
                    WHERE tag_id = %s
                    AND time >= %s
                    AND time <= %s
                    ORDER BY time
                    LIMIT 1000
                """, (tag_id, start_time, end_time))
                
                rows = cursor.fetchall()
                result['database_data'] = [{
                    'timestamp': row['time'].isoformat() if row['time'] else None,
                    'value': float(row['value_num']) if row['value_num'] is not None else None,
                    'quality': row['quality']
                } for row in rows]
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Failed to fetch historical comparison: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/comparison/latency-stats')
def get_latency_stats():
    """
    Get overall latency statistics
    """
    try:
        stats = {
            'timestamp': datetime.now().isoformat(),
            'api_latency': {
                'current': 0,
                'avg': 0,
                'min': 0,
                'max': 0
            },
            'database_latency': {
                'current': 0,
                'avg': 0,
                'min': 0,
                'max': 0
            }
        }
        
        # Test API latency
        api_times = []
        for _ in range(5):
            start = time.time()
            try:
                requests.get(f'{OPC_API_URL}/api/opc/tags', timeout=2)
                api_times.append((time.time() - start) * 1000)
            except:
                pass
        
        if api_times:
            stats['api_latency'] = {
                'current': round(api_times[-1], 2),
                'avg': round(sum(api_times) / len(api_times), 2),
                'min': round(min(api_times), 2),
                'max': round(max(api_times), 2)
            }
        
        # Test database latency
        db_times = []
        conn = get_db_connection()
        if conn:
            for _ in range(5):
                start = time.time()
                try:
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT 1")
                        cursor.fetchone()
                    db_times.append((time.time() - start) * 1000)
                except:
                    pass
            
            if db_times:
                stats['database_latency'] = {
                    'current': round(db_times[-1], 2),
                    'avg': round(sum(db_times) / len(db_times), 2),
                    'min': round(min(db_times), 2),
                    'max': round(max(db_times), 2)
                }
        
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"❌ Failed to fetch latency stats: {e}")
        return jsonify({'error': str(e)}), 500


@socketio.on('connect')
def handle_connect():
    logger.info(f"✅ Client connected: {request.sid}")
    emit('connection_status', {'status': 'connected', 'timestamp': datetime.now().isoformat()})


@socketio.on('disconnect')
def handle_disconnect():
    logger.info(f"❌ Client disconnected: {request.sid}")


if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info(" API vs MQTT Comparison Dashboard")
    logger.info("=" * 60)
    logger.info("🚀 Starting Flask server...")
    logger.info("📊 Dashboard: http://localhost:5003")
    logger.info("=" * 60)
    
    socketio.run(app, host='0.0.0.0', port=5003, debug=False)
