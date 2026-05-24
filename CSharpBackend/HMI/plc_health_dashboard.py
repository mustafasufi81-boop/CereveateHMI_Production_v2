"""
PLC Health Dashboard with Dial Gauges
=====================================
Displays PLC health metrics from MQTT topic: plc/health

FEATURES:
- Dial gauges for: Latency, Success Rate, Error Count
- Real-time graphs for: Response Time trend, Poll Statistics
- Status indicators for: Connection, Consecutive Failures
- Logs all MQTT data to D:\OpcLogs\MSLog\mslog.txt

MQTT Topic: plc/health (published every 3 seconds)

Run: python plc_health_dashboard.py
Access: http://localhost:5004
"""

from flask import Flask, render_template_string, jsonify
import paho.mqtt.client as mqtt
import json
import threading
import os
from datetime import datetime
from collections import deque

app = Flask(__name__)

# ═══════════════════════════════════════════════════════════════════
# DATA STORAGE
# ═══════════════════════════════════════════════════════════════════
health_data = {
    "timestamp": None,
    "plcCount": 0,
    "connectedCount": 0,
    "disconnectedCount": 0,
    "faultedCount": 0,
    "plcs": []
}

# History for graphs (last 100 readings = ~5 minutes at 3s interval)
history = {
    "timestamps": deque(maxlen=100),
    "latency": deque(maxlen=100),
    "successRate": deque(maxlen=100),
    "totalPolls": deque(maxlen=100),
    "failedPolls": deque(maxlen=100),
    "bufferedCount": deque(maxlen=100)
}

mqtt_stats = {
    "messagesReceived": 0,
    "lastMessageTime": None,
    "lastMessageTimestamp": None,  # datetime object for stale detection
    "connectionStatus": "Disconnected"
}

# Log file path
LOG_DIR = r"D:\OpcLogs\MSLog"
LOG_FILE = os.path.join(LOG_DIR, "mslog.txt")

# ═══════════════════════════════════════════════════════════════════
# MQTT LOGGING - ALL MESSAGES WITH MILLISECOND TIMESTAMPS
# ═══════════════════════════════════════════════════════════════════
def ensure_log_dir():
    """Create log directory if it doesn't exist"""
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
        print(f"Created log directory: {LOG_DIR}")

def log_mqtt_data(topic, payload):
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
                latency = plc.get("lastReadTimeMs", plc.get("communicationLatencyMs", plc.get("averageReadTimeMs", 0)))
                success_rate = plc.get("successRatePercent", 0)
                total_polls = plc.get("totalPolls", 0)
                failed_polls = plc.get("failedPolls", 0)
                consec_fails = plc.get("consecutiveFailures", 0)
                tag_count = plc.get("tagCount", 0)
                health_score = plc.get("healthScorePercent", 0)
                
                status = "CONNECTED" if is_connected else "DISCONNECTED"
                lines.append(f"  [{plc_name}] {status} | Health: {health_score:.0f}%")
                lines.append(f"    latency={latency:.1f}ms | success={success_rate:.1f}% | tags={tag_count}")
                lines.append(f"    polls: total={total_polls} | failed={failed_polls} | consecutive_errors={consec_fails}")
        
        else:
            # Unknown message type - log raw JSON
            lines.append(f"[TYPE]     UNKNOWN")
            lines.append(f"[RAW]      {json.dumps(payload, indent=2)}")
        
        lines.append(f"")
        
        # Write to file
        log_entry = "\n".join(lines) + "\n"
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)
            
    except Exception as e:
        print(f"Error logging to file: {e}")

# ═══════════════════════════════════════════════════════════════════
# MQTT CLIENT
# ═══════════════════════════════════════════════════════════════════
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        mqtt_stats["connectionStatus"] = "Connected"
        print("[MQTT] Connected to broker")
        # Subscribe to ALL PLC topics to capture everything
        client.subscribe("plc/#")  # All plc topics: plc/plc/all, plc/health, etc.
        print("[MQTT] Subscribed to plc/# (all PLC topics)")
        print(f"[MQTT] Logging ALL messages to: {LOG_FILE}")
    else:
        mqtt_stats["connectionStatus"] = f"Failed (rc={rc})"
        print(f"[MQTT] Connection failed with code {rc}")

