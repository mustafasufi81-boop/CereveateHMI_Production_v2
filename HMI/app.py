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
import random
from datetime import datetime, timedelta, timezone, timezone
from zoneinfo import ZoneInfo
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from flask import Flask, request
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from services.signalr_listener import SignalRListener
from services.mqtt_client_service import MQTTClientService
from container import container
import db_pool

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
    """Detailed system status — OPC/DB/MQTT/SignalR/REST-fallback details."""
    import time as _time
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
    # SignalR
    signalr_ok = False
    try:
        signalr_ok = bool(container.signalr_listener and container.signalr_listener.is_connected)
    except Exception:
        signalr_ok = False

    # Fix #3: transport state snapshot (safe copy under lock)
    with _rest_lock:
        ts = dict(_transport_state)

    from flask import jsonify as _jsonify
    return _jsonify({
        'flask':    {'ok': True, 'uptime_s': round(_time.time() - _flask_start_time)},
        'db':       {'ok': db_ok},
        'mqtt':     {'ok': mqtt_ok},
        'signalr':  {'ok': signalr_ok},
        'transport': {
            'active_source':    ts['active_source'],
            'mqtt_alive':       ts['mqtt_alive'],
            'signalr_alive':    ts['signalr_alive'],
            'fallback_active':  ts['fallback_active'],
            'rest_backoff_s':   ts['rest_backoff_s'],
            'rest_poll_count':  ts['rest_poll_count'],
            'rest_error_count': ts['rest_error_count'],
            'rest_last_error':  ts['rest_last_error'],
        },
        'clients':   len(connected_clients),
        'cacheSize': len(latest_tag_values),
        'ts':        _time.time(),
    }), 200


@app.route('/api/source-status', methods=['GET'])
def api_source_status():
    """Return per-server_progid connection status.

    Logic:
    - Query DB for all distinct server_progid values that have at least one
      enabled tag configured (server_progid IS NOT NULL AND enabled = true).
    - For each source, check if any tag from that source has a live value in
      the in-memory cache (latest_tag_values) with a timestamp fresher than
      60 seconds.
    - Status per source:
        'live'          — ≥1 tag with fresh data in cache
        'disconnected'  — tags configured but NO fresh data arriving
    - If NO sources are configured in DB, returns empty list (nothing to show).
    """
    from flask import jsonify as _jsonify
    import time as _t
    from datetime import datetime, timezone

    now_utc = datetime.now(timezone.utc)
    sources = []

    try:
        conn = db_pool.get_conn()
        cur = conn.cursor()

        # Get all distinct server_progids with enabled tags + their tag names
        cur.execute("""
            SELECT server_progid, array_agg(tag_name) AS tag_names, COUNT(*) AS tag_count
            FROM historian_meta.tag_master
            WHERE server_progid IS NOT NULL AND server_progid <> '' AND enabled = true
            GROUP BY server_progid
            ORDER BY server_progid
        """)
        rows = cur.fetchall()
        cur.close()
        db_pool.return_conn(conn)

        for (progid, tag_names, tag_count) in rows:
            # Check cache for any live value from this source's tags
            live_count = 0
            for tname in (tag_names or []):
                cached = latest_tag_values.get(tname) or latest_tag_values.get(str(tname))
                if not cached:
                    # Also try by tag_id numeric key
                    continue
                ts_str = cached.get('timestamp') or cached.get('cachedAt') or cached.get('time')
                if not ts_str:
                    continue
                try:
                    from dateutil import parser as _dp
                    ts = _dp.parse(ts_str)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    age_s = (now_utc - ts).total_seconds()
                    if age_s <= 60:
                        live_count += 1
                except Exception:
                    pass

            sources.append({
                'server_progid': progid,
                'tag_count': tag_count,
                'live_tag_count': live_count,
                # disconnected = source is configured but zero fresh tags
                'status': 'live' if live_count > 0 else 'disconnected',
            })

    except Exception as e:
        logger.warning(f'[source-status] DB query failed: {e}')
        return _jsonify({'sources': [], 'error': str(e)}), 200

    return _jsonify({'sources': sources}), 200


