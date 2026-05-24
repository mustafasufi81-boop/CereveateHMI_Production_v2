"""
PLC Health & Real-Time Trends HMI
=================================
Features:
1. PLC Health Dashboard - Connection status, polling rates, message rates
2. Real-Time Trends - All 32 PLC tags from MQTT with 200ms scan visualization
3. Performance Metrics - Latency, samples per second, data throughput
4. MQTT Logging - ALL messages logged to D:\OpcLogs\MSLog\mslog.txt

Run: python plc_health_trends.py
Open: http://localhost:5003

Data Source: MQTT topic plc/plc/all (from C# PlcGateway)
"""

from flask import Flask, render_template_string, jsonify, request
import threading
import time
import json
import requests
import os
from datetime import datetime
from collections import deque
import paho.mqtt.client as mqtt

app = Flask(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "plc/plc/all"
API_BASE = "http://localhost:5001"

# Trend history: 300 points = 5 minutes at 1 sec/point OR 60 seconds at 200ms
MAX_TREND_POINTS = 300

# MQTT Logging
LOG_DIR = r"D:\OpcLogs\MSLog"
LOG_FILE = os.path.join(LOG_DIR, "mslog.txt")

# ============================================================================
# MQTT LOGGING - ALL MESSAGES WITH MILLISECOND TIMESTAMPS
# ============================================================================
def ensure_log_dir():
    """Create log directory if it doesn't exist"""
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
        print(f"Created log directory: {LOG_DIR}")

def log_mqtt_message(topic, payload):
    """
    Log ALL MQTT data to file with millisecond precision timestamps
    Captures: plc/plc/all (tag values), plc/health (health metrics)
    """
    try:
        ensure_log_dir()
        
        # Current receive timestamp with milliseconds
        receive_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        # Build detailed log entry
        lines = []
        lines.append(f"{'='*80}")
        lines.append(f"[RECEIVED] {receive_ts}")
        lines.append(f"[TOPIC]    {topic}")
        
        # Extract PLC timestamp from payload if present
        plc_ts = payload.get("timestamp", "N/A")
        lines.append(f"[PLC_TS]   {plc_ts}")
        
        # For tag value messages (plc/plc/all)
        if "values" in payload and isinstance(payload.get("values"), list):
            tag_count = payload.get("tagCount", len(payload["values"]))
            total_samples = payload.get("totalSamples", tag_count)
            publish_interval = payload.get("publishIntervalMs", "N/A")
            
            lines.append(f"[TYPE]     TAG_VALUES")
            lines.append(f"[TAGS]     {tag_count} tags | {total_samples} total samples | interval={publish_interval}ms")
            lines.append(f"")
            lines.append(f"TAG DATA:")
            lines.append(f"{'-'*80}")
            
            # Log each tag with its samples
            for tag in payload["values"]:
                tag_name = tag.get("tag", tag.get("tagName", "unknown"))
                plc_id = tag.get("plcId", "unknown")
                scan_rate = tag.get("scanRateMs", "N/A")
                sample_count = tag.get("sampleCount", 1)
                data_type = tag.get("dataType", "unknown")
                
                # Get samples array or single value
                samples = tag.get("samples", [])
                if samples:
                    # Multiple samples per tag
                    lines.append(f"  [{tag_name}] plc={plc_id} | rate={scan_rate}ms | type={data_type} | samples={sample_count}")
                    for i, sample in enumerate(samples):
                        s_value = sample.get("value", "N/A")
                        s_quality = sample.get("quality", "N/A")
                        s_ts = sample.get("timestamp", "N/A")
                        lines.append(f"    [{i+1}] value={s_value} | quality={s_quality} | ts={s_ts}")
                else:
                    # Single value (backward compatible)
                    value = tag.get("value", "N/A")
                    quality = tag.get("quality", "N/A")
                    tag_ts = tag.get("timestamp", "N/A")
                    lines.append(f"  [{tag_name}] value={value} | quality={quality} | ts={tag_ts}")
        
        # For health messages (plc/health)
        elif "plcs" in payload:
            plc_count = payload.get("plcCount", 0)
            connected = payload.get("connectedCount", 0)
            
            lines.append(f"[TYPE]     HEALTH_METRICS")
            lines.append(f"[PLCS]     {plc_count} total | {connected} connected")
            lines.append(f"")
            lines.append(f"PLC HEALTH DATA:")
            lines.append(f"{'-'*80}")
            
            for plc in payload.get("plcs", []):
                plc_id = plc.get("plcId", "unknown")
                plc_name = plc.get("plcName", plc_id)
                is_connected = plc.get("isConnected", False)
                latency = plc.get("averageReadTimeMs", 0)
                success_rate = plc.get("successRatePercent", 0)
                total_polls = plc.get("totalPolls", 0)
                failed_polls = plc.get("failedPolls", 0)
                consec_fails = plc.get("consecutiveFailures", 0)
                tag_count = plc.get("tagCount", 0)
                
                status = "CONNECTED" if is_connected else "DISCONNECTED"
                lines.append(f"  [{plc_name}] {status}")
                lines.append(f"    latency={latency:.1f}ms | success={success_rate:.1f}% | tags={tag_count}")
                lines.append(f"    polls: total={total_polls} | failed={failed_polls} | consecutive_errors={consec_fails}")
        
        else:
            # Unknown message type - log raw JSON
            lines.append(f"[TYPE]     UNKNOWN")
            lines.append(f"[RAW]      {json.dumps(payload)}")
        
        lines.append(f"")
        
        # Write to file
        log_entry = "\n".join(lines) + "\n"
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)
            
    except Exception as e:
        print(f"Error logging to file: {e}")

