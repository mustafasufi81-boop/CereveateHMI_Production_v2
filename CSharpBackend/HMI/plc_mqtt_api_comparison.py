"""
PLC Data Viewer - MQTT vs API Performance Comparison
=====================================================
This HMI shows real-time PLC data from two sources:
1. MQTT (localhost:1883, topic: plc/plc/all)
2. REST API (http://localhost:5001/api/plc/values)

Features:
- Side-by-side comparison of both data sources
- Real-time trend charts (last 60 seconds)
- Performance metrics (latency, update rate)
- Tag value tables with quality indicators
- PLC Health monitoring panel

Run: python plc_mqtt_api_comparison.py
Open: http://localhost:5002
"""

from flask import Flask, render_template_string, jsonify
import threading
import time
import json
import requests
from datetime import datetime
from collections import deque
import paho.mqtt.client as mqtt

app = Flask(__name__)

# ============================================================================
# DATA STORES
# ============================================================================

# Store last 60 seconds of data (60 samples at 1 second interval)
MAX_HISTORY = 60

# MQTT Data Store
mqtt_data = {
    'values': {},
    'timestamp': None,
    'latency_ms': 0,
    'update_count': 0,
    'history': {},  # tag -> deque of (timestamp, value)
    'connected': False,
    'last_update': None
}

# API Data Store
api_data = {
    'values': {},
    'timestamp': None,
    'latency_ms': 0,
    'update_count': 0,
    'history': {},  # tag -> deque of (timestamp, value)
    'last_update': None
}

# PLC Health Data Store
plc_health_data = {
    'status': 'unknown',
    'timestamp': None,
    'totalPlcs': 0,
    'connectedPlcs': 0,
    'healthyPlcs': 0,
    'faultedPlcs': 0,
    'workers': [],
    'last_update': None
}

# Locks for thread safety
mqtt_lock = threading.Lock()
api_lock = threading.Lock()
health_lock = threading.Lock()

# ============================================================================
# MQTT CLIENT
# ============================================================================

def on_mqtt_connect(client, userdata, flags, rc):
    """MQTT connect callback - using older stable API"""
    global mqtt_data
    if rc == 0:
        print("[MQTT] Connected to broker")
        client.subscribe('plc/#', qos=1)
        with mqtt_lock:
            mqtt_data['connected'] = True
    else:
        print(f"[MQTT] Connection failed: {rc}")

def on_mqtt_disconnect(client, userdata, rc):
    """MQTT disconnect callback - using older stable API"""
    global mqtt_data
    print(f"[MQTT] Disconnected (rc={rc})")
    with mqtt_lock:
        mqtt_data['connected'] = False

def on_mqtt_message(client, userdata, msg):
    """
    Handle MQTT message - DYNAMIC format support
    
    Supports both formats:
    1. Legacy: Single value per tag (value field)
    2. New: Multiple samples per tag (samples array)
    
    New format example:
    {
        "publishIntervalMs": 1000,
        "tagCount": 32,
        "totalSamples": 160,
        "values": [
            {
                "tag": "Pump_RPM",
                "scanRateMs": 200,
                "sampleCount": 5,
                "samples": [
                    {"value": 74.5, "quality": "Good", "timestamp": "..."},
                    ...
                ],
                "value": 74.6  // Latest value for backward compatibility
            }
        ]
    }
    """
    global mqtt_data
    receive_time = time.time()
    
    try:
        payload = json.loads(msg.payload.decode())
        
        # Calculate latency from message timestamp
        msg_timestamp = payload.get('timestamp', '')
        if msg_timestamp:
            try:
                # Parse ISO timestamp
                msg_time = datetime.fromisoformat(msg_timestamp.replace('Z', '+00:00'))
                latency_ms = (receive_time - msg_time.timestamp()) * 1000
            except:
                latency_ms = 0
        else:
            latency_ms = 0
        
        # Extract dynamic metadata
        publish_interval_ms = payload.get('publishIntervalMs', 1000)
        total_samples = payload.get('totalSamples', payload.get('count', 0))
        
        with mqtt_lock:
            mqtt_data['timestamp'] = datetime.now().isoformat()
            mqtt_data['latency_ms'] = round(latency_ms, 2)
            mqtt_data['update_count'] += 1
            mqtt_data['last_update'] = receive_time
            mqtt_data['publish_interval_ms'] = publish_interval_ms
            mqtt_data['total_samples'] = total_samples
            
            # Process values
            values = payload.get('values', [])
            if isinstance(payload, list):
                values = payload
            
            for tag in values:
                tag_name = tag.get('tag') or tag.get('tagName', 'unknown')
                
                # DYNAMIC: Check if tag has samples array (new format)
                samples = tag.get('samples', [])
                scan_rate_ms = tag.get('scanRateMs', 1000)
                sample_count = tag.get('sampleCount', len(samples) if samples else 1)
                
                # Get latest value (for display) - works with both formats
                if samples:
                    # New format: Use last sample as current value
                    latest_sample = samples[-1] if samples else {}
                    value = latest_sample.get('value')
                    quality = latest_sample.get('quality', 'Unknown')
                    timestamp = latest_sample.get('timestamp', '')
                else:
                    # Legacy format: Single value
                    value = tag.get('value')
                    quality = tag.get('quality', 'Unknown')
                    timestamp = tag.get('timestamp', '')
                
                mqtt_data['values'][tag_name] = {
                    'value': value,
                    'quality': quality,
                    'dataType': tag.get('dataType', 'unknown'),
                    'timestamp': timestamp,
                    'scanRateMs': scan_rate_ms,
                    'sampleCount': sample_count,
                    'samples': samples  # Keep all samples for detailed view
                }
                
                # Add ALL samples to history (not just latest)
                if tag_name not in mqtt_data['history']:
                    mqtt_data['history'][tag_name] = deque(maxlen=MAX_HISTORY * 10)  # More space for samples
                
                if samples:
                    # Add each sample to history
                    for sample in samples:
                        sample_value = sample.get('value')
                        if isinstance(sample_value, (int, float)):
                            mqtt_data['history'][tag_name].append({
                                'time': sample.get('timestamp', datetime.now().isoformat()),
                                'value': sample_value
                            })
                elif isinstance(value, (int, float)):
                    # Legacy: single value
                    mqtt_data['history'][tag_name].append({
                        'time': datetime.now().isoformat(),
                        'value': value
                    })
                    
    except Exception as e:
        print(f"[MQTT] Error processing message: {e}")