@app.route('/api/opc-plc-status', methods=['GET'])
def api_opc_plc_status():
    """Proxy OPC and PLC connection status from the C# backend.

    Calls:
      GET http://localhost:5001/api/health/opc   → OPC server status
      GET http://localhost:5001/api/plc/connections   → PLC gateway status

    Returns combined JSON so the React frontend only needs one call to know
    whether the OPC server and/or any PLC is disconnected.
    """
    from flask import jsonify as _jsonify
    import requests as _req

    cfg = container.config.get('csharp_backend', {})
    base = f"http://{cfg.get('host', 'localhost')}:{cfg.get('port', 5001)}"
    timeout = 3.0

    opc_data = {}
    plc_data = {}
    errors = []

    try:
        r = _req.get(f"{base}/api/health/opc", timeout=timeout)
        r.raise_for_status()
        opc_data = r.json()
    except Exception as e:
        errors.append(f"opc: {e}")
        opc_data = {'status': 'Unknown', 'error': str(e)}

    try:
        r = _req.get(f"{base}/api/plc/connections", timeout=timeout)
        r.raise_for_status()
        plc_data = r.json()
    except Exception as e:
        errors.append(f"plc: {e}")
        plc_data = {'success': False, 'connections': [], 'error': str(e)}

    # Derive simple connected flags
    opc_connected = opc_data.get('status', '').lower() == 'connected'
    # C# returns { connections: [...], isConnected: bool } per PLC
    plcs = plc_data.get('connections', plc_data.get('plcs', []))
    any_plc_disconnected = any(
        not p.get('isConnected', True)
        for p in plcs
        if p.get('enabled', True)
    )

    return _jsonify({
        'opc': {
            'connected': opc_connected,
            'status':    opc_data.get('status', 'Unknown'),
            'serverName': opc_data.get('serverName', ''),
            'tagsConnected': opc_data.get('tagsConnected', 0),
            'healthScore': opc_data.get('healthScore', 0),
            'lastError': opc_data.get('lastError'),
        },
        'plcs': [
            {
                'id':        p.get('plcId') or p.get('id') or p.get('name', ''),
                'name':      p.get('name', ''),
                'connected': bool(p.get('isConnected', False)),
                'protocol':  p.get('protocol', ''),
                'ipAddress': p.get('ipAddress', ''),
                'lastError': p.get('lastError', ''),
                'tagCount':  p.get('tagCount', 0),
                'lastUpdate': p.get('lastUpdate', ''),
            }
            for p in plcs
        ],
        'anyPlcDisconnected': any_plc_disconnected,
        'backendReachable': len(errors) < 2,
        'errors': errors if errors else None,
    }), 200


# ── Admin Cache Management ──────────────────────────────────────────────────

@app.route('/api/admin/cache/flush', methods=['POST'])
def admin_cache_flush():
    """Admin-only: flush the in-memory tag-value cache and re-seed from DB.
    Does NOT touch sessions, tokens, or any other application state.
    Requires a valid non-partial JWT belonging to an admin user.
    """
    from flask import jsonify as _jsonify
    # ── Auth check ─────────────────────────────────────────────────────────
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return _jsonify({'message': 'Authorisation required'}), 401
    token = auth_header.split(' ', 1)[1]
    token_data = container.auth_service.decode_token(token)
    if not token_data or token_data.get('partial'):
        return _jsonify({'message': 'Invalid or partial token'}), 401
    # Must be admin
    try:
        is_admin = container.rbac_service.is_user_admin(token_data['user_id'])
    except Exception:
        is_admin = False
    if not is_admin:
        return _jsonify({'message': 'Admin access required'}), 403
    # ── Flush ──────────────────────────────────────────────────────────────
    global latest_tag_values
    before = len(latest_tag_values)
    latest_tag_values.clear()
    logger.warning(
        "[CACHE] Admin cache flush: %d entries cleared by user_id=%s (%s)",
        before, token_data['user_id'], token_data.get('username', '?')
    )
    # Re-seed from DB so operators don't stare at a blank screen
    try:
        _seed_tag_cache_from_db()
        after = len(latest_tag_values)
        logger.info("[CACHE] Re-seeded %d tags from DB after flush", after)
    except Exception as _exc:
        logger.warning("[CACHE] Re-seed after flush failed (non-fatal): %s", _exc)
        after = 0
    # Audit trail
    try:
        container.audit_service.log_action(
            user_id=token_data['user_id'],
            username=token_data.get('username', '?'),
            action_type='CACHE_FLUSH',
            action_category='admin',
            target_entity='tag_value_cache',
            additional_data={'cleared': before, 'reseeded': after},
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
        )
    except Exception:
        pass  # audit failure must never block the operation
    return _jsonify({
        'message': 'Tag value cache flushed and re-seeded',
        'cleared': before,
        'reseeded': after,
    }), 200


# Start predictive engine
try:
    from services.predictive_alarm_engine import engine_instance as _pred_engine
    _pred_engine().start()
    logger.info("[OK] Predictive alarm engine started")
except Exception as _e:
    logger.warning("[WARN] Predictive engine failed to start: %s", _e)# RBAC Middleware
@app.before_request
def check_rbac_permissions():
    """
    Enforce RBAC permissions on protected endpoints
    """
    # Log all incoming requests — never log request body (may contain credentials)
    logger.info("[HTTP] %s %s from %s", request.method, request.path, request.remote_addr)
    if request.headers.get('Authorization'):
        token_preview = request.headers.get('Authorization')[:30]
        logger.debug("[AUTH] Authorization header present: %s...", token_preview)
    # (No else-branch logging — avoids noise for public/unauthenticated endpoints)
    
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
latest_tag_values = {}
connected_clients = set()

# ── REST Fallback Transport State (Fix #3) ────────────────────────────────────
# Tracks MQTT/SignalR health and controls REST poller lifecycle.
# All fields read/written only from the REST poller greenlet or MQTT callbacks
# (gevent cooperative — no real threading race, but _rest_lock guards the few
#  fields that MQTT callback and poller greenlet both touch).
import threading as _threading
_rest_lock = _threading.Lock()