# ============================================================================
# DATA STORES
# ============================================================================

# MQTT Statistics
mqtt_stats = {
    'connected': False,
    'messages_received': 0,
    'messages_per_second': 0,
    'samples_per_second': 0,
    'total_samples': 0,
    'last_message_time': None,
    'latency_ms': 0,
    'connection_time': None,
    'reconnect_count': 0
}

# PLC Health from API
plc_health = {
    'status': 'unknown',
    'plcs': [],
    'last_check': None
}

# Tag Values & Trends
tag_values = {}  # tag_name -> {value, quality, timestamp, dataType, plcId}
tag_trends = {}  # tag_name -> deque of {timestamp, value}
tag_scan_rates = {}  # tag_name -> scan_rate_ms (from samples array)

# Message timing for rate calculation
message_times = deque(maxlen=100)
sample_counts = deque(maxlen=100)

# Lock for thread safety
data_lock = threading.Lock()

# ============================================================================
# MQTT CLIENT
# ============================================================================

def on_connect(client, userdata, flags, rc):
    global mqtt_stats
    if rc == 0:
        mqtt_stats['connected'] = True
        mqtt_stats['connection_time'] = datetime.now().isoformat()
        client.subscribe(MQTT_TOPIC)
        client.subscribe("plc/#")  # Subscribe to all PLC topics
        print(f"[MQTT] Connected and subscribed to {MQTT_TOPIC}")
    else:
        mqtt_stats['connected'] = False
        mqtt_stats['reconnect_count'] += 1
        print(f"[MQTT] Connection failed with code {rc}")

def on_disconnect(client, userdata, rc):
    global mqtt_stats
    mqtt_stats['connected'] = False
    print(f"[MQTT] Disconnected (code {rc})")