def start_mqtt_client():
    """
    MQTT client with robust reconnection logic
    - Uses stable older API (not VERSION2)
    - Auto-reconnects on disconnect
    - Maintains consistent connection
    """
    reconnect_delay = 1  # Start with 1 second
    max_reconnect_delay = 30  # Max 30 seconds between retries
    
    while True:
        try:
            # Use older stable API (no VERSION2) - matches working test_mqtt_subscribe.py
            client = mqtt.Client(client_id='hmi_mqtt_viewer', clean_session=True)
            client.on_connect = on_mqtt_connect
            client.on_disconnect = on_mqtt_disconnect
            client.on_message = on_mqtt_message
            
            # Enable automatic reconnection
            client.reconnect_delay_set(min_delay=1, max_delay=30)
            
            print(f"[MQTT] Connecting to localhost:1883...")
            client.connect('localhost', 1883, keepalive=60)
            
            # Reset delay on successful connection
            reconnect_delay = 1
            
            # This blocks and handles reconnection internally
            client.loop_forever(retry_first_connection=True)
            
        except ConnectionRefusedError:
            print(f"[MQTT] Connection refused - broker may not be running. Retry in {reconnect_delay}s...")
        except Exception as e:
            print(f"[MQTT] Connection error: {e}. Retry in {reconnect_delay}s...")
        
        # Wait before reconnecting with exponential backoff
        time.sleep(reconnect_delay)
        reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)

# ============================================================================
# API POLLER
# ============================================================================

def poll_api():
    global api_data
    api_url = 'http://localhost:5001/api/plc/values'
    
    while True:
        start_time = time.time()
        try:
            response = requests.get(api_url, timeout=5)
            latency_ms = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                data = response.json()
                
                with api_lock:
                    api_data['timestamp'] = datetime.now().isoformat()
                    api_data['latency_ms'] = round(latency_ms, 2)
                    api_data['update_count'] += 1
                    api_data['last_update'] = time.time()
                    
                    values = data.get('values', [])
                    for tag in values:
                        tag_name = tag.get('tagName', 'unknown')
                        value = tag.get('value')
                        
                        api_data['values'][tag_name] = {
                            'value': value,
                            'quality': tag.get('quality', 'Unknown'),
                            'dataType': tag.get('dataType', 'unknown'),
                            'timestamp': tag.get('timestamp', '')
                        }
                        
                        # Add to history
                        if tag_name not in api_data['history']:
                            api_data['history'][tag_name] = deque(maxlen=MAX_HISTORY)
                        
                        if isinstance(value, (int, float)):
                            api_data['history'][tag_name].append({
                                'time': datetime.now().isoformat(),
                                'value': value
                            })
        except Exception as e:
            print(f"[API] Error: {e}")
        
        time.sleep(1)  # Poll every second