_transport_state = {
    # Transport liveness (set by callbacks + poller)
    "mqtt_alive":         False,   # True while MQTT is delivering messages
    "signalr_alive":      False,   # True while SignalR is delivering messages
    # Fix #4 — source arbitration
    "active_source":      "NONE",  # "MQTT" | "SIGNALR" | "REST" | "NONE"
    "mqtt_stable_since":  None,    # monotonic time MQTT first became alive (for hysteresis)
    "signalr_stable_since": None,  # monotonic time SignalR first became alive (for hysteresis)
    # Fallback control
    "fallback_active":    False,   # True when REST polling is running
    "grace_start":        None,    # monotonic time when grace period began
    "grace_cancelled":    False,   # True if MQTT/SignalR recovered during grace
    # REST poller internals
    "rest_inflight":      False,   # single-flight guard
    "rest_backoff_s":     1.0,     # current backoff interval
    "rest_consecutive_ok": 0,      # successes since last error
    "rest_last_error":    None,    # last error string
    # Metrics for health endpoint / debugging
    "last_mqtt_msg_at":   None,    # monotonic time of last MQTT message
    "last_signalr_msg_at":None,
    "last_rest_ok_at":    None,
    "rest_poll_count":    0,
    "rest_error_count":   0,
}

_REST_GRACE_S          = 30      # seconds before REST activates after transport loss
_REST_POLL_INTERVAL_S  = 1.0    # target interval between REST polls
_REST_TIMEOUT_S        = 4.0    # per-request timeout (< poll interval to avoid pileup)
_REST_BACKOFF_STEPS    = [1, 2, 4, 8, 30]  # backoff ladder (seconds)
_REST_BACKOFF_JITTER   = 1.5    # max uniform jitter added to each backoff step
_REST_STABLE_SUCCESSES = 3      # consecutive successes needed to reset backoff
_PROMOTE_STABLE_S      = 5      # Fix #4: seconds a transport must be alive before promotion
# ──────────────────────────────────────────────────────────────────────────────


def _update_active_source():
    """
    Fix #4 — Source Arbitration (MUST be called under _rest_lock).
    Priority: MQTT > SIGNALR > REST > NONE
    Hysteresis: a transport must deliver messages for _PROMOTE_STABLE_S
    consecutive seconds before it is promoted to active_source.
    This prevents rapid MQTT ↔ REST oscillation on flapping connections.
    Logs every source transition for field debugging.
    """
    now = time.monotonic()
    ts  = _transport_state

    # ── Update per-transport stability timers ──────────────────────────────────
    if ts["mqtt_alive"]:
        if ts["mqtt_stable_since"] is None:
            ts["mqtt_stable_since"] = now
    else:
        ts["mqtt_stable_since"] = None

    if ts["signalr_alive"]:
        if ts["signalr_stable_since"] is None:
            ts["signalr_stable_since"] = now
    else:
        ts["signalr_stable_since"] = None

    # ── Determine candidate source (with hysteresis) ───────────────────────────
    mqtt_stable    = (ts["mqtt_stable_since"] is not None
                      and (now - ts["mqtt_stable_since"]) >= _PROMOTE_STABLE_S)
    signalr_stable = (ts["signalr_stable_since"] is not None
                      and (now - ts["signalr_stable_since"]) >= _PROMOTE_STABLE_S)

    if mqtt_stable:
        new_source = "MQTT"
    elif signalr_stable:
        new_source = "SIGNALR"
    elif ts["fallback_active"]:
        new_source = "REST"
    else:
        new_source = "NONE"

    # ── Log and apply transition ───────────────────────────────────────────────
    old_source = ts["active_source"]
    if new_source != old_source:
        ts["active_source"] = new_source
        mqtt_age = (round(now - ts["last_mqtt_msg_at"], 1)
                    if ts["last_mqtt_msg_at"] else None)
        sig_age  = (round(now - ts["last_signalr_msg_at"], 1)
                    if ts["last_signalr_msg_at"] else None)
        logger.info(
            "[TRANSPORT] ACTIVE SOURCE: %s → %s  "
            "(mqtt_age=%ss  signalr_age=%ss  stable_window=%ds)",
            old_source, new_source, mqtt_age, sig_age, _PROMOTE_STABLE_S
        )

# ── Per-SID session store: maps socket SID → allowed (plant, area) set or None(=admin)
# Populated on connect, cleaned on disconnect.  None means no filtering (admin).
_sid_sessions: dict = {}   # { sid: {"user_id": int, "is_admin": bool, "allowed": set|None} }