def on_disconnect(client, userdata, rc):
    mqtt_stats["connectionStatus"] = "Disconnected"
    print(f"[MQTT] Disconnected (rc={rc})")

def on_message(client, userdata, msg):
    global health_data
    try:
        payload = json.loads(msg.payload.decode())
        mqtt_stats["messagesReceived"] += 1
        mqtt_stats["lastMessageTime"] = datetime.now().strftime("%H:%M:%S")
        mqtt_stats["lastMessageTimestamp"] = datetime.now()  # For stale detection
        
        # Log to file
        log_mqtt_data(msg.topic, payload)
        
        # Parse health data
        if msg.topic == "plc/health":
            health_data = {
                "timestamp": payload.get("timestamp"),
                "plcCount": payload.get("plcCount", 0),
                "connectedCount": payload.get("connectedCount", 0),
                "disconnectedCount": payload.get("disconnectedCount", 0),
                "faultedCount": payload.get("faultedCount", 0),
                "plcs": payload.get("plcs", [])
            }
            
            # Update history for graphs
            if health_data["plcs"]:
                plc = health_data["plcs"][0]  # First PLC for now
                history["timestamps"].append(datetime.now().strftime("%H:%M:%S"))
                # Use raw lastReadTimeMs or communicationLatencyMs instead of average
                history["latency"].append(plc.get("lastReadTimeMs", plc.get("communicationLatencyMs", plc.get("averageReadTimeMs", 0))))
                history["successRate"].append(plc.get("successRatePercent", 100))
                history["totalPolls"].append(plc.get("totalPolls", 0))
                history["failedPolls"].append(plc.get("failedPolls", 0))
                history["bufferedCount"].append(plc.get("bufferedCount", 0))
            
            print(f"[MQTT] Health update: {health_data['connectedCount']}/{health_data['plcCount']} PLCs connected")
            
    except Exception as e:
        print(f"[MQTT] Error parsing message: {e}")

def start_mqtt():
    """Start MQTT client in background thread"""
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    
    try:
        client.connect("localhost", 1883, 60)
        client.loop_start()
        print("[MQTT] Client started")
    except Exception as e:
        print(f"[MQTT] Failed to connect: {e}")
        mqtt_stats["connectionStatus"] = f"Error: {e}"

# ═══════════════════════════════════════════════════════════════════
# FLASK ROUTES
# ═══════════════════════════════════════════════════════════════════

@app.route('/')
def dashboard():
    return render_template_string(DASHBOARD_HTML)

@app.route('/api/health')
def get_health():
    """Return current health data with stale detection"""
    
    # Check if data is stale (no MQTT message received for 10+ seconds)
    is_stale = False
    seconds_since_last_msg = -1
    
    if mqtt_stats.get("lastMessageTimestamp"):
        seconds_since_last_msg = (datetime.now() - mqtt_stats["lastMessageTimestamp"]).total_seconds()
        is_stale = seconds_since_last_msg > 10
    elif mqtt_stats["messagesReceived"] == 0:
        # Never received any message
        is_stale = True
    
    # If stale, return zeroed/disconnected values
    if is_stale:
        stale_health = {
            "timestamp": None,
            "plcCount": health_data.get("plcCount", 0),
            "connectedCount": 0,  # Show as disconnected when stale
            "disconnectedCount": health_data.get("plcCount", 1),
            "faultedCount": health_data.get("plcCount", 1),
            "plcs": []
        }
        # Add stale indicator to each PLC
        for plc in health_data.get("plcs", []):
            stale_plc = dict(plc)  # Copy original
            stale_plc["isConnected"] = False
            stale_plc["state"] = "STALE - No Data"
            stale_plc["lastReadTimeMs"] = 0
            stale_plc["communicationLatencyMs"] = 0
            stale_plc["healthScorePercent"] = 0
            stale_health["plcs"].append(stale_plc)
        
        return jsonify({
            "health": stale_health,
            "mqtt": {
                **mqtt_stats,
                "isStale": True,
                "secondsSinceLastMessage": int(seconds_since_last_msg) if seconds_since_last_msg > 0 else None,
                "connectionStatus": "STALE - No Data"
            },
            "history": {
                "timestamps": list(history["timestamps"]),
                "latency": list(history["latency"]),
                "successRate": list(history["successRate"]),
                "totalPolls": list(history["totalPolls"]),
                "failedPolls": list(history["failedPolls"]),
                "bufferedCount": list(history["bufferedCount"])
            }
        })
    
    return jsonify({
        "health": health_data,
        "mqtt": {
            **mqtt_stats,
            "isStale": False,
            "secondsSinceLastMessage": int(seconds_since_last_msg) if seconds_since_last_msg > 0 else 0
        },
        "history": {
            "timestamps": list(history["timestamps"]),
            "latency": list(history["latency"]),
            "successRate": list(history["successRate"]),
            "totalPolls": list(history["totalPolls"]),
            "failedPolls": list(history["failedPolls"]),
            "bufferedCount": list(history["bufferedCount"])
        }
    })