# ============================================================================
# PLC HEALTH POLLER
# ============================================================================

def poll_plc_health():
    """Poll PLC Gateway health and worker status"""
    global plc_health_data
    health_url = 'http://localhost:5001/api/plc/health'
    status_url = 'http://localhost:5001/api/plc/status'
    
    while True:
        try:
            # Get health status
            health_response = requests.get(health_url, timeout=5)
            if health_response.status_code == 200:
                health = health_response.json()
                
                with health_lock:
                    plc_health_data['status'] = health.get('status', 'unknown')
                    plc_health_data['timestamp'] = health.get('timestamp')
                    plc_health_data['totalPlcs'] = health.get('totalPlcs', 0)
                    plc_health_data['connectedPlcs'] = health.get('connectedPlcs', 0)
                    plc_health_data['healthyPlcs'] = health.get('healthyPlcs', 0)
                    plc_health_data['faultedPlcs'] = health.get('faultedPlcs', 0)
                    plc_health_data['last_update'] = time.time()
            
            # Get detailed worker status
            status_response = requests.get(status_url, timeout=5)
            if status_response.status_code == 200:
                status = status_response.json()
                
                with health_lock:
                    plc_health_data['workers'] = status.get('workers', [])
                    plc_health_data['summary'] = status.get('summary', {})
                    
        except Exception as e:
            print(f"[HEALTH] Error polling PLC health: {e}")
            with health_lock:
                plc_health_data['status'] = 'error'
        
        time.sleep(2)  # Poll every 2 seconds

# ============================================================================
# FLASK ROUTES
# ============================================================================

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/mqtt/data')
def get_mqtt_data():
    with mqtt_lock:
        return jsonify({
            'values': mqtt_data['values'],
            'timestamp': mqtt_data['timestamp'],
            'latency_ms': mqtt_data['latency_ms'],
            'update_count': mqtt_data['update_count'],
            'connected': mqtt_data['connected'],
            'tag_count': len(mqtt_data['values'])
        })

@app.route('/api/api/data')
def get_api_data():
    with api_lock:
        return jsonify({
            'values': api_data['values'],
            'timestamp': api_data['timestamp'],
            'latency_ms': api_data['latency_ms'],
            'update_count': api_data['update_count'],
            'tag_count': len(api_data['values'])
        })

@app.route('/api/mqtt/history/<tag_name>')
def get_mqtt_history(tag_name):
    with mqtt_lock:
        history = list(mqtt_data['history'].get(tag_name, []))
        return jsonify({'tag': tag_name, 'history': history})

@app.route('/api/api/history/<tag_name>')
def get_api_history(tag_name):
    with api_lock:
        history = list(api_data['history'].get(tag_name, []))
        return jsonify({'tag': tag_name, 'history': history})

@app.route('/api/tags')
def get_tags():
    """Get list of all available tags"""
    with mqtt_lock:
        mqtt_tags = list(mqtt_data['values'].keys())
    with api_lock:
        api_tags = list(api_data['values'].keys())
    
    all_tags = list(set(mqtt_tags + api_tags))
    all_tags.sort()
    return jsonify({'tags': all_tags})

@app.route('/api/plc/health')
def get_plc_health():
    """Get PLC health and worker status"""
    with health_lock:
        return jsonify({
            'status': plc_health_data['status'],
            'timestamp': plc_health_data['timestamp'],
            'totalPlcs': plc_health_data['totalPlcs'],
            'connectedPlcs': plc_health_data['connectedPlcs'],
            'healthyPlcs': plc_health_data['healthyPlcs'],
            'faultedPlcs': plc_health_data['faultedPlcs'],
            'workers': plc_health_data['workers'],
            'summary': plc_health_data.get('summary', {})
        })