def _seed_tag_cache_from_db():
    """Seed latest_tag_values from the DB on startup so cards are populated
    immediately on the first Socket.IO connect, even after a Flask restart."""
    global latest_tag_values
    try:
        with db_pool.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT ON (tag_id)
                        tag_id,
                        value_num,
                        value_text,
                        quality,
                        sample_time AS "timestamp"
                    FROM historian_raw.historian_timeseries
                    WHERE sample_time >= NOW() - INTERVAL '1 hour'
                    ORDER BY tag_id, sample_time DESC
                """)
                rows = cur.fetchall()
        for row in rows:
            if isinstance(row, dict):
                tag_id = row.get('tag_id')
                ts = row.get('timestamp')
            else:
                tag_id, value_num, value_text, quality, ts = row[0], row[1], row[2], row[3], row[4]
            if not tag_id:
                continue
            ts_str = ts.isoformat() if hasattr(ts, 'isoformat') else str(ts)
            if isinstance(row, dict):
                latest_tag_values[tag_id] = {
                    'tag_id': tag_id,
                    'value_num': row.get('value_num'),
                    'value_text': row.get('value_text'),
                    'quality': row.get('quality', 'G'),
                    'timestamp': ts_str,
                    'source': 'DB_SEED',
                }
            else:
                latest_tag_values[tag_id] = {
                    'tag_id': tag_id,
                    'value_num': value_num,
                    'value_text': value_text,
                    'quality': quality or 'G',
                    'timestamp': ts_str,
                    'source': 'DB_SEED',
                }
        logger.info("[STARTUP] Seeded latest_tag_values with %d tags from DB", len(latest_tag_values))
    except Exception as exc:
        logger.warning("[STARTUP] Could not seed tag cache from DB (non-fatal): %s", exc)


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


def _compute_age_ms(ts_str) -> int | None:
    """
    Fix #5 — Cache Age/Freshness.
    Compute how many milliseconds ago a tag value was timestamped.
    Returns None if timestamp is unparseable.
    The result is included in every tag value dict as 'age_ms' so the UI
    can display a stale-data warning when age_ms exceeds a threshold.
    """
    if not ts_str:
        return None
    try:
        dt = _parse_sample_time(ts_str)
        now_utc = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST_TZ)
        delta_ms = int((now_utc - dt.astimezone(timezone.utc)).total_seconds() * 1000)
        return max(0, delta_ms)   # clamp: never return negative age
    except Exception:
        return None


# Fix #5 — stale policy thresholds
_STALE_THRESHOLD_MS = 5_000    # > 5s  → quality overridden to 'STALE'
_MAX_AGE_MS         = 30_000   # > 30s → quality overridden to 'EXPIRED' (Last Good Value still served)

def _apply_stale_policy(entry: dict) -> dict:
    """
    Fix #5 — Last Good Value stale policy.
    Overrides 'quality' in-place based on age_ms:
      age_ms > _MAX_AGE_MS         → 'EXPIRED'  (value shown as --- on UI)
      age_ms > _STALE_THRESHOLD_MS → 'STALE'    (value shown greyed-out)
      otherwise                    → quality unchanged (Good/G/Bad/B from source)
    Always returns the same dict for chaining.
    """
    age = entry.get('age_ms')
    if age is None:
        return entry
    if age > _MAX_AGE_MS:
        entry['quality'] = 'EXPIRED'
    elif age > _STALE_THRESHOLD_MS:
        entry['quality'] = 'STALE'
    return entry


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
    """
    global latest_tag_values

    # ── Fix #3 + #4: stamp MQTT liveness and re-arbitrate source ──
    with _rest_lock:
        _transport_state["last_mqtt_msg_at"] = time.monotonic()
        if not _transport_state["mqtt_alive"]:
            _transport_state["mqtt_alive"] = True
            _transport_state["grace_cancelled"] = True   # cancel any running grace timer
            if _transport_state["fallback_active"]:
                logger.info("[TRANSPORT] MQTT recovered → REST fallback will deactivate")
        _update_active_source()

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
                
                ts_val = tag.get('time') or now_ist_iso()
                latest_tag_values[tag_id] = _apply_stale_policy({
                    'tag_id': tag_id,
                    'value_num': tag.get('value_num'),
                    'value_text': tag.get('value_text'),
                    'value_bool': tag.get('value_bool'),
                    'quality': quality,
                    'timestamp': ts_val,
                    'source': 'MQTT',
                    'topic': topic,
                    'plcId': tag.get('plcId'),
                    'age_ms': _compute_age_ms(ts_val),
                })
        
        # ── Per-SID filtered broadcast (area-access enforcement) ──────
        # Build tag_id → (plant, area) from tag_cache once per batch
        tag_meta_mqtt = {t['tag_id']: (t.get('plant'), t.get('area'))
                         for t in container.tag_cache.get_all_tags()}
        gateway_id   = raw_data.get('gateway_id')
        mqtt_ts      = raw_data.get('timestamp')

        for sid, session in list(_sid_sessions.items()):
            user_id   = session.get('user_id')
            is_admin  = session.get('is_admin', False)

            # Re-fetch permissions live so admin changes take effect immediately
            # (avoids stale permissions cached at connect time)
            allowed = _get_user_allowed_areas(user_id, is_admin) if user_id else set()
            # Keep session up-to-date so the snapshot on reconnect is also fresh
            session['allowed'] = allowed

            if allowed is None:
                # Admin: full payload
                socketio.emit('mqtt_tag_update', {
                        'topic': topic, 'tags': filtered_tags,
                        'gateway_id': gateway_id, 'timestamp': mqtt_ts
                    }, room=sid, namespace='/')
            else:
                user_tags = [
                    t for t in filtered_tags
                    if (
                        # Tags with no plant/area (e.g. PLC tags) are visible to all
                        # authenticated users — they have no area restriction to enforce
                        tag_meta_mqtt.get(t.get('tag_id'), (None, None)) == (None, None)
                        or tag_meta_mqtt.get(t.get('tag_id'), (None, None)) in allowed
                    )
                ]
                if user_tags:
                    socketio.emit('mqtt_tag_update', {
                            'topic': topic, 'tags': user_tags,
                            'gateway_id': gateway_id, 'timestamp': mqtt_ts
                        }, room=sid, namespace='/')        # Log periodically to reduce overhead
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
    Callback when SignalR receives BATCHED tag updates from listener.
    """
    global latest_tag_values

    # ── Fix #3 + #4: stamp SignalR liveness and re-arbitrate source ──
    with _rest_lock:
        _transport_state["last_signalr_msg_at"] = time.monotonic()
        if not _transport_state["signalr_alive"]:
            _transport_state["signalr_alive"] = True
            _transport_state["grace_cancelled"] = True
            if _transport_state["fallback_active"]:
                logger.info("[TRANSPORT] SignalR recovered → REST fallback will deactivate")
        _update_active_source()
        current_source = _transport_state["active_source"]

    try:
        if not isinstance(tags_data, list):
            logger.warning(f"[WARN] Expected list, got {type(tags_data)}")
            return
        
        if len(tags_data) == 0:
            return
        
        # Fix #4: only write to cache if MQTT is not the active source.
        # MQTT has higher priority — never let SignalR overwrite fresher MQTT values.
        updated_count = 0
        if current_source != "MQTT":
            for tag in tags_data:
                if isinstance(tag, dict):
                    tag_id = tag.get('itemID') or tag.get('itemId')
                    if tag_id:
                        ts_val = tag.get('timestamp') or now_ist_iso()
                        latest_tag_values[tag_id] = _apply_stale_policy({
                            'value': tag.get('value'),
                            'quality': tag.get('quality'),
                            'timestamp': ts_val,
                            'source': 'SIGNALR',
                            'age_ms': _compute_age_ms(ts_val),
                        })
                        updated_count += 1
        else:
            # MQTT is active — count tags for logging but skip cache write
            updated_count = sum(1 for t in tags_data
                                if isinstance(t, dict) and (t.get('itemID') or t.get('itemId')))
        
        # ── Per-SID filtered broadcast (area-access enforcement) ──────
        # Build tag_id → (plant, area) from tag_cache once per batch
        tag_meta = {t['tag_id']: (t.get('plant'), t.get('area'))
                    for t in container.tag_cache.get_all_tags()}

        for sid, session in list(_sid_sessions.items()):
            user_id  = session.get('user_id')
            is_admin = session.get('is_admin', False)
            allowed  = _get_user_allowed_areas(user_id, is_admin) if user_id else set()
            session['allowed'] = allowed   # keep session fresh

            if allowed is None:
                # Admin: send full batch unchanged
                socketio.emit('tag_update', tags_data, room=sid, namespace='/')
            else:
                filtered_batch = [
                    t for t in tags_data
                    if isinstance(t, dict) and (
                        tag_meta.get(t.get('itemID') or t.get('itemId'), (None, None)) == (None, None)
                        or tag_meta.get(t.get('itemID') or t.get('itemId'), (None, None)) in allowed
                    )
                ]
                if filtered_batch:
                    socketio.emit('tag_update', filtered_batch, room=sid, namespace='/')        # Log batch statistics every 5 seconds to reduce overhead
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
            # Tags with no plant/area (e.g. PLC/OPC tags) are visible to all
            # authenticated users — same rule as the MQTT broadcast in on_mqtt_message.
            if tag_meta.get(tid, (None, None)) == (None, None)
            or tag_meta.get(tid, (None, None)) in allowed
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


# ── Step 4 — Dispatcher Metrics Persistence ──────────────────────────────────
# Two write modes in one greenlet:
#   SNAPSHOT    — every 60s regardless of change (trend/p95 queries)
#   STATE_CHANGE — immediately when state string changes
#   REJECTION   — immediately when rejectedCount increases
#   TIMEOUT     — immediately when timeoutCount increases
#
# Table: historian_analytics.dispatcher_metrics
# DDL:   HMI/migrations/dispatcher_metrics_table.sql  (run once manually)
# ─────────────────────────────────────────────────────────────────────────────
_DISP_POLL_S   = 5.0    # how often we read the backend (lightweight)
_DISP_SNAP_S   = 60.0   # how often we force a SNAPSHOT row


def _fetch_dispatcher_snap() -> dict | None:
    """Pull /api/health/dispatcher from C# backend. Returns normalised dict or None."""
    try:
        import requests as _req
        cfg      = container.config.get('csharp_backend', {})
        url      = f"http://{cfg.get('host', 'localhost')}:{cfg.get('port', 5001)}/api/health/dispatcher"
        resp     = _req.get(url, timeout=3)
        if resp.status_code == 200:
            raw = resp.json()
            # normalise keys to lowercase
            return {k.lower(): v for k, v in raw.items()}
    except Exception:
        pass
    return None