def on_message(client, userdata, msg):
    global mqtt_stats, tag_values, tag_trends, tag_scan_rates
    
    try:
        receive_time = time.time()
        payload = json.loads(msg.payload)
        
        # LOG ALL MQTT MESSAGES TO FILE
        log_mqtt_message(msg.topic, payload)
        
        with data_lock:
            # Update message stats
            mqtt_stats['messages_received'] += 1
            mqtt_stats['last_message_time'] = datetime.now().isoformat()
            
            # Track message timing for rate calculation
            message_times.append(receive_time)
            
            # Parse values array
            values = payload.get('values', [])
            sample_count = 0
            
            for tag_data in values:
                tag_name = tag_data.get('tag', tag_data.get('tagName', ''))
                if not tag_name:
                    continue
                
                # Check for samples array (multi-sample mode)
                samples = tag_data.get('samples', [])
                if samples:
                    # Multi-sample mode - process all samples for trends
                    for sample in samples:
                        value = sample.get('value')
                        timestamp = sample.get('timestamp', datetime.now().isoformat())
                        add_trend_point(tag_name, value, timestamp)
                        sample_count += 1
                    
                    # Store scan rate
                    scan_rate = tag_data.get('scanRateMs', 1000)
                    tag_scan_rates[tag_name] = scan_rate
                    
                    # Latest value
                    if samples:
                        latest = samples[-1]
                        tag_values[tag_name] = {
                            'value': latest.get('value'),
                            'quality': latest.get('quality', 'Good'),
                            'timestamp': latest.get('timestamp'),
                            'dataType': tag_data.get('dataType', 'float'),
                            'plcId': tag_data.get('plcId', ''),
                            'scanRateMs': scan_rate,
                            'sampleCount': len(samples)
                        }
                else:
                    # Single value mode
                    value = tag_data.get('value')
                    timestamp = tag_data.get('timestamp', datetime.now().isoformat())
                    
                    tag_values[tag_name] = {
                        'value': value,
                        'quality': tag_data.get('quality', 'Good'),
                        'timestamp': timestamp,
                        'dataType': tag_data.get('dataType', 'float'),
                        'plcId': tag_data.get('plcId', ''),
                        'scanRateMs': tag_data.get('scanRateMs', 1000),
                        'sampleCount': 1
                    }
                    
                    add_trend_point(tag_name, value, timestamp)
                    sample_count += 1
            
            sample_counts.append(sample_count)
            mqtt_stats['total_samples'] += sample_count
            
            # Calculate publish interval latency
            msg_timestamp = payload.get('timestamp')
            if msg_timestamp:
                try:
                    # Parse ISO timestamp
                    if 'Z' in msg_timestamp:
                        msg_time = datetime.fromisoformat(msg_timestamp.replace('Z', '+00:00'))
                    else:
                        msg_time = datetime.fromisoformat(msg_timestamp)
                    now = datetime.now(msg_time.tzinfo) if msg_time.tzinfo else datetime.now()
                    mqtt_stats['latency_ms'] = int((now - msg_time).total_seconds() * 1000)
                except:
                    pass
            
            # Calculate rates
            if len(message_times) >= 2:
                time_span = message_times[-1] - message_times[0]
                if time_span > 0:
                    mqtt_stats['messages_per_second'] = round(len(message_times) / time_span, 2)
                    mqtt_stats['samples_per_second'] = round(sum(sample_counts) / time_span, 2)
                    
    except Exception as e:
        print(f"[MQTT] Error processing message: {e}")

def add_trend_point(tag_name, value, timestamp):
    """Add a point to the trend history for a tag"""
    if tag_name not in tag_trends:
        tag_trends[tag_name] = deque(maxlen=MAX_TREND_POINTS)
    
    # Only add numeric values
    if value is not None and not isinstance(value, bool):
        try:
            numeric_value = float(value)
            tag_trends[tag_name].append({
                'timestamp': timestamp,
                'value': numeric_value
            })
        except (ValueError, TypeError):
            pass

# Start MQTT client
mqtt_client = mqtt.Client(client_id='plc_health_trends_hmi', clean_session=True)
mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.on_message = on_message

def mqtt_connect():
    """Connect to MQTT broker"""
    try:
        print(f"[MQTT] Connecting to {MQTT_BROKER}:{MQTT_PORT}...")
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
    except Exception as e:
        print(f"[MQTT] Connection error: {e}")

# ============================================================================
# PLC HEALTH CHECKER (Background Thread)
# ============================================================================

def check_plc_health():
    """Background thread to poll PLC health from API"""
    global plc_health
    while True:
        try:
            # Get health from C# API
            response = requests.get(f"{API_BASE}/api/plc/health", timeout=5)
            if response.ok:
                health_data = response.json()
                with data_lock:
                    plc_health = {
                        'status': 'online',
                        'data': health_data,
                        'last_check': datetime.now().isoformat()
                    }
            else:
                with data_lock:
                    plc_health['status'] = 'api_error'
        except requests.exceptions.ConnectionError:
            with data_lock:
                plc_health['status'] = 'offline'
        except Exception as e:
            with data_lock:
                plc_health['status'] = f'error: {str(e)[:50]}'
        
        time.sleep(2)  # Check every 2 seconds

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/api/mqtt/stats')
def get_mqtt_stats():
    """Get MQTT connection statistics"""
    with data_lock:
        return jsonify(mqtt_stats)