# ═══════════════════════════════════════════════════════════════════
# DASHBOARD HTML
# ═══════════════════════════════════════════════════════════════════
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PLC Health Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #fff;
            min-height: 100vh;
            padding: 20px;
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        .header h1 {
            font-size: 2.5em;
            background: linear-gradient(45deg, #00d4ff, #00ff88);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .mqtt-status {
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9em;
            margin-top: 10px;
        }
        .mqtt-connected { background: #00ff88; color: #000; }
        .mqtt-disconnected { background: #ff4444; color: #fff; }
        
        .dashboard-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            max-width: 1800px;
            margin: 0 auto;
        }
        
        .card {
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 20px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.1);
        }
        .card h3 {
            color: #00d4ff;
            margin-bottom: 15px;
            font-size: 1.1em;
        }
        
        /* Gauge Styles */
        .gauges-row {
            display: flex;
            justify-content: space-around;
            flex-wrap: wrap;
            gap: 20px;
        }
        .gauge-container {
            text-align: center;
            min-width: 150px;
        }
        .gauge {
            width: 150px;
            height: 90px;
            position: relative;
        }
        .gauge-bg {
            fill: none;
            stroke: rgba(255,255,255,0.1);
            stroke-width: 15;
        }
        .gauge-fill {
            fill: none;
            stroke-width: 15;
            stroke-linecap: round;
            transition: stroke-dashoffset 0.5s ease, stroke 0.3s;
        }
        .gauge-value {
            font-size: 1.5em;
            font-weight: bold;
            margin-top: -30px;
        }
        .gauge-label {
            font-size: 0.85em;
            color: #aaa;
            margin-top: 5px;
        }
        
        /* Status Indicators */
        .status-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
        }
        .status-item {
            background: rgba(0,0,0,0.2);
            border-radius: 10px;
            padding: 15px;
            text-align: center;
        }
        .status-value {
            font-size: 2em;
            font-weight: bold;
        }
        .status-label {
            font-size: 0.8em;
            color: #aaa;
            margin-top: 5px;
        }
        .status-good { color: #00ff88; }
        .status-warning { color: #ffaa00; }
        .status-bad { color: #ff4444; }
        
        /* Chart Container */
        .chart-container {
            height: 250px;
            position: relative;
        }
        
        /* PLC Cards */
        .plc-list {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        .plc-card {
            background: rgba(0,0,0,0.3);
            border-radius: 10px;
            padding: 15px;
            display: grid;
            grid-template-columns: auto 1fr auto;
            align-items: center;
            gap: 15px;
        }
        .plc-status-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }
        .plc-connected { background: #00ff88; box-shadow: 0 0 10px #00ff88; }
        .plc-disconnected { background: #ff4444; box-shadow: 0 0 10px #ff4444; }
        .plc-info h4 { margin-bottom: 5px; }
        .plc-info small { color: #888; }
        .plc-metrics {
            display: flex;
            gap: 20px;
            font-size: 0.9em;
        }
        .plc-metric {
            text-align: center;
        }
        .plc-metric-value {
            font-size: 1.2em;
            font-weight: bold;
            color: #00d4ff;
        }
        
        /* Log section */
        .log-info {
            background: rgba(0,0,0,0.3);
            border-radius: 10px;
            padding: 15px;
            font-family: monospace;
            font-size: 0.85em;
        }
        .log-path {
            color: #00ff88;
            word-break: break-all;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🏭 PLC Health Dashboard</h1>
        <div id="mqttStatus" class="mqtt-status mqtt-disconnected">MQTT: Disconnected</div>
    </div>
    
    <div class="dashboard-grid">
        <!-- Gauges Card -->
        <div class="card" style="grid-column: span 2;">
            <h3>📊 Performance Gauges</h3>
            <div class="gauges-row">
                <div class="gauge-container">
                    <svg class="gauge" viewBox="0 0 150 90">
                        <path class="gauge-bg" d="M 15 75 A 60 60 0 0 1 135 75"></path>
                        <path id="latencyGauge" class="gauge-fill" d="M 15 75 A 60 60 0 0 1 135 75" 
                              stroke="#00d4ff" stroke-dasharray="188" stroke-dashoffset="188"></path>
                    </svg>
                    <div id="latencyValue" class="gauge-value">0 ms</div>
                    <div class="gauge-label">Response Latency</div>
                </div>
                <div class="gauge-container">
                    <svg class="gauge" viewBox="0 0 150 90">
                        <path class="gauge-bg" d="M 15 75 A 60 60 0 0 1 135 75"></path>
                        <path id="successGauge" class="gauge-fill" d="M 15 75 A 60 60 0 0 1 135 75" 
                              stroke="#00ff88" stroke-dasharray="188" stroke-dashoffset="188"></path>
                    </svg>
                    <div id="successValue" class="gauge-value">0%</div>
                    <div class="gauge-label">Success Rate</div>
                </div>
                <div class="gauge-container">
                    <svg class="gauge" viewBox="0 0 150 90">
                        <path class="gauge-bg" d="M 15 75 A 60 60 0 0 1 135 75"></path>
                        <path id="errorsGauge" class="gauge-fill" d="M 15 75 A 60 60 0 0 1 135 75" 
                              stroke="#ff4444" stroke-dasharray="188" stroke-dashoffset="0"></path>
                    </svg>
                    <div id="errorsValue" class="gauge-value">0</div>
                    <div class="gauge-label">Failed Polls</div>
                </div>
                <div class="gauge-container">
                    <svg class="gauge" viewBox="0 0 150 90">
                        <path class="gauge-bg" d="M 15 75 A 60 60 0 0 1 135 75"></path>
                        <path id="bufferGauge" class="gauge-fill" d="M 15 75 A 60 60 0 0 1 135 75" 
                              stroke="#ffaa00" stroke-dasharray="188" stroke-dashoffset="188"></path>
                    </svg>
                    <div id="bufferValue" class="gauge-value">0</div>
                    <div class="gauge-label">Buffer Size</div>
                </div>
            </div>
        </div>
        
        <!-- Status Summary -->
        <div class="card">
            <h3>📡 Connection Status</h3>
            <div class="status-grid">
                <div class="status-item">
                    <div id="plcCount" class="status-value">0</div>
                    <div class="status-label">Total PLCs</div>
                </div>
                <div class="status-item">
                    <div id="connectedCount" class="status-value status-good">0</div>
                    <div class="status-label">Connected</div>
                </div>
                <div class="status-item">
                    <div id="disconnectedCount" class="status-value status-bad">0</div>
                    <div class="status-label">Disconnected</div>
                </div>
                <div class="status-item">
                    <div id="faultedCount" class="status-value status-warning">0</div>
                    <div class="status-label">Faulted</div>
                </div>
            </div>
        </div>
        
        <!-- Latency Graph -->
        <div class="card" style="grid-column: span 2;">
            <h3>📈 Response Time Trend</h3>
            <div class="chart-container">
                <canvas id="latencyChart"></canvas>
            </div>
        </div>
        
        <!-- Poll Statistics Graph -->
        <div class="card">
            <h3>📊 Poll Statistics</h3>
            <div class="chart-container">
                <canvas id="pollChart"></canvas>
            </div>
        </div>
        
        <!-- PLC List -->
        <div class="card" style="grid-column: span 2;">
            <h3>🔌 PLC Connections</h3>
            <div id="plcList" class="plc-list">
                <div class="plc-card">
                    <div class="plc-status-dot plc-disconnected"></div>
                    <div class="plc-info">
                        <h4>Waiting for data...</h4>
                        <small>MQTT topic: plc/health</small>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Log Info -->
        <div class="card">
            <h3>📝 MQTT Logging</h3>
            <div class="log-info">
                <p>All MQTT messages logged to:</p>
                <p class="log-path">D:\\OpcLogs\\MSLog\\mslog.txt</p>
                <p style="margin-top: 10px;">Messages received: <span id="msgCount">0</span></p>
                <p>Last message: <span id="lastMsgTime">-</span></p>
            </div>
        </div>
    </div>

    <script>
        // ═══════════════════════════════════════════════════════════════
        // CHARTS INITIALIZATION
        // ═══════════════════════════════════════════════════════════════
        const latencyCtx = document.getElementById('latencyChart').getContext('2d');
        const latencyChart = new Chart(latencyCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Response Time (ms)',
                    data: [],
                    borderColor: '#00d4ff',
                    backgroundColor: 'rgba(0,212,255,0.1)',
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { color: 'rgba(255,255,255,0.1)' }, ticks: { color: '#888' } },
                    y: { grid: { color: 'rgba(255,255,255,0.1)' }, ticks: { color: '#888' }, min: 0 }
                }
            }
        });

        const pollCtx = document.getElementById('pollChart').getContext('2d');
        const pollChart = new Chart(pollCtx, {
            type: 'bar',
            data: {
                labels: ['Total', 'Success', 'Failed'],
                datasets: [{
                    label: 'Polls',
                    data: [0, 0, 0],
                    backgroundColor: ['#00d4ff', '#00ff88', '#ff4444']
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { color: 'rgba(255,255,255,0.1)' }, ticks: { color: '#888' } },
                    y: { grid: { color: 'rgba(255,255,255,0.1)' }, ticks: { color: '#888' }, min: 0 }
                }
            }
        });

        // ═══════════════════════════════════════════════════════════════
        // GAUGE FUNCTIONS
        // ═══════════════════════════════════════════════════════════════
        function updateGauge(gaugeId, valueId, value, max, unit = '', colorFunc = null) {
            const gauge = document.getElementById(gaugeId);
            const valueEl = document.getElementById(valueId);
            
            const percent = Math.min(value / max, 1);
            const offset = 188 * (1 - percent);
            gauge.style.strokeDashoffset = offset;
            
            if (colorFunc) {
                gauge.style.stroke = colorFunc(percent);
            }
            
            valueEl.textContent = typeof value === 'number' ? 
                (value % 1 !== 0 ? value.toFixed(1) : value) + unit : value + unit;
        }

        function getLatencyColor(percent) {
            if (percent < 0.3) return '#00ff88';
            if (percent < 0.6) return '#ffaa00';
            return '#ff4444';
        }

        function getSuccessColor(percent) {
            if (percent > 0.95) return '#00ff88';
            if (percent > 0.8) return '#ffaa00';
            return '#ff4444';
        }

        // ═══════════════════════════════════════════════════════════════
        // UPDATE FUNCTION
        // ═══════════════════════════════════════════════════════════════
        async function updateDashboard() {
            try {
                const response = await fetch('/api/health');
                const data = await response.json();
                
                // Update MQTT status with stale indicator
                const mqttStatus = document.getElementById('mqttStatus');
                const isStale = data.mqtt.isStale;
                const secSince = data.mqtt.secondsSinceLastMessage;
                
                if (isStale) {
                    mqttStatus.textContent = `⚠️ STALE DATA - No updates for ${secSince}s`;
                    mqttStatus.className = 'mqtt-status mqtt-disconnected';
                    // Flash background to indicate stale
                    document.body.style.background = 'linear-gradient(135deg, #3a1a1a 0%, #2e1616 100%)';
                } else {
                    mqttStatus.textContent = `MQTT: ${data.mqtt.connectionStatus} (${secSince}s ago)`;
                    mqttStatus.className = data.mqtt.connectionStatus === 'Connected' ? 
                        'mqtt-status mqtt-connected' : 'mqtt-status mqtt-disconnected';
                    // Normal background
                    document.body.style.background = 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)';
                    // Normal background
                    document.body.style.background = 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)';
                }
                
                // Update message stats
                document.getElementById('msgCount').textContent = data.mqtt.messagesReceived;
                document.getElementById('lastMsgTime').textContent = data.mqtt.lastMessageTime || '-';
                
                // Update summary counts
                document.getElementById('plcCount').textContent = data.health.plcCount;
                document.getElementById('connectedCount').textContent = data.health.connectedCount;
                document.getElementById('disconnectedCount').textContent = data.health.disconnectedCount;
                document.getElementById('faultedCount').textContent = data.health.faultedCount;
                
                // Update gauges if we have PLC data
                if (data.health.plcs && data.health.plcs.length > 0) {
                    const plc = data.health.plcs[0];
                    
                    // Use raw lastReadTimeMs or communicationLatencyMs (not average)
                    const latency = plc.lastReadTimeMs || plc.communicationLatencyMs || plc.averageReadTimeMs || 0;
                    updateGauge('latencyGauge', 'latencyValue', latency, 500, ' ms', getLatencyColor);
                    updateGauge('successGauge', 'successValue', plc.successRatePercent || 100, 100, '%', getSuccessColor);
                    updateGauge('errorsGauge', 'errorsValue', plc.failedPolls || 0, Math.max(plc.failedPolls || 1, 10), '');
                    updateGauge('bufferGauge', 'bufferValue', plc.bufferedCount || 0, 10000, '');
                    
                    // Update poll chart
                    pollChart.data.datasets[0].data = [
                        plc.totalPolls || 0,
                        plc.successfulPolls || 0,
                        plc.failedPolls || 0
                    ];
                    pollChart.update('none');
                }
                
                // Update latency chart
                if (data.history.timestamps.length > 0) {
                    latencyChart.data.labels = data.history.timestamps;
                    latencyChart.data.datasets[0].data = data.history.latency;
                    latencyChart.update('none');
                }
                
                // Update PLC list
                if (data.health.plcs && data.health.plcs.length > 0) {
                    const plcList = document.getElementById('plcList');
                    plcList.innerHTML = data.health.plcs.map(plc => `
                        <div class="plc-card">
                            <div class="plc-status-dot ${plc.isConnected ? 'plc-connected' : 'plc-disconnected'}"></div>
                            <div class="plc-info">
                                <h4>${plc.plcName || plc.plcId}</h4>
                                <small>${plc.ipAddress}:${plc.port} | ${plc.protocol} | ${plc.state}</small>
                            </div>
                            <div class="plc-metrics">
                                <div class="plc-metric">
                                    <div class="plc-metric-value">${(plc.lastReadTimeMs || plc.communicationLatencyMs || plc.averageReadTimeMs || 0).toFixed(0)}ms</div>
                                    <small>Latency</small>
                                </div>
                                <div class="plc-metric">
                                    <div class="plc-metric-value">${plc.tagCount || 0}</div>
                                    <small>Tags</small>
                                </div>
                                <div class="plc-metric">
                                    <div class="plc-metric-value">${(plc.successRatePercent || 100).toFixed(1)}%</div>
                                    <small>Success</small>
                                </div>
                                <div class="plc-metric">
                                    <div class="plc-metric-value">${(plc.healthScorePercent || 0).toFixed(0)}%</div>
                                    <small>Health</small>
                                </div>
                                <div class="plc-metric">
                                    <div class="plc-metric-value">${plc.bufferedCount || 0}</div>
                                    <small>Buffer</small>
                                </div>
                            </div>
                        </div>
                    `).join('');
                }
                
            } catch (error) {
                console.error('Update error:', error);
            }
        }

        // Update every 1 second
        setInterval(updateDashboard, 1000);
        updateDashboard();
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    print("=" * 60)
    print("PLC HEALTH DASHBOARD")
    print("=" * 60)
    print(f"MQTT Topic: plc/health")
    print(f"Log File: {LOG_FILE}")
    print(f"Dashboard: http://localhost:5004")
    print("=" * 60)
    
    # Ensure log directory exists
    ensure_log_dir()
    
    # Start MQTT client
    mqtt_thread = threading.Thread(target=start_mqtt, daemon=True)
    mqtt_thread.start()
    
    # Start Flask app
    app.run(host='0.0.0.0', port=5004, debug=False, threaded=True)
