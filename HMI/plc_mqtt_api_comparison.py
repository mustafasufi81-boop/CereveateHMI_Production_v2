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

# Locks for thread safety
mqtt_lock = threading.Lock()
api_lock = threading.Lock()

# ============================================================================
# MQTT CLIENT
# ============================================================================

def on_mqtt_connect(client, userdata, flags, rc, properties=None):
    global mqtt_data
    if rc == 0:
        print("[MQTT] Connected to broker")
        client.subscribe('plc/#')
        with mqtt_lock:
            mqtt_data['connected'] = True
    else:
        print(f"[MQTT] Connection failed: {rc}")

def on_mqtt_disconnect(client, userdata, rc, properties=None, reason_code=None):
    global mqtt_data
    print(f"[MQTT] Disconnected")
    with mqtt_lock:
        mqtt_data['connected'] = False

def on_mqtt_message(client, userdata, msg):
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
        
        with mqtt_lock:
            mqtt_data['timestamp'] = datetime.now().isoformat()
            mqtt_data['latency_ms'] = round(latency_ms, 2)
            mqtt_data['update_count'] += 1
            mqtt_data['last_update'] = receive_time
            
            # Process values
            values = payload.get('values', [])
            if isinstance(payload, list):
                values = payload
            
            for tag in values:
                tag_name = tag.get('tag') or tag.get('tagName', 'unknown')
                value = tag.get('value')
                
                mqtt_data['values'][tag_name] = {
                    'value': value,
                    'quality': tag.get('quality', 'Unknown'),
                    'dataType': tag.get('dataType', 'unknown'),
                    'timestamp': tag.get('timestamp', '')
                }
                
                # Add to history
                if tag_name not in mqtt_data['history']:
                    mqtt_data['history'][tag_name] = deque(maxlen=MAX_HISTORY)
                
                if isinstance(value, (int, float)):
                    mqtt_data['history'][tag_name].append({
                        'time': datetime.now().isoformat(),
                        'value': value
                    })
    except Exception as e:
        print(f"[MQTT] Error processing message: {e}")

def start_mqtt_client():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, 'hmi_mqtt_viewer')
    client.on_connect = on_mqtt_connect
    client.on_disconnect = on_mqtt_disconnect
    client.on_message = on_mqtt_message
    
    try:
        client.connect('localhost', 1883, 60)
        client.loop_forever()
    except Exception as e:
        print(f"[MQTT] Failed to connect: {e}")

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
    </style>
</head>
<body>
    <div class="header">
        <h1>🏭 PLC Data Viewer - MQTT vs REST API</h1>
        <p>Real-time comparison of data sources | Rockwell PLC @ 192.168.0.20</p>
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
    print("HMI URL: http://localhost:5002")
    print("=" * 60)
    
    # Start MQTT client thread
    mqtt_thread = threading.Thread(target=start_mqtt_client, daemon=True)
    mqtt_thread.start()
    
    # Start API poller thread
    api_thread = threading.Thread(target=poll_api, daemon=True)
    api_thread.start()
    
    # Give threads time to start
    time.sleep(1)
    
    # Start Flask
    app.run(host='0.0.0.0', port=5002, debug=False, threaded=True)