@app.route('/api/plc/health')
def get_plc_health():
    """Get PLC health status"""
    with data_lock:
        return jsonify(plc_health)

@app.route('/api/tags')
def get_all_tags():
    """Get all current tag values"""
    with data_lock:
        return jsonify({
            'count': len(tag_values),
            'tags': tag_values
        })

@app.route('/api/tags/<tag_name>')
def get_tag(tag_name):
    """Get a specific tag value"""
    with data_lock:
        if tag_name in tag_values:
            return jsonify(tag_values[tag_name])
        return jsonify({'error': 'Tag not found'}), 404

@app.route('/api/trends/<tag_name>')
def get_tag_trend(tag_name):
    """Get trend history for a specific tag"""
    with data_lock:
        if tag_name in tag_trends:
            return jsonify({
                'tag': tag_name,
                'points': list(tag_trends[tag_name]),
                'scanRateMs': tag_scan_rates.get(tag_name, 1000)
            })
        return jsonify({'error': 'Tag not found', 'points': []})

@app.route('/api/trends')
def get_all_trends():
    """Get trend history for all tags"""
    with data_lock:
        result = {}
        for tag_name, points in tag_trends.items():
            result[tag_name] = {
                'points': list(points),
                'scanRateMs': tag_scan_rates.get(tag_name, 1000)
            }
        return jsonify(result)

