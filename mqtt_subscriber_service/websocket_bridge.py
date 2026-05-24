"""
WebSocket Bridge for HMI Live Data
Subscribes to EMQX MQTT topics and forwards to HMI frontend via Socket.IO.

Topics subscribed:
  opc/+/tags/bulk        — OPC DA tags from C# (e.g. opc/Matrikon.OPC.Simulation.1/tags/bulk)
  opc/+/tags/bulk/+      — chunked batches
  plc/+/bulk             — PLC tags from C# (e.g. plc/PLC_GATEWAY_01/bulk)
  plc/all                — legacy PLC all-tags topic
  plc/health             — PLC health heartbeats
  opc/alarms/events      — ISA-18.2 alarm lifecycle events from C# AlarmEvaluationService
  opc/interlocks/events  — Interlock state transitions from C# InterlockEvaluationService
"""
import logging
import json
from flask import Flask
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import paho.mqtt.client as mqtt
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# MQTT broker configuration — must match appsettings.json OpcMqttTransport
MQTT_BROKER_HOST = 'localhost'
MQTT_BROKER_PORT = 1883

# Topics to subscribe — wildcards cover all OPC servers and PLC IDs
MQTT_TOPICS = [
    ('opc/+/tags/bulk',      0),   # OPC bulk snapshot per server
    ('opc/+/tags/bulk/+',    0),   # OPC chunked batches
    ('plc/+/bulk',           0),   # PLC per-device bulk
    ('plc/all',              0),   # PLC legacy all-tags
    ('plc/health',           0),   # PLC health heartbeat
    ('opc/alarms/events',    1),   # ISA-18.2 alarm lifecycle — C# AlarmEvaluationService
    ('opc/interlocks/events', 1),  # Interlock state transitions — C# InterlockEvaluationService
]

# Flask + Socket.IO
app = Flask(__name__)
app.config['SECRET_KEY'] = 'hmi-websocket-secret'
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',
    logger=False,
    engineio_logger=False
)

# ─── MQTT callbacks ────────────────────────────────────────────────────────────

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info(f"✅ MQTT connected to {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}")
        for topic, qos in MQTT_TOPICS:
            client.subscribe(topic, qos)
            logger.info(f"   📥 Subscribed: {topic}")
    else:
        logger.error(f"❌ MQTT connect failed, rc={rc}")

def on_disconnect(client, userdata, rc):
    logger.warning(f"⚠️  MQTT disconnected, rc={rc} — will auto-reconnect")

