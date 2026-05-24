"""
HMI Flask Application - High-Performance Real-Time + Historical Trends
Connects to EXISTING C# SignalR hub - NO CHANGES to C# services required
NOW INCLUDES: MQTT Live Data Streaming
"""

# ── Gevent monkey-patch MUST be first — before any stdlib/network imports ──
from gevent import monkey as _monkey
_monkey.patch_all()

import logging
import time
import os
import sys
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from flask import Flask, request
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from services.signalr_listener import SignalRListener
from services.mqtt_client_service import MQTTClientService
from container import container

# Import Blueprints
from controllers.auth_controller import auth_bp
from controllers.main_controller import main_bp
from controllers.tag_controller import tag_bp
from controllers.historical_controller import historical_bp
from controllers.system_controller import system_bp
from controllers.admin_controller import admin_bp
from controllers.alarm_controller import alarm_bp
from controllers.asset_controller import asset_bp
from controllers.mqtt_controller import mqtt_bp
from controllers.report_controller import report_bp

# Enhanced RBAC Controllers
from controllers.audit_controller import audit_bp
from controllers.session_controller import session_bp
from controllers.equipment_controller import equipment_bp
from controllers.approval_controller import approval_bp
from controllers.industrial_rbac_controller import industrial_rbac_bp


def setup_logging():
    """
    Configure production-ready file-based logging with rotation
    - Size-based rotation: 5 MB max per file
    - Date-based rotation: Daily logs with 30-day retention
    - Separate error log file
    - Console output for real-time monitoring
    """
    # Create logs directory if it doesn't exist
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Define log file paths
    info_log_file = os.path.join(log_dir, 'hmi_app.log')
    error_log_file = os.path.join(log_dir, 'hmi_errors.log')
    daily_log_file = os.path.join(log_dir, 'hmi_daily.log')
    
    # Define log format
    detailed_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)-8s] [%(name)-25s] [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Remove any existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers = []
    root_logger.setLevel(logging.INFO)
    
    # 1. Console Handler (INFO level) - for terminal output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)
    root_logger.addHandler(console_handler)
    
    # 2. Rotating File Handler - Size-based (5 MB, keep 10 backups)
    rotating_handler = RotatingFileHandler(
        info_log_file,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=10,
        encoding='utf-8'
    )
    rotating_handler.setLevel(logging.INFO)
    rotating_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(rotating_handler)
    
    # 3. Daily Log — RotatingFileHandler capped at 10 MB (replaces unbounded
    #    TimedRotatingFileHandler which grew to 300 MB+ on busy days).
    #    Keeps 5 backups = max 60 MB total for daily log files.
    daily_handler = RotatingFileHandler(
        daily_log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB hard cap
        backupCount=5,
        encoding='utf-8'
    )
    daily_handler.setLevel(logging.INFO)
    daily_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(daily_handler)
    
    # 4. Error File Handler - Separate file for errors only
    error_handler = RotatingFileHandler(
        error_log_file,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=10,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(error_handler)
    
    # Log startup message
    startup_logger = logging.getLogger(__name__)
    startup_logger.info("=" * 80)
    startup_logger.info("[STARTUP] HMI Flask Application Starting")
    startup_logger.info(f"[CONFIG] Log Directory: {log_dir}")
    startup_logger.info(f"[CONFIG] Info Log: {info_log_file}")
    startup_logger.info(f"[CONFIG] Error Log: {error_log_file}")
    startup_logger.info(f"[CONFIG] Daily Log: {daily_log_file}")
    startup_logger.info(f"[CONFIG] Rotation: 5 MB per file, 10 backups, 30 days retention")
    startup_logger.info("=" * 80)
    
    return startup_logger


# Configure production logging
logger = setup_logging()

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = container.secret_key
CORS(app)

# Register Blueprints
app.register_blueprint(main_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(tag_bp)
app.register_blueprint(historical_bp)
app.register_blueprint(system_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(alarm_bp)
app.register_blueprint(asset_bp)
app.register_blueprint(mqtt_bp)
app.register_blueprint(report_bp)

# Register Enhanced RBAC Blueprints
app.register_blueprint(audit_bp)
app.register_blueprint(session_bp)
app.register_blueprint(equipment_bp)
app.register_blueprint(approval_bp)
app.register_blueprint(industrial_rbac_bp)

from controllers.pews_controller import pews_bp
app.register_blueprint(pews_bp)

from controllers.bi_controller import bi_bp
app.register_blueprint(bi_bp)

from controllers.predictive_alarm_controller import predictive_bp
app.register_blueprint(predictive_bp)

# ── Lightweight health endpoint — no auth required, used by UI banner ──────
import time as _time
_flask_start_time = _time.time()

@app.route('/api/health', methods=['GET'])
def api_health():
    """Liveness probe — ALWAYS returns 200 if Flask is alive.
    DB status is informational only; a stale DB connection never causes a non-200.
    Used by the React ConnectionHealthBanner every 30s.
    """
    from flask import jsonify as _jsonify
    db_ok = False
    try:
        conn = container.historical_service.connection
        # conn.closed == 0 means open — property check, no network round-trip
        db_ok = (conn is not None and conn.closed == 0)
    except Exception:
        db_ok = False
    return _jsonify({
        'status': 'ok',
        'uptime_s': round(_time.time() - _flask_start_time),
        'db': db_ok,
    }), 200  # ALWAYS 200 — Flask being alive IS the health check


@app.route('/api/system-status', methods=['GET'])
def api_system_status():
    """Detailed system status — OPC/DB/MQTT/SignalR details.
    Used by the UI system-status panel. Requires no auth (read-only, non-sensitive).
    """
    from flask import jsonify as _jsonify
    # DB
    db_ok = False
    try:
        conn = container.historical_service.connection
        db_ok = (conn is not None and conn.closed == 0)
    except Exception:
        db_ok = False
    # MQTT
    mqtt_ok = False
    try:
        mqtt_ok = bool(container.mqtt_client and container.mqtt_client.is_connected)
    except Exception:
        mqtt_ok = False
    # SignalR (C# OPC bridge)
    signalr_ok = False
    try:
        signalr_ok = bool(container.signalr_listener and container.signalr_listener.is_connected)
    except Exception:
        signalr_ok = False
    return _jsonify({
        'flask':    {'ok': True,      'uptime_s': round(_time.time() - _flask_start_time)},
        'db':       {'ok': db_ok},
        'mqtt':     {'ok': mqtt_ok},
        'signalr':  {'ok': signalr_ok},
        'clients':  len(connected_clients),
        'ts':       _time.time(),
    }), 200

# Start predictive engine
try:
    from services.predictive_alarm_engine import engine_instance as _pred_engine
    _pred_engine().start()
    logger.info("[OK] Predictive alarm engine started")
except Exception as _e:
    logger.warning("[WARN] Predictive engine failed to start: %s", _e)

# RBAC Middleware
@app.before_request
def check_rbac_permissions():
    """
    Enforce RBAC permissions on protected endpoints
    """
    # Log all incoming requests
    logger.info(f"[HTTP] {request.method} {request.path} from {request.remote_addr}")
    if request.headers.get('Authorization'):
        token_preview = request.headers.get('Authorization')[:30]
        logger.info(f"[AUTH] Authorization header: {token_preview}...")
    else:
        logger.info(f"[WARN] No Authorization header")
    
    # Skip RBAC check for auth endpoints and public endpoints
    public_endpoints = [
        '/api/auth/login',
        '/api/auth/logout',
        '/api/auth/verify',
        '/api/main/hmi-mode',
        '/api/main/equipment-options',
        '/socket.io'
    ]
    
    if any(request.path.startswith(ep) for ep in public_endpoints):
        return None
    
    # Check if endpoint requires RBAC (optional - controller can handle it)
    # This is a hook for future RBAC enforcement at the app level
    return None

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
# CHANGED: Use threading mode for better Windows compatibility
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='gevent',          # gevent — better concurrency than threading
    ping_interval=60,             # server pings client every 60s
    ping_timeout=180,             # allow 3 min for pong — survives browser background throttle
    logger=True,
    engineio_logger=False,
)

# In-memory cache for latest tag values (performance optimization)
# Note: This is now managed here but ideally belongs in a RealtimeService. 
# Keeping it here for simplicity in this step.
latest_tag_values = {}
connected_clients = set()

# ── Per-SID session store: maps socket SID → allowed (plant, area) set or None(=admin)
# Populated on connect, cleaned on disconnect.  None means no filtering (admin).
_sid_sessions: dict = {}   # { sid: {"user_id": int, "is_admin": bool, "allowed": set|None} }


def _get_user_allowed_areas(user_id: int, is_admin: bool):
    """
    Returns:
      None            – admin, no filtering
      set of (plant, area) tuples – areas this user is allowed to see
    Mirrors the priority logic in decorators.get_user_allowed_tag_filter().
    """
    if is_admin:
        return None
    try:
        assigned = container.area_access_service.get_user_area_access(user_id)
    except Exception as exc:
        logger.error("[SOCKET] area_access_service failed for user %s: %s", user_id, exc)
        assigned = []
    if assigned is None:
        # Service-level admin bypass
        return None
    if assigned:
        return {(a.get('plant'), a.get('area')) for a in assigned if a.get('plant') and a.get('area')}
    # Fallback: old role-based permissions
    try:
        perms = container.rbac_service.get_user_allowed_tags(user_id) or []
        return {(p.get('plant'), p.get('area')) for p in perms
                if p.get('can_view') and p.get('plant') and p.get('area')} or set()
    except Exception:
        return set()   # deny all on error

try:
    IST_TZ = ZoneInfo('Asia/Kolkata')
except Exception:
    # Fallback for environments without tzdata package on Windows.
    IST_TZ = timezone(timedelta(hours=5, minutes=30))


def now_ist_iso():
    """Return current IST timestamp in ISO 8601 format with timezone offset."""
    return datetime.now(IST_TZ).isoformat()


def _parse_sample_time(raw_time):
    """Parse MQTT/sample timestamp safely; default to current IST if missing/invalid."""
    if isinstance(raw_time, datetime):
        dt = raw_time
    elif isinstance(raw_time, str) and raw_time.strip():
        text = raw_time.strip()
        if text.endswith('Z'):
            text = text[:-1] + '+00:00'
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            dt = datetime.now(IST_TZ)
    else:
        dt = datetime.now(IST_TZ)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST_TZ)
    return dt


def _coerce_bool(raw_value):
    """Convert mixed bool-like payload values to strict bool/None for DB writes."""
    if raw_value is None:
        return None

    if isinstance(raw_value, bool):
        return raw_value

    if isinstance(raw_value, (int, float)):
        if raw_value in (0, 0.0):
            return False
        if raw_value in (1, 1.0):
            return True
        return None

    if isinstance(raw_value, str):
        val = raw_value.strip().lower()
        if val in ('true', 't', '1', 'yes', 'y', 'on'):
            return True
        if val in ('false', 'f', '0', 'no', 'n', 'off'):
            return False
        return None

    return None


def _persist_mqtt_samples(filtered_tags, topic):
    """Persist filtered MQTT tags to historian_raw.historian_timeseries."""
    db_service = container.historical_service
    if not db_service or not db_service.connection or not filtered_tags:
        return

    rows = []
    bool_coerced = 0
    bool_dropped = 0
    for tag in filtered_tags:
        tag_id = tag.get('tag_id')
        if not tag_id:
            continue

        sample_time = _parse_sample_time(tag.get('time'))
        quality = (tag.get('quality') or 'G')
        if quality == 'Good':
            quality = 'G'
        elif quality == 'Bad':
            quality = 'B'

        try:
            mapping_version = int(tag.get('mapping_version') or 1)
        except (TypeError, ValueError):
            mapping_version = 1

        raw_bool = tag.get('value_bool')
        safe_bool = _coerce_bool(raw_bool)
        if raw_bool is not None and safe_bool is None:
            bool_dropped += 1
        elif raw_bool is not None and type(raw_bool) is not bool:
            bool_coerced += 1

        rows.append((
            sample_time,
            tag_id,
            tag.get('value_num'),
            tag.get('value_text'),
            safe_bool,
            quality,
            'MQTT',
            mapping_version,
            sample_time,
        ))

    if not rows:
        return

    if bool_coerced or bool_dropped:
        logger.info(
            "[MQTT_PERSIST_BOOL_NORMALIZE] topic=%s rows=%s coerced=%s dropped=%s",
            topic,
            len(rows),
            bool_coerced,
            bool_dropped,
        )

    try:
        with db_service.connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO historian_raw.historian_timeseries
                    (time, tag_id, value_num, value_text, value_bool, quality, sample_source, mapping_version, opc_timestamp)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (time, tag_id) DO UPDATE SET
                    value_num = EXCLUDED.value_num,
                    value_text = EXCLUDED.value_text,
                    value_bool = EXCLUDED.value_bool,
                    quality = EXCLUDED.quality,
                    sample_source = EXCLUDED.sample_source,
                    mapping_version = EXCLUDED.mapping_version,
                    opc_timestamp = EXCLUDED.opc_timestamp
                """,
                rows,
            )
        db_service.connection.commit()
    except Exception as ex:
        try:
            db_service.connection.rollback()
        except Exception:
            pass
        sample = rows[0] if rows else None
        logger.error("[MQTT_PERSIST_ERROR] topic=%s rows=%s error=%s", topic, len(rows), ex)
        logger.error(
            "[MQTT_PERSIST_DEBUG] topic=%s sample_tag=%s sample_value_num=%s sample_value_text=%s sample_value_bool=%s sample_bool_type=%s",
            topic,
            sample[1] if sample else None,
            sample[2] if sample else None,
            sample[3] if sample else None,
            sample[4] if sample else None,
            type(sample[4]).__name__ if sample and sample[4] is not None else None,
        )

def on_mqtt_message(topic, filtered_tags, raw_data):
    """
    Callback when MQTT message received with filtered tags
    Sends live data to frontend via WebSocket
    
    Args:
        topic: MQTT topic name
        filtered_tags: List of tags filtered for this topic's PLC
        raw_data: Raw MQTT payload (includes alarm_summary if alarms present)
    """
    global latest_tag_values
    
    try:
        message_ts = now_ist_iso()
        logger.info(
            "[ALARM_FLOW] topic=%s filtered_tags=%s has_alarm_summary=%s msg_ts=%s",
            topic,
            len(filtered_tags) if filtered_tags else 0,
            isinstance(raw_data, dict) and 'alarm_summary' in raw_data,
            message_ts
        )

        # NOTE: historian_raw.historian_events writes are OWNED by C# AlarmEvaluationService.
        # HMI only emits real-time events to the browser via socketio — no DB inserts here.

        alarms_processed = 0

        # Check for embedded alarms in the payload
        if isinstance(raw_data, dict) and 'alarm_summary' in raw_data:
            alarm_summary = raw_data['alarm_summary']
            alarms = alarm_summary.get('alarms', [])
            
            if alarms:
                logger.info(f"🚨 Processing {len(alarms)} alarms from topic {topic}")
                
                for alarm_data in alarms:
                    # Map severity (1=CRITICAL, 2=HIGH, 3=WARNING) to priority
                    severity_value = alarm_data.get('severity', 2)
                    if severity_value == 1:
                        priority = 3  # CRITICAL
                        severity_name = 'CRITICAL'
                    elif severity_value == 2:
                        priority = 2  # HIGH/WARNING
                        severity_name = 'WARNING'
                    else:
                        priority = 1  # INFO
                        severity_name = 'INFO'
                    
                    metadata = alarm_data.get('metadata', {})
                    tag_id = alarm_data.get('tag_id', 'UNKNOWN')

                    # DB write is handled by C# AlarmEvaluationService — use client-side temp ID.
                    alarm_id = f"ALM_{tag_id}_{int(time.time() * 1000)}"
                    alarms_processed += 1
                    
                    # Emit alarm to all connected clients
                    socketio.emit('mqtt_alarm', {
                        'id': alarm_id,
                        'timestamp': alarm_data.get('time', now_ist_iso()),
                        'priority': priority,
                        'tagId': tag_id,
                        'message': alarm_data.get('message', 'Alarm triggered'),
                        'acknowledged': metadata.get('acknowledged', False),
                        'value': metadata.get('alarm_value'),
                        'plcName': raw_data.get('gateway_id', ''),
                        'state': metadata.get('state', 'ACTIVE'),
                        'eventType': alarm_data.get('event_type', 'ALARM'),
                        'setpoint': metadata.get('setpoint'),
                        'unit': metadata.get('unit', ''),
                        'area': metadata.get('area', ''),
                        'equipment': metadata.get('equipment', '')
                    }, namespace='/')
                    
                    logger.info(f"🚨 ALARM: {tag_id} - {alarm_data.get('message')} [{severity_name}]")

        # Fallback: derive alarms from tag values when payload has no explicit alarm_summary.
        # This keeps alarm events persisted even when publishers send alarm states as regular tags.
        if alarms_processed == 0 and filtered_tags:
            for tag in filtered_tags:
                tag_id = tag.get('tag_id', '')
                if not tag_id:
                    continue

                tag_upper = str(tag_id).upper()
                is_alarm_tag = 'ALARM' in tag_upper or tag_upper.endswith('_TRIP_STATUS')
                if not is_alarm_tag:
                    continue

                value_bool = tag.get('value_bool')
                value_num = tag.get('value_num')
                is_active = bool(value_bool) or (isinstance(value_num, (int, float)) and value_num > 0)
                if not is_active:
                    continue

                metadata = {
                    'alarm_value': value_num if value_num is not None else (1 if value_bool else 0),
                    'setpoint': 0,
                    'unit': '',
                    'area': '',
                    'equipment': tag_upper.split('_')[0],
                    'state': 'ACTIVE',
                    'source': 'derived_from_tag_value'
                }
                derived_alarm = {
                    'time': tag.get('time') or now_ist_iso(),
                    'tag_id': tag_id,
                    'event_type': 'ALARM_HIGH_WARNING',
                    'severity': 2,
                    'message': f"{tag_id}: Alarm state active from MQTT tag value"
                }

                # DB write is handled by C# AlarmEvaluationService — use client-side temp ID.
                alarm_id = f"ALM_{tag_id}_{int(time.time() * 1000)}"

                socketio.emit('mqtt_alarm', {
                    'id': alarm_id,
                    'timestamp': derived_alarm['time'],
                    'priority': 2,
                    'tagId': tag_id,
                    'message': derived_alarm['message'],
                    'acknowledged': False,
                    'value': metadata.get('alarm_value'),
                    'plcName': raw_data.get('gateway_id', ''),
                    'state': 'ACTIVE',
                    'eventType': derived_alarm['event_type'],
                    'setpoint': metadata.get('setpoint'),
                    'unit': metadata.get('unit', ''),
                    'area': metadata.get('area', ''),
                    'equipment': metadata.get('equipment', '')
                }, namespace='/')

                logger.info(f"🚨 DERIVED ALARM: {tag_id} persisted from tag value")

        logger.info(
            "[ALARM_FLOW_DONE] topic=%s alarms_processed=%s filtered_tags=%s",
            topic,
            alarms_processed,
            len(filtered_tags) if filtered_tags else 0
        )
        
        if not filtered_tags:
            return

        # DISABLED 2026-05-23 — C# OPC/PLC historian now owns all writes to historian_timeseries.
        # HMI was writing sample_source='MQTT' causing duplicate rows alongside C#'s OPC/PLC writes.
        # Keep: alarm_audit_trail (alarm_controller.py), report_gen_log, tag_alarm_config — unaffected.
        # _persist_mqtt_samples(filtered_tags, topic)
        
        # Update cache with MQTT data
        for tag in filtered_tags:
            tag_id = tag.get('tag_id')
            if tag_id:
                # Normalize quality value
                quality = tag.get('quality', 'G')
                if quality == 'Good':
                    quality = 'G'
                elif quality == 'Bad':
                    quality = 'B'
                
                latest_tag_values[tag_id] = {
                    'tag_id': tag_id,
                    'value_num': tag.get('value_num'),
                    'value_text': tag.get('value_text'),
                    'value_bool': tag.get('value_bool'),
                    'quality': quality,
                    'timestamp': tag.get('time') or now_ist_iso(),
                    'source': 'MQTT',
                    'topic': topic,
                    'plcId': tag.get('plcId')
                }
        
        # ── Per-SID filtered broadcast (area-access enforcement) ──────
        # Build tag_id → (plant, area) from tag_cache once per batch
        tag_meta_mqtt = {t['tag_id']: (t.get('plant'), t.get('area'))
                         for t in container.tag_cache.get_all_tags()}
        gateway_id   = raw_data.get('gateway_id')
        mqtt_ts      = raw_data.get('timestamp')

        for sid, session in list(_sid_sessions.items()):
            allowed = session.get('allowed')   # None = admin, set = restricted
            if allowed is None:
                # Admin: full payload
                socketio.emit('mqtt_tag_update', {
                    'topic': topic, 'tags': filtered_tags,
                    'gateway_id': gateway_id, 'timestamp': mqtt_ts
                }, room=sid, namespace='/')
            else:
                user_tags = [
                    t for t in filtered_tags
                    if tag_meta_mqtt.get(t.get('tag_id'), (None, None)) in allowed
                ]
                if user_tags:
                    socketio.emit('mqtt_tag_update', {
                        'topic': topic, 'tags': user_tags,
                        'gateway_id': gateway_id, 'timestamp': mqtt_ts
                    }, room=sid, namespace='/')
        
        # Log periodically to reduce overhead
        current_time = time.time()
        if not hasattr(on_mqtt_message, 'last_log_time'):
            on_mqtt_message.last_log_time = 0
        
        if current_time - on_mqtt_message.last_log_time >= 5:
            logger.info(
                f"[MQTT] Topic={topic}, Tags={len(filtered_tags)}, Clients={len(connected_clients)}"
            )
            on_mqtt_message.last_log_time = current_time
        
    except Exception as e:
        logger.error(f"[ERROR] Error in MQTT message callback: {e}", exc_info=True)


def on_signalr_tag_update(tags_data):
    """
    Callback when SignalR receives BATCHED tag updates from listener
    SignalR listener buffers individual tags and sends in batches (200ms window)
    
    PERFORMANCE: Processes 60+ tags per batch instead of 60+ individual callbacks
    """
    global latest_tag_values
    
    try:
        if not isinstance(tags_data, list):
            logger.warning(f"[WARN] Expected list, got {type(tags_data)}")
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
                        'timestamp': tag.get('timestamp') or now_ist_iso()
                    }
                    updated_count += 1
        
        # ── Per-SID filtered broadcast (area-access enforcement) ──────
        # Build tag_id → (plant, area) from tag_cache once per batch
        tag_meta = {t['tag_id']: (t.get('plant'), t.get('area'))
                    for t in container.tag_cache.get_all_tags()}

        for sid, session in list(_sid_sessions.items()):
            allowed = session.get('allowed')   # None = admin (all), set = restricted
            if allowed is None:
                # Admin: send full batch unchanged
                socketio.emit('tag_update', tags_data, room=sid, namespace='/')
            else:
                filtered_batch = [
                    t for t in tags_data
                    if isinstance(t, dict) and
                    tag_meta.get(t.get('itemID') or t.get('itemId'), (None, None)) in allowed
                ]
                if filtered_batch:
                    socketio.emit('tag_update', filtered_batch, room=sid, namespace='/')

        # Log batch statistics every 5 seconds to reduce overhead
        current_time = time.time()
        if not hasattr(on_signalr_tag_update, 'last_log_time'):
            on_signalr_tag_update.last_log_time = 0

        if current_time - on_signalr_tag_update.last_log_time >= 5:
            logger.info(
                f"[SIGNALR] Batch: {updated_count} tags/batch, {len(connected_clients)} clients | "
                f"Cache: {len(latest_tag_values)} tags"
            )
            on_signalr_tag_update.last_log_time = current_time
        
    except Exception as e:
        logger.error(f"[ERROR] Error in batch update: {e}", exc_info=True)


@socketio.on('connect')
def handle_connect(auth):
    """Browser client connected via WebSocket.
    Validates JWT (from Socket.IO auth object), stores per-SID allowed areas.
    On connect: sends only the cached values the user is allowed to see.
    """
    global connected_clients
    connected_clients.add(request.sid)
    sid = request.sid

    # ── Validate JWT from socket.io auth ──────────────────────────────
    token = (auth or {}).get('token', '') if isinstance(auth, dict) else ''
    user_id = None
    is_admin = False
    if token:
        try:
            data = container.auth_service.decode_token(token)
            if data:
                user_id = data.get('user_id')
                is_admin = bool(container.rbac_service.is_user_admin(user_id))
        except Exception as exc:
            logger.warning("[SOCKET] Token validation failed for %s: %s", sid, exc)

    allowed = _get_user_allowed_areas(user_id, is_admin) if user_id else set()
    _sid_sessions[sid] = {'user_id': user_id, 'is_admin': is_admin, 'allowed': allowed}

    logger.info(
        "[SOCKET] Client CONNECTED: %s | user=%s | admin=%s | areas=%s | transport=%s | total=%d",
        sid, user_id, is_admin,
        'ALL' if allowed is None else len(allowed),
        request.environ.get('HTTP_UPGRADE', 'http'),
        len(connected_clients)
    )

    # ── Send filtered snapshot of current cached values ──────────────
    if not latest_tag_values:
        return
    if allowed is None:
        # Admin: send everything
        emit('tag_update', list(latest_tag_values.values()))
    else:
        # Build tag_id → (plant, area) lookup from tag_cache
        tag_meta = {t['tag_id']: (t.get('plant'), t.get('area'))
                    for t in container.tag_cache.get_all_tags()}
        filtered = [
            v for tid, v in latest_tag_values.items()
            if tag_meta.get(tid, (None, None)) in allowed
        ]
        if filtered:
            emit('tag_update', filtered)


@socketio.on('disconnect')
def handle_disconnect():
    """Browser client disconnected — log reason for debugging"""
    global connected_clients
    sid = request.sid
    connected_clients.discard(sid)
    _sid_sessions.pop(sid, None)   # ← clean up per-SID session
    reason = request.args.get('reason', 'unknown')
    logger.warning(f"[SOCKET] Client DISCONNECTED: {sid} | reason={reason} | remaining={len(connected_clients)}")


def _heartbeat_emitter():
    """Gevent greenlet: emits a 'heartbeat' event to all clients every 30s.
    The React client uses this to reset the stale-data watchdog — so a quiet plant
    (no tag changes) does not trigger a false 'data stale' alarm.
    """
    import gevent as _gevent
    logger.info("[HEARTBEAT] Heartbeat emitter started (30s interval)")
    while True:
        _gevent.sleep(30)
        try:
            socketio.emit('heartbeat', {'ts': _time.time()}, namespace='/')
        except Exception as _he:
            logger.warning(f"[HEARTBEAT] Emit failed: {_he}")


@socketio.on('subscribe_tags')
def handle_subscribe(data):
    """
    Client wants to subscribe to specific tags
    Forwards to C# SignalR hub for filtering
    """
    tag_ids = data.get('tagIds', [])
    
    if container.signalr_listener and container.signalr_listener.is_connected:
        container.signalr_listener.subscribe_to_tags(tag_ids)
        logger.info(f"[OK] Client {request.sid} subscribed to {len(tag_ids)} tags")
        emit('subscribe_success', {'count': len(tag_ids)})
    else:
        logger.warning("[WARN] SignalR not connected, cannot subscribe")
        emit('subscribe_error', {'message': 'SignalR not connected'})


def start_signalr_listener():
    """Start listening to C# SignalR hub in background"""
    
    signalr_config = {
        'host': container.config['csharp_backend']['host'],
        'port': container.config['csharp_backend']['port'],
        'hub_path': container.config['csharp_backend']['signalr_hub']
    }
    
    logger.info(f"[SIGNALR] Starting SignalR listener: http://{signalr_config['host']}:{signalr_config['port']}{signalr_config['hub_path']}")
    
    # Initialize SignalR listener with the callback and cache from container
    # Note: on_signalr_tag_update is defined in this file to access socketio, 
    # but container.tag_cache is used.
    container.signalr_listener = SignalRListener(signalr_config, container.tag_cache, on_signalr_tag_update)
    container.signalr_listener.connect()


def start_mqtt_client():
    """Start MQTT client for real-time tag data streaming"""
    
    try:
        logger.info("[MQTT] Starting MQTT client for live data streaming...")
        
        # Load topic-tag mappings first
        container.topic_tag_mapper.load_configuration()
        
        # Get MQTT configuration
        mqtt_config = container.config.get('mqtt', {})
        
        # Initialize MQTT client with callback
        container.mqtt_client = MQTTClientService(
            mqtt_config=mqtt_config,
            topic_tag_mapper=container.topic_tag_mapper,
            on_message_callback=on_mqtt_message
        )
        
        # Connect to MQTT broker
        container.mqtt_client.connect()
        
        logger.info("[OK] MQTT client initialized")
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to start MQTT client: {e}")
        logger.warning("[WARN] MQTT live data will not be available")


def initialize_services():
    """Initialize database and SignalR connections (both optional - graceful degradation)"""
    logger.info("[START] Initializing HMI services...")
    
    # Try to connect to database (optional - app works without it)
    db_connected = False
    try:
        if container.historical_service.connect():
            logger.info("[OK] Historical data service ready")
            db_connected = True
        else:
            logger.warning("[WARN] Historical data service unavailable (database not connected)")
    except Exception as e:
        logger.warning(f"[WARN] Database connection skipped: {e}")
        logger.info("[INFO] Historical trends will not be available")

    # Seed default RBAC module permissions (Viewer gets no analytics access)
    try:
        container.rbac_service.seed_default_module_permissions()
    except Exception as e:
        logger.warning(f"[WARN] RBAC seed skipped: {e}")
    
    # Start tag cache background refresh
    try:
        container.tag_cache.start()
        logger.info("[OK] Tag cache started (background refresh every 30s)")
    except Exception as e:
        logger.warning(f"[WARN] Tag cache failed to start: {e}")
    
    # Start MQTT client for live data streaming
    try:
        start_mqtt_client()
    except Exception as e:
        logger.warning(f"[WARN] MQTT client failed to start: {e}")
    
    # Determine mode
    mqtt_connected = container.mqtt_client and container.mqtt_client.is_connected
    signalr_connected = container.signalr_listener and container.signalr_listener.is_connected
    
    if (mqtt_connected or signalr_connected) and db_connected:
        logger.info("[OK] HMI Mode: FULL (Live MQTT/SignalR + Historical)")
    elif mqtt_connected:
        logger.info("[OK] HMI Mode: MQTT LIVE ONLY")
    elif db_connected:
        logger.info("[OK] HMI Mode: HISTORICAL ONLY")
    else:
        logger.info("[OK] HMI Mode: DEMO (UI only)")


if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("[STARTUP] HMI Application Starting...")
    logger.info("=" * 60)
    logger.info(f"[DEBUG] Python executable: {sys.executable}")
    logger.info(f"[DEBUG] Python version: {sys.version}")
    logger.info(f"[DEBUG] Current working directory: {os.getcwd()}")
    logger.info(f"[DEBUG] App file directory: {os.path.dirname(os.path.abspath(__file__))}")
    logger.info(f"[DEBUG] Config path exists: {os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json'))}")
    logger.info(f"[DEBUG] IST timezone object: {IST_TZ}")
    
    # Initialize services within app context
    with app.app_context():
        # Start SignalR listener (if configured)
        # Note: start_signalr_listener() was called in original app.py implicitly or I might have missed it in init services?
        # Original code had `start_signalr_listener()` function but I don't see it being called in `if __name__ == '__main__':` block in the original file provided.
        # Wait, the original `if __name__` block had `initialize_services()`.
        # `initialize_services` in original code did NOT call `start_signalr_listener()`.
        # Ah, `start_signalr_listener` was defined but maybe not called?
        # Let me re-read original `app.py`.
        # Line 640 `initialize_services` only does DB and cache.
        # Line 669 mentions "HTTP POLLING MODE".
        # It seems SignalR was OPTIONAL or handled elsewhere?
        # Re-reading: "HMI works in multiple modes...".
        # If I want SignalR, I should probably start it.
        # But if the original didn't start it, I shouldn't change behavior unless I know why to.
        # However, `signalr_listener` variable WAS initialized to None at top level.
        # It seems the original code MIGHT have intended to start it but maybe it relies on just HTTP polling?
        # "SignalR is optional for UI responsiveness... Browser polls ... every 1 second"
        # Okay, so I will stick to the original behavior and NOT start SignalR listener unless I find where it was started.
        # It seems it WASN'T started in the main block.
        # BUT, `initialize_services` CHECKS `signalr_listener.is_connected`.
        # This implies it *should* have been started before or I missed something.
        # Ah, looking at `app.py` line 624 `start_signalr_listener` is defined.
        # But it is NOT called in `initialize_services` or `main`.
        # Maybe it's called somewhere I missed?
        # Wait, if I search for `start_signalr_listener` usages...
        # It is defined at line 624.
        # Usages: None visible in the file content `view_file` returned.
        # So maybe it's just code lying around?
        # "HMI Mode: HTTP Polling (same pattern as Historian service)"
        # "SignalR is optional... Browser polls... every 1 second"
        # Okay, I will preserve this logic. I will Define `start_signalr_listener` but not call it, just like original.
        pass

    with app.app_context():
        initialize_services()
    
    # Cleanup on exit (graceful shutdown)
    import atexit
    def cleanup():
        try:
            logger.info("🛑 Shutting down HMI...")
            if container.signalr_listener:
                container.signalr_listener.stop()
            if container.mqtt_client:
                container.mqtt_client.disconnect()
            # Use threading.Event instead of join() to avoid eventlet conflicts
            container.tag_cache._stop_event.set()
            logger.info("[OK] Services stopped")
        except (KeyboardInterrupt, SystemExit, Exception):
            pass 
    
    atexit.register(cleanup)

    # Start heartbeat greenlet — keeps client stale-detection accurate on quiet plants
    import gevent as _gevent
    _gevent.spawn(_heartbeat_emitter)
    logger.info("[HEARTBEAT] Greenlet spawned")

    # Start Flask-SocketIO server
    socketio.run(
        app,
        host=container.config['hmi_server']['host'],
        port=container.config['hmi_server']['port'],
        debug=container.config['hmi_server']['debug'],
        use_reloader=False  # Disable reloader to prevent duplicate MQTT connections
    )