def _persist_dispatcher_row(snap: dict, event_type: str) -> None:
    """Insert one row into historian_analytics.dispatcher_metrics."""
    try:
        with db_pool.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO historian_analytics.dispatcher_metrics (
                        recorded_at, event_type,
                        thread_id, apartment,
                        queue_depth, max_queue_depth,
                        rejected_count, ops_processed, timeout_count,
                        state, state_reason, last_state_change_utc,
                        last_success, last_heartbeat, last_error
                    ) VALUES (
                        NOW(), %s,
                        %s, %s,
                        %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s
                    )
                """, (
                    event_type,
                    snap.get('threadid'),
                    snap.get('apartment'),
                    snap.get('queuedepth'),
                    snap.get('maxqueuedepth'),
                    snap.get('rejectedcount'),
                    snap.get('operationsprocessed'),
                    snap.get('timeoutcount'),
                    snap.get('state'),
                    snap.get('statereason'),
                    snap.get('laststatechangeutc'),
                    snap.get('lastsuccess'),
                    snap.get('lastheartbeat'),
                    snap.get('lasterror'),
                ))
                conn.commit()
    except Exception as _e:
        logger.warning("[DISP_METRICS] DB write failed (%s): %s", event_type, _e)


def _dispatcher_metrics_persister():
    """Gevent greenlet — polls dispatcher health and persists to PostgreSQL.
    Writes a SNAPSHOT row every 60s plus event-based rows on significant changes.
    Silently skips if backend is unreachable or table doesn't exist yet.
    """
    import gevent as _gevent
    logger.info("[DISP_METRICS] Persistence greenlet started (poll=%ds, snap=%ds)",
                int(_DISP_POLL_S), int(_DISP_SNAP_S))

    last_snap_at     = 0.0
    last_state       = None
    last_rejected    = None
    last_timeout     = None

    while True:
        _gevent.sleep(_DISP_POLL_S)
        snap = _fetch_dispatcher_snap()
        if snap is None:
            continue

        now           = _time.time()
        cur_state     = snap.get('state')
        cur_rejected  = snap.get('rejectedcount', 0)
        cur_timeout   = snap.get('timeoutcount',  0)

        # ── event-based rows ─────────────────────────────────────────────────
        if last_state is not None and cur_state != last_state:
            _persist_dispatcher_row(snap, 'STATE_CHANGE')
            logger.info("[DISP_METRICS] STATE_CHANGE %s -> %s", last_state, cur_state)

        elif last_rejected is not None and cur_rejected > last_rejected:
            _persist_dispatcher_row(snap, 'REJECTION')
            logger.warning("[DISP_METRICS] REJECTION delta=%d total=%d",
                           cur_rejected - last_rejected, cur_rejected)

        elif last_timeout is not None and cur_timeout > last_timeout:
            _persist_dispatcher_row(snap, 'TIMEOUT')
            logger.warning("[DISP_METRICS] TIMEOUT delta=%d total=%d",
                           cur_timeout - last_timeout, cur_timeout)

        # ── periodic snapshot ─────────────────────────────────────────────────
        elif (now - last_snap_at) >= _DISP_SNAP_S:
            _persist_dispatcher_row(snap, 'SNAPSHOT')
            last_snap_at = now

        last_state    = cur_state
        last_rejected = cur_rejected
        last_timeout  = cur_timeout


@app.route('/api/metrics/dispatcher/history', methods=['GET'])
def api_dispatcher_metrics_history():
    """Query persisted dispatcher metrics.
    Query params:
      hours      — lookback window in hours (default: 24, max: 168)
      limit      — max rows returned (default: 200, max: 1000)
      state      — filter by state string (optional, e.g. 'Degraded')
      event_type — filter by event type (optional, e.g. 'STATE_CHANGE')
    """
    from flask import jsonify as _jsonify, request as _req
    try:
        hours      = min(int(_req.args.get('hours',      24)),  168)
        limit      = min(int(_req.args.get('limit',     200)), 1000)
        state_f    = _req.args.get('state')
        event_f    = _req.args.get('event_type')
    except ValueError:
        return _jsonify({'error': 'invalid query parameter'}), 400

    filters = ["recorded_at >= NOW() - INTERVAL '%s hours'"]
    params  = [hours]
    if state_f:
        filters.append("state = %s")
        params.append(state_f)
    if event_f:
        filters.append("event_type = %s")
        params.append(event_f)
    where = ' AND '.join(filters)

    try:
        with db_pool.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT
                        id, recorded_at, event_type,
                        thread_id, apartment,
                        queue_depth, max_queue_depth,
                        rejected_count, ops_processed, timeout_count,
                        state, state_reason, last_state_change_utc,
                        last_success, last_heartbeat, last_error
                    FROM historian_analytics.dispatcher_metrics
                    WHERE {where}
                    ORDER BY recorded_at DESC
                    LIMIT %s
                """, params + [limit])
                cols = [d[0] for d in cur.description]
                rows = [
                    {c: (v.isoformat() if hasattr(v, 'isoformat') else v)
                     for c, v in zip(cols, row)}
                    for row in cur.fetchall()
                ]
        return _jsonify({'count': len(rows), 'hours': hours, 'rows': rows}), 200
    except Exception as _e:
        logger.error("[DISP_METRICS] Query failed: %s", _e)
        return _jsonify({'error': 'query failed', 'detail': str(_e)}), 500


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