def on_message(client, userdata, msg):
    """Route incoming MQTT messages to the correct Socket.IO event."""
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        topic   = msg.topic

        # ── OPC DA bulk snapshot ──────────────────────────────────────────────
        if topic.startswith('opc/') and 'tags/bulk' in topic:
            server_prog_id = topic.split('/')[1]          # e.g. Matrikon.OPC.Simulation.1
            values = payload.get('values', [])

            # Normalise to a flat list the HMI already understands
            tags = []
            for v in values:
                tags.append({
                    'tag_id':      v.get('tagId'),
                    'value':       v.get('value'),
                    'quality':     v.get('quality', 'Good'),
                    'time':        v.get('timestamp'),
                    'is_stale':    v.get('isStale', False),
                    'is_changed':  v.get('isChanged', True),
                    'sequence_id': v.get('sequenceId'),
                    'source':      'opc_da',
                    'server':      server_prog_id,
                })

            data = {
                'tags':        tags,
                'timestamp':   payload.get('timestamp', datetime.utcnow().isoformat()),
                'topic':       topic,
                'source':      'opc_da',
                'server':      server_prog_id,
                'tag_count':   payload.get('tagCount', len(tags)),
                'batch_index': payload.get('batchIndex', 0),
                'total_batches': payload.get('totalBatches', 1),
            }
            socketio.emit('mqtt_tag_update', data)
            logger.debug(f"📡 OPC [{server_prog_id}] → {len(tags)} tags forwarded to HMI")

        # ── PLC bulk snapshot ─────────────────────────────────────────────────
        elif topic.startswith('plc/') and topic.endswith('/bulk'):
            plc_id = topic.split('/')[1]
            values = payload.get('values', payload.get('tags', []))

            tags = []
            for v in values:
                tags.append({
                    'tag_id':   v.get('tagId', v.get('tag_id')),
                    'value':    v.get('value'),
                    'quality':  v.get('quality', 'Good'),
                    'time':     v.get('timestamp', v.get('time')),
                    'source':   'plc',
                    'plc_id':   plc_id,
                })

            data = {
                'tags':      tags,
                'timestamp': payload.get('timestamp', datetime.utcnow().isoformat()),
                'topic':     topic,
                'source':    'plc',
                'plc_id':    plc_id,
            }
            socketio.emit('mqtt_tag_update', data)
            logger.debug(f"📡 PLC [{plc_id}] → {len(tags)} tags forwarded to HMI")

        # ── PLC legacy all-tags ───────────────────────────────────────────────
        elif topic == 'plc/all':
            socketio.emit('mqtt_tag_update', {
                'tags':      payload.get('tags', []),
                'timestamp': payload.get('timestamp', datetime.utcnow().isoformat()),
                'topic':     topic,
                'source':    'plc',
            })

        # ── PLC health heartbeat ──────────────────────────────────────────────
        elif topic == 'plc/health':
            socketio.emit('plc_health', payload)
            logger.debug(f"💓 PLC health forwarded")

        # ── ISA-18.2 alarm lifecycle event from C# AlarmEvaluationService ────
        elif topic == 'opc/alarms/events':
            tag_id  = payload.get('tag_id', 'UNKNOWN')
            level   = payload.get('level', '')
            state   = payload.get('alarm_state', 'ACTIVE')    # 'ACTIVE' or 'RTN'
            transition = payload.get('transition', '')         # 'RAISED' or 'RTN'

            # Map level to frontend priority (higher number = more critical in AlarmPanel)
            level_priority = {
                'HighHigh': 5,
                'High':     4,
                'Low':      3,
                'LowLow':   2,
            }
            priority = level_priority.get(level, payload.get('priority', 3))

            # Human-readable message
            if transition == 'RAISED':
                message = f"{tag_id}: {level} alarm ACTIVE"
            elif transition == 'RTN':
                message = f"{tag_id}: {level} alarm returned to normal"
            else:
                message = f"{tag_id}: {level} alarm state {state}"

            alarm_event = {
                'event_id':   payload.get('event_id'),
                'tagId':      tag_id,
                'tag_id':     tag_id,
                'transition': transition,
                'level':      level,
                'value':      payload.get('value'),
                'setpoint':   payload.get('setpoint'),
                'priority':   priority,
                'state':      state,
                'alarm_state': state,
                'eventType':  f'ALARM_{level.upper()}' if level else 'ALARM',
                'message':    message,
                'raised_at':  payload.get('raised_at'),
                'timestamp':  payload.get('timestamp', payload.get('raised_at')),
            }
            socketio.emit('mqtt_alarm', alarm_event)
            logger.info(f"🚨 ALARM → frontend: {tag_id} [{level}] {transition} (state={state})")

        # ── Interlock state transition from C# InterlockEvaluationService ────
        elif topic == 'opc/interlocks/events':
            tag_id          = payload.get('tag_id', 'UNKNOWN')
            interlock_state = payload.get('interlock_state', 'UNKNOWN')

            # Derive status badge expected by InterlockStatusBoard
            status_map = {
                'VIOLATED':  'VIOLATION',
                'SATISFIED': 'NORMAL',
                'BYPASSED':  'ACTIVE_BYPASS',
                'DISABLED':  'ACTIVE_BYPASS',
            }
            status = status_map.get(interlock_state, 'NORMAL')

            interlock_event = {
                'interlock_event_id':    payload.get('event_id'),
                'event_time':            payload.get('event_time', payload.get('timestamp')),
                'interlock_tag_id':      tag_id,
                'interlock_tag_name':    tag_id,
                'interlock_type':        payload.get('interlock_type', 'PERMISSIVE'),
                'interlock_state':       interlock_state,
                'previous_state':        payload.get('previous_state'),
                'state_duration_seconds': None,
                'affected_equipment':    payload.get('affected_equipment', ''),
                'bypass_reason':         None,
                'bypass_authorized_by':  None,
                'bypass_expires_at':     None,
                'bypass_remaining_seconds': None,
                'related_trip_event_id': None,
                'status':                status,
                'timestamp':             payload.get('timestamp'),
            }
            socketio.emit('mqtt_interlock', interlock_event)
            logger.info(f"🔒 INTERLOCK → frontend: {tag_id} [{payload.get('interlock_type')}] {interlock_state}")

    except Exception as e:
        logger.error(f"❌ on_message error on topic '{msg.topic}': {e}")


def start_mqtt():
    """Connect MQTT client and start its network loop in a background thread."""
    client = mqtt.Client(client_id='websocket_bridge_hmi', clean_session=True)
    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    try:
        client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, keepalive=60)
    except Exception as e:
        logger.error(f"❌ Initial MQTT connect failed: {e} — will retry in background")
    client.loop_start()   # non-blocking background thread
    return client

_mqtt_client = None   # kept alive for process lifetime

@socketio.on('connect')
def handle_connect():
    """Handle HMI client connection."""
    logger.info('✅ HMI client connected')
    emit('connection_status', {
        'status':  'connected',
        'message': 'WebSocket bridge connected — subscribed to MQTT topics',
        'topics':  [t for t, _ in MQTT_TOPICS],
    })


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection."""
    logger.info('⚠️  HMI client disconnected')


@app.route('/health')
def health():
    """Health check endpoint."""
    return {
        'status':  'ok',
        'service': 'websocket-bridge',
        'port':    6002,
        'mqtt':    'connected' if (_mqtt_client and _mqtt_client.is_connected()) else 'disconnected',
        'topics':  [t for t, _ in MQTT_TOPICS],
    }


if __name__ == '__main__':
    # Start MQTT subscriber (non-blocking background thread)
    _mqtt_client = start_mqtt()

    # Start Socket.IO server (blocks forever)
    logger.info("🚀 Starting WebSocket bridge on port 6002...")
    socketio.run(app, host='0.0.0.0', port=6002, debug=False, allow_unsafe_werkzeug=True)