# ============================================================================
# HTML TEMPLATE
# ============================================================================

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>PLC HMI - MQTT vs API Comparison</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            background: #1a1a2e; 
            color: #eee;
            padding: 10px;
        }
        .header {
            text-align: center;
            padding: 15px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 10px;
            margin-bottom: 15px;
        }
        .header h1 { font-size: 24px; }
        .header p { opacity: 0.8; font-size: 14px; }
        
        .container { display: flex; gap: 15px; }
        .panel {
            flex: 1;
            background: #16213e;
            border-radius: 10px;
            padding: 15px;
            border: 1px solid #0f3460;
        }
        .panel-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 10px;
            border-bottom: 1px solid #0f3460;
            margin-bottom: 10px;
        }
        .panel-title {
            font-size: 18px;
            font-weight: bold;
        }
        .mqtt-title { color: #00d9ff; }
        .api-title { color: #00ff88; }
        
        .status-badge {
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
        }
        .status-connected { background: #00ff88; color: #000; }
        .status-disconnected { background: #ff4444; color: #fff; }
        
        .metrics {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            margin-bottom: 15px;
        }
        .metric {
            background: #0f3460;
            padding: 10px;
            border-radius: 8px;
            text-align: center;
        }
        .metric-value {
            font-size: 24px;
            font-weight: bold;
        }
        .metric-label {
            font-size: 11px;
            opacity: 0.7;
            margin-top: 3px;
        }
        .mqtt-value { color: #00d9ff; }
        .api-value { color: #00ff88; }
        
        .chart-container {
            background: #0f3460;
            border-radius: 8px;
            padding: 10px;
            margin-bottom: 15px;
            height: 200px;
        }
        
        .tag-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
        }
        .tag-table th, .tag-table td {
            padding: 8px;
            text-align: left;
            border-bottom: 1px solid #0f3460;
        }
        .tag-table th {
            background: #0f3460;
            position: sticky;
            top: 0;
        }
        .tag-table-container {
            max-height: 300px;
            overflow-y: auto;
        }
        .quality-good { color: #00ff88; }
        .quality-bad { color: #ff4444; }
        
        .tag-select {
            margin-bottom: 10px;
        }
        .tag-select select {
            width: 100%;
            padding: 8px;
            background: #0f3460;
            border: 1px solid #667eea;
            color: #fff;
            border-radius: 5px;
        }
        
        .comparison-row {
            display: flex;
            gap: 15px;
            margin-top: 15px;
        }
        .comparison-chart {
            flex: 1;
            background: #16213e;
            border-radius: 10px;
            padding: 15px;
            border: 1px solid #0f3460;
        }
        .comparison-chart h3 {
            margin-bottom: 10px;
            color: #667eea;
        }
        
        /* PLC Health Panel Styles */
        .health-panel {
            background: #16213e;
            border-radius: 10px;
            padding: 15px;
            border: 1px solid #0f3460;
            margin-bottom: 15px;
        }
        .health-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 10px;
            border-bottom: 1px solid #0f3460;
            margin-bottom: 10px;
        }
        .health-title {
            font-size: 18px;
            font-weight: bold;
            color: #ffa500;
        }
        .health-metrics {
            display: flex;
            gap: 20px;
            margin-bottom: 15px;
        }
        .health-metric {
            background: #0f3460;
            padding: 10px 20px;
            border-radius: 8px;
            text-align: center;
            min-width: 100px;
        }
        .health-value {
            font-size: 28px;
            font-weight: bold;
            color: #fff;
        }
        .health-value.connected { color: #00d9ff; }
        .health-value.healthy { color: #00ff88; }
        .health-value.faulted { color: #ff4444; }
        .health-label {
            font-size: 11px;
            opacity: 0.7;
            margin-top: 3px;
        }
        .workers-container {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }
        .worker-card {
            background: #0f3460;
            border-radius: 8px;
            padding: 12px;
            min-width: 280px;
            flex: 1;
            max-width: 350px;
        }
        .worker-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }
        .worker-name {
            font-weight: bold;
            color: #fff;
        }
        .worker-protocol {
            font-size: 11px;
            background: #667eea;
            padding: 2px 8px;
            border-radius: 10px;
        }
        .worker-info {
            font-size: 12px;
            color: #aaa;
        }
        .worker-info div {
            margin: 3px 0;
        }
        .worker-stat {
            display: inline-block;
            margin-right: 15px;
        }
        .worker-stat-label {
            opacity: 0.7;
        }
        .worker-stat-value {
            font-weight: bold;
        }
        .worker-state-running { color: #00ff88; }
        .worker-state-connecting { color: #ffa500; }
        .worker-state-disconnected { color: #ff4444; }
        .worker-state-faulted { color: #ff0000; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🏭 PLC Data Viewer - MQTT vs REST API</h1>
        <p>Real-time comparison of data sources | Rockwell PLC @ 192.168.0.20</p>
    </div>
    
    <!-- PLC Health Panel -->
    <div class="health-panel">
        <div class="health-header">
            <span class="health-title">🔌 PLC Gateway Health</span>
            <span id="plc-health-status" class="status-badge status-disconnected">Unknown</span>
        </div>
        <div class="health-metrics">
            <div class="health-metric">
                <div class="health-value" id="total-plcs">0</div>
                <div class="health-label">Total PLCs</div>
            </div>
            <div class="health-metric">
                <div class="health-value connected" id="connected-plcs">0</div>
                <div class="health-label">Connected</div>
            </div>
            <div class="health-metric">
                <div class="health-value healthy" id="healthy-plcs">0</div>
                <div class="health-label">Healthy</div>
            </div>
            <div class="health-metric">
                <div class="health-value faulted" id="faulted-plcs">0</div>
                <div class="health-label">Faulted</div>
            </div>
        </div>
        <div id="workers-container" class="workers-container"></div>
    </div>
    
    <div class="container">
        <!-- MQTT Panel -->
        <div class="panel">
            <div class="panel-header">
                <span class="panel-title mqtt-title">📡 MQTT (Push)</span>
                <span id="mqtt-status" class="status-badge status-disconnected">Disconnected</span>
            </div>
            <div class="metrics">
                <div class="metric">
                    <div class="metric-value mqtt-value" id="mqtt-latency">--</div>
                    <div class="metric-label">Latency (ms)</div>
                </div>
                <div class="metric">
                    <div class="metric-value mqtt-value" id="mqtt-updates">0</div>
                    <div class="metric-label">Updates</div>
                </div>
                <div class="metric">
                    <div class="metric-value mqtt-value" id="mqtt-tags">0</div>
                    <div class="metric-label">Tags</div>
                </div>
            </div>
            <div class="tag-select">
                <select id="mqtt-tag-select" onchange="updateMqttChart()">
                    <option value="">Select tag for trend...</option>
                </select>
            </div>
            <div class="chart-container">
                <canvas id="mqtt-chart"></canvas>
            </div>
            <div class="tag-table-container">
                <table class="tag-table">
                    <thead>
                        <tr><th>Tag</th><th>Value</th><th>Quality</th></tr>
                    </thead>
                    <tbody id="mqtt-table-body"></tbody>
                </table>
            </div>
        </div>
        
        <!-- API Panel -->
        <div class="panel">
            <div class="panel-header">
                <span class="panel-title api-title">🔗 REST API (Poll)</span>
                <span class="status-badge status-connected">Active</span>
            </div>
            <div class="metrics">
                <div class="metric">
                    <div class="metric-value api-value" id="api-latency">--</div>
                    <div class="metric-label">Latency (ms)</div>
                </div>
                <div class="metric">
                    <div class="metric-value api-value" id="api-updates">0</div>
                    <div class="metric-label">Updates</div>
                </div>
                <div class="metric">
                    <div class="metric-value api-value" id="api-tags">0</div>
                    <div class="metric-label">Tags</div>
                </div>
            </div>
            <div class="tag-select">
                <select id="api-tag-select" onchange="updateApiChart()">
                    <option value="">Select tag for trend...</option>
                </select>
            </div>
            <div class="chart-container">
                <canvas id="api-chart"></canvas>
            </div>
            <div class="tag-table-container">
                <table class="tag-table">
                    <thead>
                        <tr><th>Tag</th><th>Value</th><th>Quality</th></tr>
                    </thead>
                    <tbody id="api-table-body"></tbody>
                </table>
            </div>
        </div>
    </div>
    
    <div class="comparison-row">
        <div class="comparison-chart">
            <h3>📊 Latency Comparison (Last 60 Updates)</h3>
            <div style="height: 150px;">
                <canvas id="latency-chart"></canvas>
            </div>
        </div>
    </div>

    <script>
        // Chart configurations
        const chartConfig = {
            type: 'line',
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                scales: {
                    x: { display: false },
                    y: { 
                        grid: { color: '#0f3460' },
                        ticks: { color: '#888' }
                    }
                },
                plugins: { legend: { display: false } }
            }
        };
        
        // Initialize charts
        const mqttChart = new Chart(document.getElementById('mqtt-chart'), {
            ...chartConfig,
            data: {
                labels: [],
                datasets: [{
                    data: [],
                    borderColor: '#00d9ff',
                    backgroundColor: 'rgba(0, 217, 255, 0.1)',
                    fill: true,
                    tension: 0.3
                }]
            }
        });
        
        const apiChart = new Chart(document.getElementById('api-chart'), {
            ...chartConfig,
            data: {
                labels: [],
                datasets: [{
                    data: [],
                    borderColor: '#00ff88',
                    backgroundColor: 'rgba(0, 255, 136, 0.1)',
                    fill: true,
                    tension: 0.3
                }]
            }
        });
        
        const latencyChart = new Chart(document.getElementById('latency-chart'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'MQTT',
                        data: [],
                        borderColor: '#00d9ff',
                        tension: 0.3
                    },
                    {
                        label: 'API',
                        data: [],
                        borderColor: '#00ff88',
                        tension: 0.3
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                scales: {
                    x: { display: false },
                    y: { 
                        grid: { color: '#0f3460' },
                        ticks: { color: '#888' },
                        title: { display: true, text: 'ms', color: '#888' }
                    }
                },
                plugins: {
                    legend: { 
                        position: 'top',
                        labels: { color: '#888' }
                    }
                }
            }
        });
        
        // Latency history
        const latencyHistory = { mqtt: [], api: [], labels: [] };
        const MAX_LATENCY_HISTORY = 60;
        
        // Tag lists populated
        let tagsPopulated = false;
        
        // Fetch and update data
        async function fetchMqttData() {
            try {
                const response = await fetch('/api/mqtt/data');
                const data = await response.json();
                
                // Update metrics
                document.getElementById('mqtt-latency').textContent = data.latency_ms || '--';
                document.getElementById('mqtt-updates').textContent = data.update_count;
                document.getElementById('mqtt-tags').textContent = data.tag_count;
                
                // Update status
                const statusEl = document.getElementById('mqtt-status');
                if (data.connected) {
                    statusEl.textContent = 'Connected';
                    statusEl.className = 'status-badge status-connected';
                } else {
                    statusEl.textContent = 'Disconnected';
                    statusEl.className = 'status-badge status-disconnected';
                }
                
                // Update table
                const tbody = document.getElementById('mqtt-table-body');
                tbody.innerHTML = '';
                const tags = Object.keys(data.values).sort();
                tags.forEach(tag => {
                    const v = data.values[tag];
                    const tr = document.createElement('tr');
                    const qualityClass = v.quality === 'Good' ? 'quality-good' : 'quality-bad';
                    tr.innerHTML = `
                        <td>${tag}</td>
                        <td>${formatValue(v.value)}</td>
                        <td class="${qualityClass}">${v.quality}</td>
                    `;
                    tbody.appendChild(tr);
                });
                
                // Populate tag select if needed
                if (!tagsPopulated && tags.length > 0) {
                    populateTagSelects(tags);
                    tagsPopulated = true;
                }
                
                // Update latency history
                latencyHistory.mqtt.push(data.latency_ms || 0);
                if (latencyHistory.mqtt.length > MAX_LATENCY_HISTORY) {
                    latencyHistory.mqtt.shift();
                }
                
            } catch (e) {
                console.error('MQTT fetch error:', e);
            }
        }
        
        async function fetchApiData() {
            try {
                const response = await fetch('/api/api/data');
                const data = await response.json();
                
                // Update metrics
                document.getElementById('api-latency').textContent = data.latency_ms || '--';
                document.getElementById('api-updates').textContent = data.update_count;
                document.getElementById('api-tags').textContent = data.tag_count;
                
                // Update table
                const tbody = document.getElementById('api-table-body');
                tbody.innerHTML = '';
                const tags = Object.keys(data.values).sort();
                tags.forEach(tag => {
                    const v = data.values[tag];
                    const tr = document.createElement('tr');
                    const qualityClass = v.quality === 'Good' ? 'quality-good' : 'quality-bad';
                    tr.innerHTML = `
                        <td>${tag}</td>
                        <td>${formatValue(v.value)}</td>
                        <td class="${qualityClass}">${v.quality}</td>
                    `;
                    tbody.appendChild(tr);
                });
                
                // Update latency history
                latencyHistory.api.push(data.latency_ms || 0);
                latencyHistory.labels.push('');
                if (latencyHistory.api.length > MAX_LATENCY_HISTORY) {
                    latencyHistory.api.shift();
                    latencyHistory.labels.shift();
                }
                
                // Update latency comparison chart
                latencyChart.data.labels = latencyHistory.labels;
                latencyChart.data.datasets[0].data = latencyHistory.mqtt;
                latencyChart.data.datasets[1].data = latencyHistory.api;
                latencyChart.update('none');
                
            } catch (e) {
                console.error('API fetch error:', e);
            }
        }
        
        function formatValue(val) {
            if (typeof val === 'boolean') return val ? 'TRUE' : 'FALSE';
            if (typeof val === 'number') return val.toFixed(2);
            return val;
        }
        
        function populateTagSelects(tags) {
            const mqttSelect = document.getElementById('mqtt-tag-select');
            const apiSelect = document.getElementById('api-tag-select');
            
            // Filter numeric tags only
            tags.forEach(tag => {
                const opt1 = document.createElement('option');
                opt1.value = tag;
                opt1.textContent = tag;
                mqttSelect.appendChild(opt1);
                
                const opt2 = document.createElement('option');
                opt2.value = tag;
                opt2.textContent = tag;
                apiSelect.appendChild(opt2);
            });
            
            // Select first numeric tag
            if (tags.length > 0) {
                mqttSelect.value = tags[0];
                apiSelect.value = tags[0];
                updateMqttChart();
                updateApiChart();
            }
        }
        
        async function updateMqttChart() {
            const tag = document.getElementById('mqtt-tag-select').value;
            if (!tag) return;
            
            try {
                const response = await fetch(`/api/mqtt/history/${encodeURIComponent(tag)}`);
                const data = await response.json();
                
                const labels = data.history.map(h => new Date(h.time).toLocaleTimeString());
                const values = data.history.map(h => h.value);
                
                mqttChart.data.labels = labels;
                mqttChart.data.datasets[0].data = values;
                mqttChart.update('none');
            } catch (e) {
                console.error('MQTT history error:', e);
            }
        }
        
        async function updateApiChart() {
            const tag = document.getElementById('api-tag-select').value;
            if (!tag) return;
            
            try {
                const response = await fetch(`/api/api/history/${encodeURIComponent(tag)}`);
                const data = await response.json();
                
                const labels = data.history.map(h => new Date(h.time).toLocaleTimeString());
                const values = data.history.map(h => h.value);
                
                apiChart.data.labels = labels;
                apiChart.data.datasets[0].data = values;
                apiChart.update('none');
            } catch (e) {
                console.error('API history error:', e);
            }
        }
        
        // Main update loop
        setInterval(() => {
            fetchMqttData();
            fetchApiData();
            updateMqttChart();
            updateApiChart();
        }, 1000);
        
        // Initial fetch
        fetchMqttData();
        fetchApiData();
        fetchPlcHealth();
        
        // Fetch PLC Health
        async function fetchPlcHealth() {
            try {
                const response = await fetch('/api/plc/health');
                const data = await response.json();
                
                // Update health status badge
                const statusEl = document.getElementById('plc-health-status');
                if (data.status === 'healthy') {
                    statusEl.textContent = 'Healthy';
                    statusEl.className = 'status-badge status-connected';
                } else if (data.status === 'degraded') {
                    statusEl.textContent = 'Degraded';
                    statusEl.className = 'status-badge';
                    statusEl.style.background = '#ffa500';
                } else {
                    statusEl.textContent = data.status || 'Unknown';
                    statusEl.className = 'status-badge status-disconnected';
                }
                
                // Update metrics
                document.getElementById('total-plcs').textContent = data.totalPlcs || 0;
                document.getElementById('connected-plcs').textContent = data.connectedPlcs || 0;
                document.getElementById('healthy-plcs').textContent = data.healthyPlcs || 0;
                document.getElementById('faulted-plcs').textContent = data.faultedPlcs || 0;
                
                // Update workers
                const workersContainer = document.getElementById('workers-container');
                workersContainer.innerHTML = '';
                
                if (data.workers && data.workers.length > 0) {
                    data.workers.forEach(worker => {
                        const stateClass = getStateClass(worker.state);
                        const scanStats = worker.scanRateStats || {};
                        const tagsByRate = scanStats.tagsByRate || {};
                        
                        // Build scan rate breakdown HTML
                        let scanRateHtml = '';
                        if (Object.keys(tagsByRate).length > 0) {
                            const rateItems = Object.entries(tagsByRate)
                                .map(([rate, count]) => `<span style="margin-right:10px;"><b>${count}</b>@${rate}ms</span>`)
                                .join('');
                            scanRateHtml = `
                                <div style="margin-top:5px;padding:5px;background:#1a1a2e;border-radius:4px;">
                                    <div style="font-size:10px;color:#ffa500;margin-bottom:3px;">📊 Scan Rate Distribution:</div>
                                    <div style="font-size:11px;">${rateItems}</div>
                                </div>
                            `;
                        }
                        
                        // Build deadband stats HTML
                        let deadbandHtml = '';
                        if (scanStats.totalScans > 0) {
                            const filterRate = scanStats.totalFiltered > 0 
                                ? Math.round((scanStats.totalFiltered / scanStats.totalScans) * 100) 
                                : 0;
                            deadbandHtml = `
                                <div style="margin-top:5px;padding:5px;background:#1a1a2e;border-radius:4px;">
                                    <div style="font-size:10px;color:#00d9ff;margin-bottom:3px;">🎚️ Deadband Stats:</div>
                                    <div style="font-size:11px;">
                                        <span style="margin-right:10px;">Scans: <b>${scanStats.totalScans || 0}</b></span>
                                        <span style="margin-right:10px;">Cached: <b style="color:#00ff88;">${scanStats.totalCached || 0}</b></span>
                                        <span style="margin-right:10px;">Filtered: <b style="color:#ff8800;">${scanStats.totalFiltered || 0}</b> (${filterRate}%)</span>
                                        <span>Transmitted: <b style="color:#00d9ff;">${scanStats.totalTransmitted || 0}</b></span>
                                    </div>
                                    <div style="font-size:10px;margin-top:3px;">
                                        <span style="margin-right:10px;">With Deadband: ${scanStats.tagsWithDeadband || 0}</span>
                                        <span>Without: ${scanStats.tagsWithoutDeadband || 0}</span>
                                    </div>
                                </div>
                            `;
                        }
                        
                        const card = document.createElement('div');
                        card.className = 'worker-card';
                        card.innerHTML = `
                            <div class="worker-header">
                                <span class="worker-name">${worker.plcName || worker.plcId}</span>
                                <span class="worker-protocol">${worker.protocol || 'Unknown'}</span>
                            </div>
                            <div class="worker-info">
                                <div>
                                    <span class="worker-stat">
                                        <span class="worker-stat-label">State:</span>
                                        <span class="worker-stat-value ${stateClass}">${worker.state || 'Unknown'}</span>
                                    </span>
                                    <span class="worker-stat">
                                        <span class="worker-stat-label">IP:</span>
                                        <span class="worker-stat-value">${worker.ipAddress || 'N/A'}:${worker.port || ''}</span>
                                    </span>
                                    <span class="worker-stat">
                                        <span class="worker-stat-label">Poll Rate:</span>
                                        <span class="worker-stat-value" style="color:#ffa500;">${worker.pollingIntervalMs || 1000}ms</span>
                                    </span>
                                </div>
                                <div>
                                    <span class="worker-stat">
                                        <span class="worker-stat-label">Tags:</span>
                                        <span class="worker-stat-value">${worker.tagCount || 0}</span>
                                    </span>
                                    <span class="worker-stat">
                                        <span class="worker-stat-label">Polls:</span>
                                        <span class="worker-stat-value">${worker.successfulPolls || 0}/${worker.totalPolls || 0}</span>
                                    </span>
                                    <span class="worker-stat">
                                        <span class="worker-stat-label">Avg:</span>
                                        <span class="worker-stat-value">${worker.averageReadTimeMs || 0}ms</span>
                                    </span>
                                </div>
                                ${scanRateHtml}
                                ${deadbandHtml}
                                ${worker.lastError ? `<div style="color:#ff4444;font-size:11px;margin-top:5px;">Error: ${worker.lastError}</div>` : ''}
                            </div>
                        `;
                        workersContainer.appendChild(card);
                    });
                } else {
                    workersContainer.innerHTML = '<div style="color:#888;padding:10px;">No PLC workers configured</div>';
                }
                
            } catch (e) {
                console.error('Health fetch error:', e);
                document.getElementById('plc-health-status').textContent = 'Error';
                document.getElementById('plc-health-status').className = 'status-badge status-disconnected';
            }
        }
        
        function getStateClass(state) {
            if (!state) return '';
            const s = state.toLowerCase();
            if (s === 'running') return 'worker-state-running';
            if (s === 'connecting') return 'worker-state-connecting';
            if (s === 'disconnected') return 'worker-state-disconnected';
            if (s === 'faulted') return 'worker-state-faulted';
            return '';
        }
        
        // Add health polling to main loop
        setInterval(fetchPlcHealth, 2000);
    </script>
</body>
</html>
'''

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("PLC HMI - MQTT vs API Performance Comparison")
    print("=" * 60)
    print("MQTT Broker: localhost:1883")
    print("API Endpoint: http://localhost:5001/api/plc/values")
    print("Health Endpoint: http://localhost:5001/api/plc/health")
    print("HMI URL: http://localhost:5002")
    print("=" * 60)
    
    # Start MQTT client thread
    mqtt_thread = threading.Thread(target=start_mqtt_client, daemon=True)
    mqtt_thread.start()
    
    # Start API poller thread
    api_thread = threading.Thread(target=poll_api, daemon=True)
    api_thread.start()
    
    # Start PLC Health poller thread
    health_thread = threading.Thread(target=poll_plc_health, daemon=True)
    health_thread.start()
    
    # Give threads time to start
    time.sleep(1)
    
    # Start Flask
    app.run(host='0.0.0.0', port=5002, debug=False, threaded=True)