def _rest_fallback_poller():
    """
    Fix #3 — REST Fallback Poller (gevent greenlet)
    ================================================
    Lifecycle:
      1. Continuously monitors MQTT/SignalR liveness (message age > 10s = dead).
      2. On transport loss: starts 30s grace period.
         - If MQTT/SignalR recovers within grace → cancel, never activate REST.
      3. After grace expires: activates REST polling at 1s intervals.
         - Single-flight guard: skips tick if previous request still in-flight.
         - Per-request timeout: 4s (prevents stale inflight blocking next cycle).
         - Exponential backoff + jitter on errors: 1→2→4→8→30s cap.
         - Backoff resets after _REST_STABLE_SUCCESSES consecutive successes.
      4. On MQTT/SignalR recovery: deactivates REST, resets state, logs transition.
    """
    import gevent as _gevent
    try:
        import requests as _requests
    except ImportError:
        logger.error("[REST_FALLBACK] 'requests' not installed — REST fallback disabled")
        return

    cfg = container.config.get('csharp_backend', {})
    base_url = f"http://{cfg.get('host', 'localhost')}:{cfg.get('port', 5001)}"
    opc_values_url = f"{base_url}/api/opc/values"
    plc_values_url = f"{base_url}/api/plc/values"   # S1-7: Add PLC REST fallback

    # How long without a message before we consider a transport dead
    _LIVENESS_TIMEOUT_S = 10.0

    logger.info("[REST_FALLBACK] Poller greenlet started (grace=%ds, poll=%.1fs, timeout=%.1fs)",
                _REST_GRACE_S, _REST_POLL_INTERVAL_S, _REST_TIMEOUT_S)

    while True:
        _gevent.sleep(_REST_POLL_INTERVAL_S)
        now = time.monotonic()

        # ── 1. Determine transport liveness ──────────────────────────────────
        with _rest_lock:
            last_mqtt = _transport_state["last_mqtt_msg_at"]
            last_sig  = _transport_state["last_signalr_msg_at"]

        mqtt_ok = last_mqtt is not None and (now - last_mqtt) < _LIVENESS_TIMEOUT_S
        sig_ok  = last_sig  is not None and (now - last_sig)  < _LIVENESS_TIMEOUT_S
        live_transport = mqtt_ok or sig_ok

        with _rest_lock:
            prev_mqtt = _transport_state["mqtt_alive"]
            prev_sig  = _transport_state["signalr_alive"]
            _transport_state["mqtt_alive"]    = mqtt_ok
            _transport_state["signalr_alive"] = sig_ok
            _update_active_source()   # Fix #4: re-compute active_source every tick

        # Log transitions
        if prev_mqtt and not mqtt_ok:
            logger.warning("[TRANSPORT] MQTT LOST (no message >%.0fs) → starting %ds grace",
                           _LIVENESS_TIMEOUT_S, _REST_GRACE_S)
        if prev_sig and not sig_ok and sig_ok is not None:
            logger.warning("[TRANSPORT] SignalR LOST → starting %ds grace", _REST_GRACE_S)

        # ── 2. If a live transport exists: ensure REST is OFF ─────────────────
        if live_transport:
            with _rest_lock:
                if _transport_state["fallback_active"]:
                    _transport_state["fallback_active"] = False
                    _transport_state["grace_start"]     = None
                    _transport_state["grace_cancelled"] = False
                    _transport_state["rest_backoff_s"]  = _REST_BACKOFF_STEPS[0]
                    _transport_state["rest_consecutive_ok"] = 0
                    logger.info("[TRANSPORT] Live transport restored → REST fallback DEACTIVATED")
                else:
                    # Still healthy: clear any stale grace timer
                    _transport_state["grace_start"]     = None
                    _transport_state["grace_cancelled"] = False
            continue

        # ── 3. No live transport — manage grace period ────────────────────────
        with _rest_lock:
            grace_start    = _transport_state["grace_start"]
            grace_cancelled = _transport_state["grace_cancelled"]
            fallback_active = _transport_state["fallback_active"]

            if grace_cancelled:
                # Transport recovered during grace — reset
                _transport_state["grace_start"]      = None
                _transport_state["grace_cancelled"]  = False
                _transport_state["fallback_active"]  = False
                logger.info("[TRANSPORT] Grace cancelled — transport recovered, REST stays off")
                continue

            if grace_start is None:
                # Start grace timer
                _transport_state["grace_start"] = now
                logger.warning("[TRANSPORT] All transports dead → REST grace period started (%ds)",
                               _REST_GRACE_S)
                continue

            grace_elapsed = now - grace_start
            if grace_elapsed < _REST_GRACE_S:
                # Still inside grace — serve cached values, log every 5s
                if int(grace_elapsed) % 5 == 0:
                    logger.info("[TRANSPORT] Grace %.0f/%ds — serving cached values",
                                grace_elapsed, _REST_GRACE_S)
                continue

            # Grace expired: activate REST fallback
            if not fallback_active:
                _transport_state["fallback_active"] = True
                logger.warning("[TRANSPORT] Grace expired → REST fallback ACTIVATED")

        # ── 4. REST polling (fallback_active=True) ────────────────────────────
        with _rest_lock:
            if _transport_state["rest_inflight"]:
                logger.debug("[REST_FALLBACK] Previous request still in-flight — skipping tick")
                continue
            backoff_s = _transport_state["rest_backoff_s"]

        # Respect backoff: if backoff > poll interval, sleep the remainder
        # (the greenlet already slept _REST_POLL_INTERVAL_S at top of loop)
        if backoff_s > _REST_POLL_INTERVAL_S:
            extra = backoff_s - _REST_POLL_INTERVAL_S
            jitter = random.uniform(0, _REST_BACKOFF_JITTER)
            logger.info("[REST_FALLBACK] Backoff %.1fs+jitter%.1fs before next poll",
                        extra, jitter)
            _gevent.sleep(extra + jitter)

        with _rest_lock:
            _transport_state["rest_inflight"] = True
            _transport_state["rest_poll_count"] += 1

        try:
            # S1-7: Poll both OPC and PLC endpoints
            opc_resp = _requests.get(opc_values_url, timeout=_REST_TIMEOUT_S)
            opc_resp.raise_for_status()
            opc_body = opc_resp.json()
            opc_tags = opc_body if isinstance(opc_body, list) else opc_body.get("tags", [])
            
            # Poll PLC values (new in S1-7)
            plc_tags = []
            try:
                plc_resp = _requests.get(plc_values_url, timeout=_REST_TIMEOUT_S)
                plc_resp.raise_for_status()
                plc_body = plc_resp.json()
                # PLC endpoint returns {"success": true, "values": [...]}
                plc_tags = plc_body.get("values", []) if isinstance(plc_body, dict) else plc_body
            except Exception as plc_err:
                # Don't fail entire poll if PLC unavailable
                logger.debug("[REST_FALLBACK] PLC poll failed (non-fatal): %s", str(plc_err)[:80])
            
            # Combine OPC + PLC tags
            tags_raw = opc_tags + plc_tags

            if not tags_raw:
                raise ValueError("REST response contained 0 tags (OPC + PLC)")

            # Fix #4: only write to cache when REST is the active source.
            # If MQTT or SignalR recovered and became stable during this in-flight
            # request, discard the REST payload to avoid overwriting fresher data.
            with _rest_lock:
                can_write = _transport_state["active_source"] == "REST"

            updated = 0
            if can_write:
                for t in tags_raw:
                    # S1-7: Handle both OPC (tagId) and PLC (tagName/address) formats
                    tag_id = (t.get("tagId") or t.get("tag_id") or t.get("id") or 
                              t.get("tagName") or t.get("address"))
                    if not tag_id:
                        continue
                    
                    # S1-7: Use computedQuality if available (from S1-3/S1-4)
                    quality = t.get("computedQuality") or t.get("quality", "G")
                    age_ms = t.get("age_ms", 0)
                    
                    latest_tag_values[tag_id] = _apply_stale_policy({
                        "tag_id":     tag_id,
                        "value_num":  t.get("value"),
                        "value_text": str(t.get("value", "")),
                        "value_bool": None,
                        "quality":    quality,
                        "timestamp":  t.get("timestamp") or t.get("lastUpdate") or t.get("cachedAt") or now_ist_iso(),
                        "source":     "REST_FALLBACK",
                        "age_ms":     age_ms or _compute_age_ms(t.get("timestamp") or t.get("lastUpdate")),
                    })
                    updated += 1
            else:
                logger.debug("[REST_FALLBACK] Discarding REST payload — active_source is no longer REST")

            # Emit snapshot to all connected clients
            if updated > 0 and connected_clients:
                socketio.emit('tag_update', list(latest_tag_values.values()), namespace='/')

            with _rest_lock:
                _transport_state["rest_consecutive_ok"] += 1
                _transport_state["last_rest_ok_at"] = time.monotonic()
                _transport_state["rest_last_error"]  = None
                ok_count = _transport_state["rest_consecutive_ok"]
                if ok_count >= _REST_STABLE_SUCCESSES:
                    if _transport_state["rest_backoff_s"] != _REST_BACKOFF_STEPS[0]:
                        logger.info("[REST_FALLBACK] %d consecutive successes → backoff reset",
                                    ok_count)
                    _transport_state["rest_backoff_s"]      = _REST_BACKOFF_STEPS[0]
                    _transport_state["rest_consecutive_ok"] = 0

            logger.debug("[REST_FALLBACK] Polled OK — %d tags updated (OPC + PLC)", updated)

        except Exception as exc:
            err_str = str(exc)[:120]
            with _rest_lock:
                _transport_state["rest_consecutive_ok"] = 0
                _transport_state["rest_error_count"]   += 1
                _transport_state["rest_last_error"]     = err_str
                # Advance backoff
                current_b = _transport_state["rest_backoff_s"]
                idx = min(
                    len(_REST_BACKOFF_STEPS) - 1,
                    _REST_BACKOFF_STEPS.index(current_b) + 1
                    if current_b in _REST_BACKOFF_STEPS
                    else len(_REST_BACKOFF_STEPS) - 1
                )
                _transport_state["rest_backoff_s"] = _REST_BACKOFF_STEPS[idx]
                next_b = _transport_state["rest_backoff_s"]

            logger.warning("[REST_FALLBACK] Poll error: %s → backoff %.1fs", err_str, next_b)

        finally:
            with _rest_lock:
                _transport_state["rest_inflight"] = False


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

    # Fix #3: Start REST fallback poller greenlet
    try:
        import gevent as _gevent
        _gevent.spawn(_rest_fallback_poller)
        logger.info("[REST_FALLBACK] Poller greenlet spawned (grace=%ds)", _REST_GRACE_S)
    except Exception as e:
        logger.warning("[WARN] REST fallback poller failed to start: %s", e)

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

    # Seed the in-memory tag cache from DB so cards populate immediately after restart
    with app.app_context():
        _seed_tag_cache_from_db()
    
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

    # Step 4 — Start dispatcher metrics persistence greenlet
    # Requires migration: HMI/migrations/dispatcher_metrics_table.sql (run once manually)
    try:
        _gevent.spawn(_dispatcher_metrics_persister)
        logger.info("[DISP_METRICS] Persistence greenlet spawned (poll=%ds snap=%ds)",
                    int(_DISP_POLL_S), int(_DISP_SNAP_S))
    except Exception as _e:
        logger.warning("[DISP_METRICS] Failed to spawn greenlet: %s", _e)

    # Start Flask-SocketIO server
    socketio.run(
        app,
        host=container.config['hmi_server']['host'],
        port=container.config['hmi_server']['port'],
        debug=container.config['hmi_server']['debug'],
        use_reloader=False  # Disable reloader to prevent duplicate MQTT connections
    )