# ============================================================================
# HTML TEMPLATE
# ============================================================================

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PLC Health & Trends - Real-Time HMI</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            background: #0a1929; 
            color: #e0e0e0; 
            min-height: 100vh;
        }
        
        .header {
            background: linear-gradient(135deg, #1a237e 0%, #0d47a1 100%);
            padding: 15px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        }
        
        .header h1 { 
            font-size: 24px; 
            font-weight: 600;
            color: #fff;
        }
        
        .header-stats {
            display: flex;
            gap: 30px;
        }
        
        .stat-item {
            text-align: center;
        }
        
        .stat-value {
            font-size: 28px;
            font-weight: bold;
            color: #4fc3f7;
        }
        
        .stat-label {
            font-size: 11px;
            color: #90caf9;
            text-transform: uppercase;
        }
        
        .container {
            display: grid;
            grid-template-columns: 350px 1fr;
            gap: 20px;
            padding: 20px;
            max-height: calc(100vh - 80px);
        }
        
        .sidebar {
            display: flex;
            flex-direction: column;
            gap: 15px;
            overflow-y: auto;
            max-height: calc(100vh - 100px);
        }
        
        .main-content {
            display: flex;
            flex-direction: column;
            gap: 15px;
            overflow-y: auto;
        }
        
        .card {
            background: #132f4c;
            border-radius: 12px;
            padding: 15px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        }
        
        .card-title {
            font-size: 14px;
            font-weight: 600;
            color: #90caf9;
            margin-bottom: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        /* Health Panel */
        .health-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
        }
        
        .health-item {
            background: #1e3a5f;
            padding: 12px;
            border-radius: 8px;
            text-align: center;
        }
        
        .health-item .value {
            font-size: 22px;
            font-weight: bold;
            color: #4fc3f7;
        }
        
        .health-item .label {
            font-size: 10px;
            color: #90caf9;
            text-transform: uppercase;
            margin-top: 4px;
        }
        
        .health-item.good .value { color: #66bb6a; }
        .health-item.warning .value { color: #ffb74d; }
        .health-item.error .value { color: #ef5350; }
        
        /* MQTT Status */
        .mqtt-status {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px;
            background: #1e3a5f;
            border-radius: 8px;
            margin-bottom: 10px;
        }
        
        .mqtt-indicator {
            width: 14px;
            height: 14px;
            border-radius: 50%;
            background: #ef5350;
        }
        
        .mqtt-indicator.connected { 
            background: #66bb6a; 
            box-shadow: 0 0 10px #66bb6a;
        }
        
        /* Tag List */
        .tag-list {
            max-height: 400px;
            overflow-y: auto;
        }
        
        .tag-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 12px;
            background: #1e3a5f;
            border-radius: 6px;
            margin-bottom: 6px;
            cursor: pointer;
            transition: all 0.2s;
            border-left: 3px solid transparent;
        }
        
        .tag-item:hover { 
            background: #2a4a6f; 
        }
        
        .tag-item.selected {
            border-left-color: #4fc3f7;
            background: #2a4a6f;
        }
        
        .tag-item .name {
            font-size: 12px;
            color: #90caf9;
            max-width: 180px;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        
        .tag-item .value {
            font-size: 14px;
            font-weight: bold;
            color: #4fc3f7;
        }
        
        .tag-item .quality {
            font-size: 10px;
            color: #66bb6a;
        }
        
        .tag-item .quality.bad { color: #ef5350; }
        
        /* Charts */
        .chart-container {
            height: 250px;
            margin-bottom: 15px;
        }
        
        .charts-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
        }
        
        .chart-card {
            background: #1e3a5f;
            border-radius: 8px;
            padding: 10px;
        }
        
        .chart-card .title {
            font-size: 12px;
            color: #90caf9;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
        }
        
        .chart-card .scan-rate {
            font-size: 10px;
            color: #ffb74d;
        }
        
        .chart-wrapper {
            height: 180px;
        }
        
        /* Scrollbar */
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #0a1929; }
        ::-webkit-scrollbar-thumb { background: #1e3a5f; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #2a4a6f; }
        
        /* Tabs */
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
        }
        
        .tab {
            padding: 8px 16px;
            background: #1e3a5f;
            border: none;
            border-radius: 6px;
            color: #90caf9;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .tab.active {
            background: #0d47a1;
            color: #fff;
        }
        
        .tab:hover { background: #2a4a6f; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🏭 PLC Health & Real-Time Trends</h1>
        <div class="header-stats">
            <div class="stat-item">
                <div class="stat-value" id="totalTags">0</div>
                <div class="stat-label">Tags</div>
            </div>
            <div class="stat-item">
                <div class="stat-value" id="msgRate">0</div>
                <div class="stat-label">Msg/sec</div>
            </div>
            <div class="stat-item">
                <div class="stat-value" id="sampleRate">0</div>
                <div class="stat-label">Samples/sec</div>
            </div>
            <div class="stat-item">
                <div class="stat-value" id="latency">0</div>
                <div class="stat-label">Latency (ms)</div>
            </div>
        </div>
    </div>
    
    <div class="container">
        <!-- Sidebar -->
        <div class="sidebar">
            <!-- MQTT Status -->
            <div class="card">
                <div class="card-title">MQTT Connection</div>
                <div class="mqtt-status">
                    <div class="mqtt-indicator" id="mqttIndicator"></div>
                    <span id="mqttStatus">Disconnected</span>
                </div>
                <div class="health-grid">
                    <div class="health-item">
                        <div class="value" id="totalMessages">0</div>
                        <div class="label">Total Messages</div>
                    </div>
                    <div class="health-item">
                        <div class="value" id="totalSamples">0</div>
                        <div class="label">Total Samples</div>
                    </div>
                </div>
            </div>
            
            <!-- PLC Health -->
            <div class="card">
                <div class="card-title">PLC Health</div>
                <div id="plcHealthContent">Loading...</div>
            </div>
            
            <!-- Tag List -->
            <div class="card">
                <div class="card-title">All Tags (Click to add to chart)</div>
                <div class="tag-list" id="tagList"></div>
            </div>
        </div>
        
        <!-- Main Content -->
        <div class="main-content">
            <div class="tabs">
                <button class="tab active" onclick="showTab('selected')">Selected Trends</button>
                <button class="tab" onclick="showTab('all')">All Numeric Tags</button>
            </div>
            
            <div id="selectedTrends" class="charts-grid"></div>
            <div id="allTrends" class="charts-grid" style="display:none;"></div>
        </div>
    </div>
    
    <script>
        // Chart instances
        const charts = {};
        const selectedTags = new Set();
        let allTagsData = {};
        let currentTab = 'selected';
        
        // Default selected tags (first 4 numeric)
        const defaultSelectedTags = [];
        
        // Colors for charts
        const chartColors = [
            '#4fc3f7', '#66bb6a', '#ffb74d', '#ef5350', 
            '#ab47bc', '#26a69a', '#ec407a', '#7e57c2'
        ];
        
        function showTab(tab) {
            currentTab = tab;
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            event.target.classList.add('active');
            
            document.getElementById('selectedTrends').style.display = tab === 'selected' ? 'grid' : 'none';
            document.getElementById('allTrends').style.display = tab === 'all' ? 'grid' : 'none';
            
            if (tab === 'all') {
                updateAllTrendsCharts();
            }
        }
        
        function formatValue(value) {
            if (typeof value === 'boolean') return value ? 'ON' : 'OFF';
            if (typeof value === 'number') return value.toFixed(2);
            return value;
        }
        
        async function updateMqttStats() {
            try {
                const response = await fetch('/api/mqtt/stats');
                const data = await response.json();
                
                // Update header stats
                document.getElementById('msgRate').textContent = data.messages_per_second || 0;
                document.getElementById('sampleRate').textContent = data.samples_per_second || 0;
                document.getElementById('latency').textContent = data.latency_ms || 0;
                document.getElementById('totalMessages').textContent = data.messages_received || 0;
                document.getElementById('totalSamples').textContent = data.total_samples || 0;
                
                // Update connection status
                const indicator = document.getElementById('mqttIndicator');
                const status = document.getElementById('mqttStatus');
                if (data.connected) {
                    indicator.classList.add('connected');
                    status.textContent = 'Connected';
                } else {
                    indicator.classList.remove('connected');
                    status.textContent = 'Disconnected';
                }
            } catch (e) {
                console.error('Error fetching MQTT stats:', e);
            }
        }
        
        async function updatePlcHealth() {
            try {
                const response = await fetch('/api/plc/health');
                const data = await response.json();
                
                const container = document.getElementById('plcHealthContent');
                
                if (data.status === 'online' && data.data) {
                    const health = data.data;
                    let html = '<div class="health-grid">';
                    
                    // Overall status
                    const statusClass = health.overallStatus === 'Healthy' ? 'good' : 
                                       health.overallStatus === 'Degraded' ? 'warning' : 'error';
                    html += `<div class="health-item ${statusClass}">
                        <div class="value">${health.overallStatus || 'Unknown'}</div>
                        <div class="label">Status</div>
                    </div>`;
                    
                    html += `<div class="health-item">
                        <div class="value">${health.activePlcCount || 0}</div>
                        <div class="label">Active PLCs</div>
                    </div>`;
                    
                    html += `<div class="health-item">
                        <div class="value">${health.totalTagsScanned || 0}</div>
                        <div class="label">Tags Scanned</div>
                    </div>`;
                    
                    html += `<div class="health-item">
                        <div class="value">${health.scanRate || 0}</div>
                        <div class="label">Scans/sec</div>
                    </div>`;
                    
                    html += '</div>';
                    
                    // PLC details
                    if (health.plcs && health.plcs.length > 0) {
                        html += '<div style="margin-top:15px; font-size:12px; color:#90caf9;">';
                        health.plcs.forEach(plc => {
                            const plcClass = plc.status === 'Connected' ? 'good' : 'error';
                            html += `<div class="health-item ${plcClass}" style="margin-top:8px;">
                                <div class="value" style="font-size:16px;">${plc.plcId}</div>
                                <div class="label">${plc.status} | ${plc.tagCount} tags | ${plc.scanRateMs}ms</div>
                            </div>`;
                        });
                        html += '</div>';
                    }
                    
                    container.innerHTML = html;
                } else {
                    container.innerHTML = `<div class="health-item error">
                        <div class="value">⚠️</div>
                        <div class="label">${data.status || 'Unknown'}</div>
                    </div>`;
                }
            } catch (e) {
                document.getElementById('plcHealthContent').innerHTML = 
                    '<div class="health-item error"><div class="value">Error</div><div class="label">API unavailable</div></div>';
            }
        }
        
        async function updateTags() {
            try {
                const response = await fetch('/api/tags');
                const data = await response.json();
                
                document.getElementById('totalTags').textContent = data.count || 0;
                
                const tagList = document.getElementById('tagList');
                let html = '';
                
                // Sort tags alphabetically
                const sortedTags = Object.entries(data.tags || {}).sort((a, b) => a[0].localeCompare(b[0]));
                
                for (const [name, tag] of sortedTags) {
                    allTagsData[name] = tag;
                    const isSelected = selectedTags.has(name);
                    const qualityClass = tag.quality === 'Good' ? '' : 'bad';
                    
                    html += `<div class="tag-item ${isSelected ? 'selected' : ''}" onclick="toggleTag('${name}')">
                        <div>
                            <div class="name">${name}</div>
                            <div class="quality ${qualityClass}">${tag.quality} | ${tag.scanRateMs || 1000}ms</div>
                        </div>
                        <div class="value">${formatValue(tag.value)}</div>
                    </div>`;
                    
                    // Auto-select first 4 numeric tags
                    if (defaultSelectedTags.length < 4 && typeof tag.value === 'number') {
                        defaultSelectedTags.push(name);
                        selectedTags.add(name);
                    }
                }
                
                tagList.innerHTML = html;
            } catch (e) {
                console.error('Error fetching tags:', e);
            }
        }
        
        function toggleTag(tagName) {
            if (selectedTags.has(tagName)) {
                selectedTags.delete(tagName);
                // Remove chart
                if (charts[tagName]) {
                    charts[tagName].destroy();
                    delete charts[tagName];
                }
            } else {
                selectedTags.add(tagName);
            }
            updateSelectedTrendsCharts();
            updateTags();
        }
        
        async function updateSelectedTrendsCharts() {
            const container = document.getElementById('selectedTrends');
            
            for (const tagName of selectedTags) {
                try {
                    const response = await fetch(`/api/trends/${encodeURIComponent(tagName)}`);
                    const data = await response.json();
                    
                    if (!data.points || data.points.length === 0) continue;
                    
                    // Create or update chart
                    let chartDiv = document.getElementById(`chart-${tagName}`);
                    if (!chartDiv) {
                        chartDiv = document.createElement('div');
                        chartDiv.id = `chart-${tagName}`;
                        chartDiv.className = 'chart-card';
                        chartDiv.innerHTML = `
                            <div class="title">
                                <span>${tagName}</span>
                                <span class="scan-rate">${data.scanRateMs || 1000}ms scan</span>
                            </div>
                            <div class="chart-wrapper">
                                <canvas id="canvas-${tagName}"></canvas>
                            </div>
                        `;
                        container.appendChild(chartDiv);
                        
                        // Create chart
                        const ctx = document.getElementById(`canvas-${tagName}`).getContext('2d');
                        const colorIndex = Array.from(selectedTags).indexOf(tagName) % chartColors.length;
                        
                        charts[tagName] = new Chart(ctx, {
                            type: 'line',
                            data: {
                                datasets: [{
                                    label: tagName,
                                    data: data.points.map(p => ({
                                        x: new Date(p.timestamp),
                                        y: p.value
                                    })),
                                    borderColor: chartColors[colorIndex],
                                    backgroundColor: chartColors[colorIndex] + '20',
                                    borderWidth: 2,
                                    fill: true,
                                    tension: 0.3,
                                    pointRadius: 0
                                }]
                            },
                            options: {
                                responsive: true,
                                maintainAspectRatio: false,
                                animation: { duration: 0 },
                                scales: {
                                    x: {
                                        type: 'time',
                                        time: { unit: 'second' },
                                        grid: { color: '#1e3a5f' },
                                        ticks: { color: '#90caf9', maxTicksLimit: 5 }
                                    },
                                    y: {
                                        grid: { color: '#1e3a5f' },
                                        ticks: { color: '#90caf9' }
                                    }
                                },
                                plugins: {
                                    legend: { display: false }
                                }
                            }
                        });
                    } else {
                        // Update existing chart
                        if (charts[tagName]) {
                            charts[tagName].data.datasets[0].data = data.points.map(p => ({
                                x: new Date(p.timestamp),
                                y: p.value
                            }));
                            charts[tagName].update('none');
                        }
                    }
                } catch (e) {
                    console.error(`Error updating trend for ${tagName}:`, e);
                }
            }
            
            // Remove charts for unselected tags
            const existingCharts = container.querySelectorAll('.chart-card');
            existingCharts.forEach(div => {
                const tagName = div.id.replace('chart-', '');
                if (!selectedTags.has(tagName)) {
                    if (charts[tagName]) {
                        charts[tagName].destroy();
                        delete charts[tagName];
                    }
                    div.remove();
                }
            });
        }
        
        async function updateAllTrendsCharts() {
            if (currentTab !== 'all') return;
            
            try {
                const response = await fetch('/api/trends');
                const allTrends = await response.json();
                
                const container = document.getElementById('allTrends');
                
                let colorIndex = 0;
                for (const [tagName, trendData] of Object.entries(allTrends)) {
                    if (!trendData.points || trendData.points.length === 0) continue;
                    
                    const chartId = `all-chart-${tagName}`;
                    let chartDiv = document.getElementById(chartId);
                    
                    if (!chartDiv) {
                        chartDiv = document.createElement('div');
                        chartDiv.id = chartId;
                        chartDiv.className = 'chart-card';
                        chartDiv.innerHTML = `
                            <div class="title">
                                <span>${tagName}</span>
                                <span class="scan-rate">${trendData.scanRateMs || 1000}ms</span>
                            </div>
                            <div class="chart-wrapper">
                                <canvas id="all-canvas-${tagName}"></canvas>
                            </div>
                        `;
                        container.appendChild(chartDiv);
                        
                        const ctx = document.getElementById(`all-canvas-${tagName}`).getContext('2d');
                        const color = chartColors[colorIndex % chartColors.length];
                        
                        charts[`all-${tagName}`] = new Chart(ctx, {
                            type: 'line',
                            data: {
                                datasets: [{
                                    data: trendData.points.map(p => ({
                                        x: new Date(p.timestamp),
                                        y: p.value
                                    })),
                                    borderColor: color,
                                    backgroundColor: color + '20',
                                    borderWidth: 1.5,
                                    fill: true,
                                    tension: 0.3,
                                    pointRadius: 0
                                }]
                            },
                            options: {
                                responsive: true,
                                maintainAspectRatio: false,
                                animation: { duration: 0 },
                                scales: {
                                    x: {
                                        type: 'time',
                                        display: false
                                    },
                                    y: {
                                        grid: { color: '#1e3a5f' },
                                        ticks: { color: '#90caf9', maxTicksLimit: 3 }
                                    }
                                },
                                plugins: { legend: { display: false } }
                            }
                        });
                    } else {
                        if (charts[`all-${tagName}`]) {
                            charts[`all-${tagName}`].data.datasets[0].data = trendData.points.map(p => ({
                                x: new Date(p.timestamp),
                                y: p.value
                            }));
                            charts[`all-${tagName}`].update('none');
                        }
                    }
                    colorIndex++;
                }
            } catch (e) {
                console.error('Error updating all trends:', e);
            }
        }
        
        // Initial load and periodic updates
        async function init() {
            await updateTags();
            await updateMqttStats();
            await updatePlcHealth();
            await updateSelectedTrendsCharts();
            
            // Update every 500ms for real-time feel
            setInterval(updateMqttStats, 500);
            setInterval(updateTags, 1000);
            setInterval(updatePlcHealth, 2000);
            setInterval(() => {
                if (currentTab === 'selected') {
                    updateSelectedTrendsCharts();
                } else {
                    updateAllTrendsCharts();
                }
            }, 500);
        }
        
        init();
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("PLC Health & Trends HMI")
    print("=" * 60)
    print(f"MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"API Base: {API_BASE}")
    print(f"HMI URL: http://localhost:5003")
    print("=" * 60)
    
    # Connect to MQTT
    mqtt_connect()
    
    # Start health checker thread
    health_thread = threading.Thread(target=check_plc_health, daemon=True)
    health_thread.start()
    
    # Start Flask
    app.run(host='0.0.0.0', port=5003, debug=False, threaded=True)
