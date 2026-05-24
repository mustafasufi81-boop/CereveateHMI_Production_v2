"""
MQTT HMI Flask Application - Real-Time MQTT Data Dashboard
Displays data received through MQTT and stored in PostgreSQL with source='MQT'
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Load configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'Historian_data',
    'user': 'postgres',
    'password': 'Database@19c'
}

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'mqtt-hmi-secret-key'
CORS(app)

@app.after_request
def add_header(response):
    """Add headers to prevent aggressive caching"""
    if request.path.endswith('.js') or request.path.endswith('.css'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

# Initialize Flask-SocketIO
socketio = SocketIO(
    app, 
    cors_allowed_origins="*",
    async_mode='eventlet',
    logger=True,
    engineio_logger=False
)

# Database connection pool
db_connection = None

def get_db_connection():
    """Get or create database connection"""
    global db_connection
    try:
        if db_connection is None or db_connection.closed:
            db_connection = psycopg2.connect(**DB_CONFIG)
            logger.info("✅ Connected to PostgreSQL database")
        return db_connection
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return None


@app.route('/')
def index():
    """Render main MQTT dashboard"""
    return render_template('mqtt_dashboard.html')


@app.route('/api/mqtt/tags')
def get_mqtt_tags():
    """
    Get list of all tags that have MQTT data (source='MQT')
    Returns unique tag IDs from historian_timeseries
    """
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database not connected'}), 503
        
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Get unique tag IDs with MQTT data from last 24 hours
            cursor.execute("""
                SELECT DISTINCT tag_id, 
                       COUNT(*) as sample_count,
                       MAX(time) as last_update
                FROM historian_raw.historian_timeseries
                WHERE time > NOW() - INTERVAL '24 hours'
                GROUP BY tag_id
                ORDER BY last_update DESC
            """)
            
            tags = cursor.fetchall()
            
            return jsonify({
                'timestamp': datetime.now().isoformat(),
                'count': len(tags),
                'tags': [dict(row) for row in tags]
            })
            
    except Exception as e:
        logger.error(f"❌ Failed to fetch MQTT tags: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/mqtt/latest')
def get_mqtt_latest():
    """
    Get latest values for all MQTT tags
    """
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database not connected'}), 503
        
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Get latest value for each MQTT tag
            cursor.execute("""
                SELECT DISTINCT ON (tag_id) 
                    tag_id,
                    time,
                    value_num,
                    value_bool,
                    value_text,
                    quality
                FROM historian_raw.historian_timeseries
                ORDER BY tag_id, time DESC
            """)
            
            rows = cursor.fetchall()
            tags = {}
            for row in rows:
                tags[row['tag_id']] = {
                    'value': row['value_num'] if row['value_num'] is not None else row['value_text'],
                    'quality': row['quality'],
                    'timestamp': row['time'].isoformat() if row['time'] else None
                }
            
            return jsonify({
                'timestamp': datetime.now().isoformat(),
                'count': len(tags),
                'tags': tags
            })
            
    except Exception as e:
        logger.error(f"❌ Failed to fetch latest MQTT values: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/mqtt/historical/<tag_id>')
def get_mqtt_historical(tag_id):
    """
    Get historical trend data for MQTT tag
    Query parameters:
        - start: ISO timestamp
        - end: ISO timestamp  
        - max_points: Maximum data points (default: 10000)
    """
    try:
        # Parse parameters
        start_str = request.args.get('start')
        end_str = request.args.get('end')
        max_points = int(request.args.get('max_points', 10000))
        
        # Parse timestamps
        if start_str and end_str:
            start_time = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
            end_time = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
        else:
            # Default: last 1 hour
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=1)
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database not connected'}), 503
        
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Count total records
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM historian_raw.historian_timeseries
                WHERE tag_id = %s
                AND time >= %s
                AND time <= %s
            """, (tag_id, start_time, end_time))
            
            total_count = cursor.fetchone()['total']
            
            if total_count <= max_points:
                # Return all data
                query = """
                    SELECT time, value_num, quality
                    FROM historian_raw.historian_timeseries
                    WHERE tag_id = %s
                    AND time >= %s
                    AND time <= %s
                    ORDER BY time
                """
                cursor.execute(query, (tag_id, start_time, end_time))
            else:
                # Sample data evenly
                sample_rate = max(1, total_count // max_points)
                query = """
                    WITH numbered AS (
                        SELECT time, value_num, quality,
                               ROW_NUMBER() OVER (ORDER BY time) as rn
                        FROM historian_raw.historian_timeseries
                        WHERE tag_id = %s
                        AND time >= %s
                        AND time <= %s
                    )
                    SELECT time, value_num, quality
                    FROM numbered
                    WHERE rn %% %s = 1
                    ORDER BY time
                """
                cursor.execute(query, (tag_id, start_time, end_time, sample_rate))
            
            rows = cursor.fetchall()
            
            data = [{
                'timestamp': row['time'].isoformat() if row['time'] else None,
                'value': float(row['value_num']) if row['value_num'] is not None else None,
                'quality': row['quality']
            } for row in rows]
            
            return jsonify({
                'tag_id': tag_id,
                'start': start_time.isoformat(),
                'end': end_time.isoformat(),
                'total_count': total_count,
                'returned_count': len(data),
                'data': data
            })
            
    except Exception as e:
        logger.error(f"❌ Failed to fetch historical MQTT data: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/mqtt/stats')
def get_mqtt_stats():
    """
    Get MQTT data statistics
    """
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database not connected'}), 503
        
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Get statistics
            cursor.execute("""
                SELECT 
                    COUNT(DISTINCT tag_id) as unique_tags,
                    COUNT(*) as total_samples,
                    MIN(time) as first_sample,
                    MAX(time) as last_sample
                FROM historian_raw.historian_timeseries
            """)
            
            stats = cursor.fetchone()
            
            return jsonify({
                'timestamp': datetime.now().isoformat(),
                'stats': dict(stats) if stats else {}
            })
            
    except Exception as e:
        logger.error(f"❌ Failed to fetch MQTT stats: {e}")
        return jsonify({'error': str(e)}), 500


# Background task to poll for new MQTT data and emit to clients
def mqtt_data_poller():
    """
    Poll database for new MQTT data and push to connected clients
    """
    logger.info("🚀 Starting MQTT data poller...")
    last_check = datetime.now()
    
    while True:
        try:
            eventlet.sleep(2)  # Poll every 2 seconds
            
            conn = get_db_connection()
            if not conn:
                continue
            
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Get data added since last check
                cursor.execute("""
                    SELECT DISTINCT ON (tag_id) 
                        tag_id,
                        time,
                        value_num,
                        quality
                    FROM historian_raw.historian_timeseries
                    WHERE time > %s
                    ORDER BY tag_id, time DESC
                """, (last_check,))
                
                rows = cursor.fetchall()
                
                if rows:
                    # Emit updates to all connected clients
                    updates = [{
                        'tag_id': row['tag_id'],
                        'value': float(row['value_num']) if row['value_num'] is not None else None,
                        'quality': row['quality'],
                        'timestamp': row['time'].isoformat() if row['time'] else None
                    } for row in rows]
                    
                    socketio.emit('mqtt_data_update', {
                        'timestamp': datetime.now().isoformat(),
                        'updates': updates
                    })
                    
                    logger.info(f"📤 Pushed {len(updates)} MQTT updates to clients")
                
                last_check = datetime.now()
                
        except Exception as e:
            logger.error(f"❌ Error in MQTT data poller: {e}")
            eventlet.sleep(5)


@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection"""
    logger.info(f"✅ Client connected: {request.sid}")
    emit('connection_status', {'status': 'connected', 'timestamp': datetime.now().isoformat()})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection"""
    logger.info(f"❌ Client disconnected: {request.sid}")


if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info(" MQTT HMI Dashboard Server")
    logger.info("=" * 60)
    logger.info("🚀 Starting Flask server...")
    logger.info("📊 Dashboard: http://localhost:5002")
    logger.info("🔌 WebSocket: ws://localhost:5002")
    logger.info("=" * 60)
    
    # Start background poller
    eventlet.spawn(mqtt_data_poller)
    
    # Run Flask-SocketIO server
    socketio.run(app, host='0.0.0.0', port=5002, debug=False)
