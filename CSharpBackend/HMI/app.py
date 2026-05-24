"""
HMI Flask Application - High-Performance Real-Time + Historical Trends
Connects to EXISTING C# SignalR hub - NO CHANGES to C# services required
"""
# CRITICAL: Patch eventlet FIRST before ANY other imports
import eventlet
eventlet.monkey_patch()

import json
import logging
import time
import requests
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS

# Import our services
from services.signalr_listener import SignalRListener
from services.historical_data import HistoricalDataService
from services.tag_cache import TagCacheService
from services.live_data_buffer import LiveDataBuffer
from services.alarm_service import AlarmService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Load configuration
with open('config.json', 'r') as f:
    config = json.load(f)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'hmi-secret-key-change-in-production'
CORS(app)

# Add no-cache headers for static files during development
@app.after_request
def add_header(response):
    """Add headers to prevent aggressive caching"""
    if request.path.endswith('.js') or request.path.endswith('.css'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

# Initialize Flask-SocketIO for real-time browser updates
socketio = SocketIO(
    app, 
    cors_allowed_origins="*",
    async_mode='eventlet',
    logger=True,
    engineio_logger=False
)

# Initialize services
historical_service = HistoricalDataService(config['database'])
tag_cache = TagCacheService(config['database'])
live_buffer = LiveDataBuffer()
alarm_service = None  # Initialize after historical_service is ready
signalr_listener = None

# In-memory cache for latest tag values (performance optimization)
latest_tag_values = {}
connected_clients = set()


def on_signalr_tag_update(tags_data):
    """
    Callback when SignalR receives BATCHED tag updates from listener
    SignalR listener buffers individual tags and sends in batches (200ms window)
    
    PERFORMANCE: Processes 60+ tags per batch instead of 60+ individual callbacks
    """
    global latest_tag_values
    
    try:
        if not isinstance(tags_data, list):
            logger.warning(f"⚠️  Expected list, got {type(tags_data)}")
            return
        
        if len(tags_data) == 0:
            return
        
        # Update cache efficiently (single pass)
        updated_count = 0
        for tag in tags_data:
            if isinstance(tag, dict):
                tag_id = tag.get('itemID') or tag.get('itemId')
                if tag_id:
                    latest_tag_values[tag_id] = {
                        'value': tag.get('value'),
                        'quality': tag.get('quality'),
                        'timestamp': tag.get('timestamp') or datetime.now().isoformat()
                    }
                    updated_count += 1
        
        # Single batch broadcast to all browsers (efficient!)
        socketio.emit('tag_update', tags_data, namespace='/')
        
        # Log batch statistics every 5 seconds to reduce overhead
        current_time = time.time()
        if not hasattr(on_signalr_tag_update, 'last_log_time'):
            on_signalr_tag_update.last_log_time = 0
        
        if current_time - on_signalr_tag_update.last_log_time >= 5:
            logger.info(
                f"📡 ✅ Batch: {updated_count} tags/batch, {len(connected_clients)} clients | "
                f"Cache: {len(latest_tag_values)} tags"
            )
            on_signalr_tag_update.last_log_time = current_time
        
    except Exception as e:
        logger.error(f"❌ Error in batch update: {e}", exc_info=True)


@app.route('/')
def index():
    """Main HMI dashboard"""
    import time
    from flask import make_response
    response = make_response(render_template('dashboard.html', timestamp=int(time.time())))
    # Force no-cache to prevent stale JavaScript
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/realtime')
def realtime_trends():
    """Real-time trends with millisecond polling"""
    from flask import make_response
    response = make_response(render_template('realtime_trends.html'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/simple-live')
def simple_live():
    """Simple live OPC data viewer"""
    from flask import make_response
    response = make_response(render_template('simple_live.html'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/test_simple.html')
def test_simple():
    """Simple OPC polling test page"""
    from flask import make_response
    response = make_response(render_template('test_simple.html'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/plc-dashboard')
def plc_dashboard():
    """PLC Gateway Dashboard - MQTT primary with REST API failover"""
    import time
    from flask import make_response
    response = make_response(render_template('plc_dashboard.html', timestamp=int(time.time())))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/alarm-dashboard')
def alarm_dashboard():
    """Alarm Dashboard - Motor Health Monitoring with Acknowledgment"""
    import time
    from flask import make_response
    response = make_response(render_template('alarm_dashboard.html', timestamp=int(time.time())))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/report')
def industrial_report():
    """Standalone Industrial Plant Report builder (localStorage/quick dev)."""
    from flask import make_response
    response = make_response(render_template('industrial_report_template.html', timestamp=int(time.time())))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/api/opc/values')
def proxy_opc_values():
    """
    Combined endpoint for ALL live values (OPC + PLC)
    Merges data from both C# services to provide unified tag list
    DEDUPLICATION: PLC tags override OPC tags with same name
    """
    try:
        import urllib.request
        import json as json_lib
        
        tag_map = {}  # Use dict to deduplicate by tagId
        errors = []
        
        # 1. Get OPC tags FIRST (lower priority)
        try:
            req = urllib.request.Request('http://127.0.0.1:5001/api/opc/values')
            with urllib.request.urlopen(req, timeout=3) as response:
                opc_data = json_lib.loads(response.read().decode('utf-8'))
                if 'tags' in opc_data:
                    for tag in opc_data['tags']:
                        tag_map[tag['tagId']] = tag
                    logger.debug(f"✅ Fetched {len(opc_data['tags'])} OPC tags")
        except Exception as e:
            errors.append(f"OPC: {str(e)}")
            logger.warning(f"⚠️ OPC service unavailable: {e}")
        
        # 2. Get PLC tags SECOND (higher priority - will override OPC duplicates)
        try:
            req = urllib.request.Request('http://127.0.0.1:5001/api/plc/values')
            with urllib.request.urlopen(req, timeout=3) as response:
                plc_data = json_lib.loads(response.read().decode('utf-8'))
                if plc_data.get('success') and 'values' in plc_data:
                    # Convert PLC format to OPC format and OVERRIDE any duplicates
                    # CRITICAL: Use 'address' as tagId (e.g., "Welding_Voltage_V"), not 'tagName' (e.g., "Welding Voltage V")
                    for plc_val in plc_data['values']:
                        tag_id = plc_val.get('address')  # Use address (with underscores), NOT tagName (with spaces)
                        if tag_id:  # Only add if address exists
                            tag_map[tag_id] = {
                                'tagId': tag_id,
                                'value': plc_val.get('value'),
                                'quality': plc_val.get('quality', 'Good'),
                                'timestamp': plc_val.get('timestamp'),
                                'source': f"PLC:{plc_val.get('plcId')}"
                            }
                    logger.debug(f"✅ Fetched {plc_data['count']} PLC tags (overriding any OPC duplicates)")
        except Exception as e:
            errors.append(f"PLC: {str(e)}")
            logger.warning(f"⚠️ PLC service unavailable: {e}")
        
        # Convert map back to list (deduplicated)
        all_tags = list(tag_map.values())
        
        # Return combined data
        response_data = {
            'count': len(all_tags),
            'timestamp': datetime.now().isoformat(),
            'tags': all_tags
        }
        
        if errors:
            response_data['warnings'] = errors
            
        logger.info(f"📊 Combined API: {len(all_tags)} unique tags (OPC + PLC deduplicated)")
        return jsonify(response_data), 200
            
    except Exception as e:
        logger.error(f"❌ Combined proxy error: {e}")
        return jsonify({'error': str(e), 'tags': [], 'count': 0}), 500


@app.route('/api/config')
def get_config():
    """Get HMI configuration and connection status"""
    backend_config = config.get('csharp_backend', {})
    backend_url = f"http://{backend_config.get('host', 'localhost')}:{backend_config.get('port', 5001)}"
    
    return jsonify({
        'updateInterval': config['performance']['update_interval_ms'],
        'maxPointsLive': config['performance']['max_points_live'],
        'maxPointsHistorical': config['performance']['max_points_historical'],
        'sampling': config.get('sampling', {}),
        'backendUrl': backend_url,
        'connections': {
            'signalr': signalr_listener.is_connected if signalr_listener else False,
            'database': historical_service.is_connected() if historical_service else False
        }
    })


@app.route('/api/tags/enabled')
def get_enabled_tags():
    """
    Get enabled tags from database for realtime trends UI
    """
    try:
        if not historical_service or not historical_service.is_connected():
            return jsonify({'error': 'Database not connected', 'tags': []}), 503
        
        with historical_service._get_connection() as conn:
          with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Column order in table: tag_id, tag_name, description, plant, area, equipment, data_type, eng_unit
            cursor.execute("""
                SELECT tag_id, tag_name, description, plant, area, equipment, data_type, eng_unit
                FROM historian_meta.tag_master
                WHERE enabled = true
                ORDER BY tag_id
            """)
            
            rows = cursor.fetchall()
            tags = []
            for row in rows:
                tags.append({
                    'tagId': row['tag_id'],
                    'tagName': row['tag_name'],
                    'description': row['description'],
                    'plant': row['plant'],
                    'area': row['area'],
                    'equipment': row['equipment'],
                    'dataType': row['data_type'],
                    'unit': row['eng_unit']
                })
        
        logger.info(f"📋 Returned {len(tags)} enabled tags from tag_master")
        return jsonify({
            'count': len(tags),
            'tags': tags,
            'timestamp': datetime.now().isoformat()
        })
            
    except Exception as e:
        logger.error(f"❌ Failed to fetch enabled tags: {e}")
        logger.error(f"❌ Error type: {type(e).__name__}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/log/realtime', methods=['POST'])
def log_realtime_data():
    """
    Log real-time sampled data to historian database
    Receives samples from millisecond polling UI
    """
    try:
        if not historical_service or not historical_service.is_connected():
            return jsonify({'success': False, 'error': 'Database not connected'}), 503
        
        data = request.get_json()
        samples = data.get('samples', [])
        
        if not samples:
            return jsonify({'success': False, 'error': 'No samples provided'}), 400
        
        # Insert samples into historian_timeseries
        with historical_service._get_connection() as conn:
            with conn.cursor() as cursor:
                insert_query = """
                    INSERT INTO historian_raw.historian_timeseries 
                    (tag_id, value_num, quality, opc_timestamp)
                    VALUES (%s, %s, %s, %s)
                """
                
                batch = []
                for sample in samples:
                    batch.append((
                        sample['tag_id'],
                        float(sample['value']),
                        192,  # Good quality (OPC standard)
                        sample['timestamp']
                    ))
                
                cursor.executemany(insert_query, batch)
                conn.commit()
                
                logger.info(f"✅ Logged {len(batch)} realtime samples to database")
                return jsonify({
                    'success': True,
                    'samples_logged': len(batch)
                })
                
    except Exception as e:
        logger.error(f"❌ Failed to log realtime data: {e}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tags/latest')
def get_latest_tags():
    """
    TEMPORARILY DISABLED - was causing connection pool exhaustion  
    Historical data works fine, but this endpoint needs connection pool fixes
    """
    return jsonify({})  # Return empty for now
    try:
        if not historical_service or not historical_service.is_connected():
            return jsonify({'error': 'Database not connected'}), 503
        
        with historical_service._get_connection() as conn:
          with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Get latest value for each enabled tag from historian_timeseries
            # Using DISTINCT ON for PostgreSQL efficiency
            cursor.execute("""
                SELECT DISTINCT ON (t.tag_id) 
                    t.tag_id,
                    h.value_num,
                    h.quality,
                    h.opc_timestamp
                FROM historian_meta.tag_master t
                LEFT JOIN historian_raw.historian_timeseries h ON h.tag_id = t.tag_id
                WHERE t.enabled = true
                ORDER BY t.tag_id, h.opc_timestamp DESC NULLS LAST
            """)
            
            rows = cursor.fetchall()
            tags = {}
            for row in rows:
                if row['value_num'] is not None:  # Has value
                    tags[row['tag_id']] = {
                        'value': float(row['value_num']) if row['value_num'] is not None else 0,
                        'quality': row['quality'] if row['quality'] else 'UNKNOWN',
                        'timestamp': row['opc_timestamp'].isoformat() if row['opc_timestamp'] else datetime.now().isoformat()
                    }
        
        return jsonify({
            'timestamp': datetime.now().isoformat(),
            'count': len(tags),
            'tags': tags
        })
            
    except Exception as e:
        logger.error(f"❌ Failed to fetch latest tags: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/historical/<tag_id>')
def get_historical(tag_id):
    """
    Get historical trend data from PostgreSQL
    Query parameters:
        - start: ISO timestamp
        - end: ISO timestamp  
        - mode: 'raw' (default) - exact values, no aggregation
        - max_points: Maximum data points (default: 50000)
    
    CRITICAL: Returns EXACT raw values from database - NO processing
    """
    try:
        # Parse parameters
        start_str = request.args.get('start')
        end_str = request.args.get('end')
        mode = request.args.get('mode', 'raw')
        max_points = int(request.args.get('max_points', 50000))
        
        # Parse timestamps
        if start_str and end_str:
            start_time = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
            end_time = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
        else:
            # Default: last 1 hour
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=1)
        
        if not historical_service or not historical_service.is_connected():
            return jsonify({'error': 'Database not connected'}), 503
        
        with historical_service._get_connection() as conn:
          with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if mode == 'raw':
                # FAST RAW QUERY: Get exact values, no aggregation
                # Use LIMIT with subquery sampling for large datasets
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM historian_raw.historian_timeseries
                    WHERE tag_id = %s
                    AND opc_timestamp >= %s
                    AND opc_timestamp <= %s
                """, (tag_id, start_time, end_time))
                
                result = cursor.fetchone(); total_count = result['count'] if result and result['count'] is not None else 0
                
                if total_count <= max_points:
                    # Small dataset - return all raw values
                    query = """
                        SELECT opc_timestamp, value_num, quality
                        FROM historian_raw.historian_timeseries
                        WHERE tag_id = %s
                        AND opc_timestamp >= %s
                        AND opc_timestamp <= %s
                        ORDER BY opc_timestamp
                    """
                    cursor.execute(query, (tag_id, start_time, end_time))
                else:
                    # Large dataset - sample every Nth row (keep exact values!)
                    sample_every = max(1, total_count // max_points)
                    
                    query = f"""
                        WITH numbered AS (
                            SELECT opc_timestamp, value_num, quality,
                                   ROW_NUMBER() OVER (ORDER BY opc_timestamp) as rn
                            FROM historian_raw.historian_timeseries
                            WHERE tag_id = %s
                            AND opc_timestamp >= %s
                            AND opc_timestamp <= %s
                        )
                        SELECT opc_timestamp, value_num, quality
                        FROM numbered
                        WHERE rn % {sample_every} = 1
                        ORDER BY opc_timestamp
                        LIMIT %s
                    """
                    cursor.execute(query, (tag_id, start_time, end_time, max_points))
                
                rows = cursor.fetchall()
                
                # Return exact raw values
                data = [
                    {
                        'timestamp': row[0].isoformat(),
                        'value': float(row[1]) if row[1] is not None else None,
                        'quality': row[2]
                    }
                    for row in rows
                ]
                
                return jsonify({
                    'tagId': tag_id,
                    'startTime': start_time.isoformat(),
                    'endTime': end_time.isoformat(),
                    'mode': 'raw',
                    'count': len(data),
                    'totalRows': total_count,
                    'data': data
                })
            else:
                return jsonify({'error': 'Invalid mode'}), 400
        
    except Exception as e:
        logger.error(f"❌ Historical query error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/historical/multiple', methods=['POST'])
def get_multiple_historical():
    """
    Get historical data for multiple tags
    Request body: {
        "tagIds": ["tag1", "tag2"],
        "hours": 1,
        "maxPoints": 1000,
        "samplingInterval": 30  (NEW: explicit sampling interval in seconds)
    }
    """
    try:
        data = request.json
        tag_ids = data.get('tagIds', [])
        hours = data.get('hours', 1)
        max_points = data.get('maxPoints', 1000)
        sampling_interval = data.get('samplingInterval')  # NEW: Get explicit sampling interval
        
        # Use timezone-aware datetime to match database timestamps
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        results = historical_service.get_multiple_trends(
            tag_ids, start_time, end_time, max_points, sampling_interval
        )
        
        return jsonify({
            'startTime': start_time.isoformat(),
            'endTime': end_time.isoformat(),
            'trends': results
        })
        
    except Exception as e:
        logger.error(f"❌ Multiple historical query error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/statistics/<tag_id>')
def get_statistics(tag_id):
    """Get statistical summary for a tag"""
    try:
        hours = int(request.args.get('hours', 24))
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        stats = historical_service.get_tag_statistics(tag_id, start_time, end_time)
        
        return jsonify({
            'tagId': tag_id,
            'timeRange': f'{hours}h',
            'statistics': stats
        })
        
    except Exception as e:
        logger.error(f"❌ Statistics query error: {e}")
        return jsonify({'error': str(e)}), 500


@socketio.on('connect')
def handle_connect():
    """Browser client connected via WebSocket"""
    global connected_clients
    connected_clients.add(request.sid)
    logger.info(f"✅ Client connected: {request.sid} (Total: {len(connected_clients)})")
    
    # Send current cached values immediately
    emit('tag_update', list(latest_tag_values.values()))


@socketio.on('disconnect')
def handle_disconnect():
    """Browser client disconnected"""
    global connected_clients
    connected_clients.discard(request.sid)
    logger.info(f"⚠️ Client disconnected: {request.sid} (Remaining: {len(connected_clients)})")


@socketio.on('subscribe_tags')
def handle_subscribe(data):
    """
    Client wants to subscribe to specific tags
    Forwards to C# SignalR hub for filtering
    """
    tag_ids = data.get('tagIds', [])
    
    if signalr_listener and signalr_listener.is_connected:
        signalr_listener.subscribe_to_tags(tag_ids)
        logger.info(f"✅ Client {request.sid} subscribed to {len(tag_ids)} tags")
        emit('subscribe_success', {'count': len(tag_ids)})
    else:
        logger.warning("⚠️ SignalR not connected, cannot subscribe")
        emit('subscribe_error', {'message': 'SignalR not connected'})


# ============================================================================
#                               ALARM API ENDPOINTS
# ============================================================================

@app.route('/api/alarms/active')
def get_active_alarms():
    """Get all currently active alarms"""
    if not alarm_service:
        return jsonify({'error': 'Alarm service not available'}), 503
    
    try:
        alarms = alarm_service.get_active_alarms()
        return jsonify({'alarms': alarms, 'count': len(alarms)})
    except Exception as e:
        logger.error(f"❌ Failed to get active alarms: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/alarms/summary')
def get_alarm_summary():
    """Get alarm counts by priority"""
    if not alarm_service:
        return jsonify({'error': 'Alarm service not available'}), 503
    
    try:
        summary = alarm_service.get_alarm_summary()
        return jsonify(summary)
    except Exception as e:
        logger.error(f"❌ Failed to get alarm summary: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/alarms/<int:alarm_id>/acknowledge', methods=['POST'])
def acknowledge_alarm(alarm_id):
    """Acknowledge a specific alarm"""
    if not alarm_service:
        return jsonify({'error': 'Alarm service not available'}), 503
    
    try:
        data = request.get_json() or {}
        acknowledged_by = data.get('acknowledged_by', 'operator')
        
        success = alarm_service.acknowledge_alarm(alarm_id, acknowledged_by)
        if success:
            return jsonify({'success': True, 'message': f'Alarm {alarm_id} acknowledged'})
        else:
            return jsonify({'success': False, 'message': 'Alarm not found or already acknowledged'}), 404
            
    except Exception as e:
        logger.error(f"❌ Failed to acknowledge alarm {alarm_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/alarms/<int:alarm_id>/clear', methods=['POST'])
def clear_alarm(alarm_id):
    """Clear/resolve a specific alarm"""
    if not alarm_service:
        return jsonify({'error': 'Alarm service not available'}), 503
    
    try:
        success = alarm_service.clear_alarm(alarm_id)
        if success:
            return jsonify({'success': True, 'message': f'Alarm {alarm_id} cleared'})
        else:
            return jsonify({'success': False, 'message': 'Alarm not found'}), 404
            
    except Exception as e:
        logger.error(f"❌ Failed to clear alarm {alarm_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/alarms/check/<tag_id>')
def check_tag_alarms(tag_id):
    """Check if a tag should trigger alarms (for testing)"""
    if not alarm_service:
        return jsonify({'error': 'Alarm service not available'}), 503
    
    try:
        # Get current value from historical service
        current_value = request.args.get('value', type=float)
        quality = request.args.get('quality', 'GOOD')
        
        if current_value is None:
            return jsonify({'error': 'value parameter required'}), 400
        
        alarms = alarm_service.check_tag_alarms(tag_id, current_value, quality)
        return jsonify({'alarms': alarms, 'count': len(alarms)})
        
    except Exception as e:
        logger.error(f"❌ Failed to check alarms for {tag_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/alarms/test', methods=['POST'])
def test_alarm_scenario():
    """Test alarm scenarios with any tag name and value"""
    if not alarm_service:
        return jsonify({'error': 'Alarm service not available'}), 503
    
    try:
        data = request.get_json() or {}
        tag_id = data.get('tag_id', 'Test_Motor_Health')
        value = float(data.get('value', 0))
        
        # Force check alarms for this test scenario
        alarms = alarm_service.check_tag_alarms(tag_id, value, 'GOOD')
        
        # Store any new alarms
        if alarms:
            alarm_service._store_alarms(alarms)
        
        return jsonify({
            'tag_id': tag_id,
            'value': value,
            'triggered_alarms': alarms,
            'count': len(alarms),
            'message': f'Checked {tag_id} = {value}, found {len(alarms)} alarms'
        })
        
    except Exception as e:
        logger.error(f"❌ Failed to test alarm scenario: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================


def start_signalr_listener():
    """Start listening to C# SignalR hub in background"""
    global signalr_listener
    
    signalr_config = {
        'host': config['csharp_backend']['host'],
        'port': config['csharp_backend']['port'],
        'hub_path': config['csharp_backend']['signalr_hub']
    }
    
    logger.info(f"🔌 Starting SignalR listener: http://{signalr_config['host']}:{signalr_config['port']}{signalr_config['hub_path']}")
    
    signalr_listener = SignalRListener(signalr_config, tag_cache, on_signalr_tag_update)
    signalr_listener.connect()


def initialize_services():
    """Initialize database and SignalR connections (both optional - graceful degradation)"""
    logger.info("🚀 Initializing HMI services...")
    logger.info("=" * 60)
    logger.info("ℹ️  HMI MODES:")
    logger.info("   - FULL MODE: C# backend + Database (live + historical)")
    logger.info("   - HISTORICAL ONLY: Database only (no live data)")
    logger.info("   - DEMO MODE: Neither connected (UI demo)")
    logger.info("=" * 60)
    
    # Try to connect to database (optional - app works without it)
    db_connected = False
    try:
        if historical_service.connect():
            logger.info("✅ Historical data service ready")
            db_connected = True
        else:
            logger.warning("⚠️ Historical data service unavailable (database not connected)")
    except Exception as e:
        logger.warning(f"⚠️ Database connection skipped: {e}")
        logger.info("ℹ️  Historical trends will not be available")
    
    # Start tag cache background refresh
    try:
        tag_cache.start()
        logger.info("✅ Tag cache started (background refresh every 30s)")
    except Exception as e:
        logger.warning(f"⚠️ Tag cache failed to start: {e}")
    
    # Initialize alarm service if database is connected
    global alarm_service
    try:
        if db_connected and historical_service._pool:
            alarm_service = AlarmService(historical_service._pool)
            logger.info("✅ Alarm service ready")
        else:
            logger.warning("⚠️ Alarm service unavailable (database not connected)")
    except Exception as e:
        logger.warning(f"⚠️ Alarm service failed to start: {e}")
    
    # HTTP POLLING MODE: HMI polls /api/opc/values endpoint (same as Historian)
    # This matches HistorianIngestHostedService pattern - no SignalR needed
    # SignalR is optional for UI responsiveness, but HTTP polling is simpler & reliable
    logger.info("📊 HMI Mode: HTTP Polling (same pattern as Historian service)")
    logger.info("   Browser polls http://localhost:5001/api/opc/values every 1 second")
    
    # Determine mode
    if signalr_listener and signalr_listener.is_connected and db_connected:
        logger.info("✅ HMI Mode: FULL (Live + Historical)")
    elif db_connected:
        logger.info("✅ HMI Mode: HISTORICAL ONLY")
    else:
        logger.info("✅ HMI Mode: DEMO (UI only)")
    
    logger.info("=" * 60)


if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🚀 HMI Application Starting...")
    logger.info("=" * 60)
    logger.info(f"📍 HMI Dashboard: http://{config['hmi_server']['host']}:{config['hmi_server']['port']}")
    logger.info(f"🔌 C# Backend (optional): http://{config['csharp_backend']['host']}:{config['csharp_backend']['port']}")
    logger.info(f"📊 Database (optional): {config['database']['host']}:{config['database']['port']}/{config['database']['database']}")
    logger.info("")
    logger.info("ℹ️  NOTE: HMI works in multiple modes:")
    logger.info("   ✅ FULL MODE: C# + DB connected → Live data + DB writes + Historical")
    logger.info("   ✅ HISTORICAL MODE: Only DB connected → Query old data")
    logger.info("   ✅ DEMO MODE: Neither connected → UI exploration")
    logger.info("")
    logger.info("💾 DB Writer: Only writes tags in historian_meta.tag_master (enabled=true)")
    logger.info("=" * 60)
    
    # Initialize services within app context
    with app.app_context():
        initialize_services()
    
    # Cleanup on exit (graceful shutdown)
    import atexit
    def cleanup():
        try:
            logger.info("🛑 Shutting down HMI...")
            if signalr_listener:
                signalr_listener.stop()
            # Use threading.Event instead of join() to avoid eventlet conflicts
            tag_cache._stop_event.set()
            logger.info("✅ Services stopped")
        except (KeyboardInterrupt, SystemExit, Exception):
            pass  # Silently ignore cleanup errors during forced shutdown
    
    atexit.register(cleanup)
    
    # Start Flask-SocketIO server
    socketio.run(
        app,
        host=config['hmi_server']['host'],
        port=config['hmi_server']['port'],
        debug=config['hmi_server']['debug']
    )
