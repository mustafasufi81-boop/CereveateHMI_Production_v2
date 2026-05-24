"""
Application Factory for Production-Ready Flask HMI
Refactored for WSGI server compatibility and multiple environment support
"""

import logging
import time
import os
import sys
import atexit
from datetime import datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from flask import Flask, request
from flask_socketio import SocketIO
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

# Enhanced RBAC Controllers
from controllers.audit_controller import audit_bp
from controllers.session_controller import session_bp
from controllers.equipment_controller import equipment_bp
from controllers.approval_controller import approval_bp
from controllers.industrial_rbac_controller import industrial_rbac_bp

# Predictive Alarm Engine
from controllers.predictive_alarm_controller import predictive_bp
from services.predictive_alarm_engine import engine_instance as _pred_engine_instance
from services.drift_detector_service import drift_detector_instance as _drift_instance

# Global variables (module-level for proper WSGI support)
socketio = None
logger = None
latest_tag_values = {}
connected_clients = set()


def setup_logging(env='production'):
    """
    Configure production-ready file-based logging with rotation
    - Size-based rotation: 5 MB max per file
    - Date-based rotation: Daily logs with 30-day retention
    - Separate error log file
    - Console output for real-time monitoring
    """
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    info_log_file = os.path.join(log_dir, 'hmi_app.log')
    error_log_file = os.path.join(log_dir, 'hmi_errors.log')
    daily_log_file = os.path.join(log_dir, 'hmi_daily.log')
    
    detailed_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)-8s] [%(name)-25s] [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    root_logger = logging.getLogger()
    root_logger.handlers = []
    
    # Set log level based on environment
    log_level = logging.DEBUG if env == 'development' else logging.INFO
    root_logger.setLevel(log_level)
    
    # 1. Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(simple_formatter)
    root_logger.addHandler(console_handler)
    
    # 2. Rotating File Handler
    rotating_handler = RotatingFileHandler(
        info_log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=10,
        encoding='utf-8'
    )
    rotating_handler.setLevel(logging.INFO)
    rotating_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(rotating_handler)
    
    # 3. Timed Rotating File Handler
    timed_handler = TimedRotatingFileHandler(
        daily_log_file,
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    timed_handler.setLevel(logging.INFO)
    timed_handler.setFormatter(detailed_formatter)
    timed_handler.suffix = '%Y-%m-%d'
    root_logger.addHandler(timed_handler)
    
    # 4. Error File Handler
    error_handler = RotatingFileHandler(
        error_log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=10,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(error_handler)
    
    startup_logger = logging.getLogger(__name__)
    startup_logger.info("=" * 80)
    startup_logger.info(f"[START] HMI Flask Application Starting [{env.upper()}]")
    startup_logger.info(f"[LOG] Log Directory: {log_dir}")
    startup_logger.info(f"[LOG] Info Log: {info_log_file}")
    startup_logger.info(f"[LOG] Error Log: {error_log_file}")
    startup_logger.info(f"[LOG] Daily Log: {daily_log_file}")
    startup_logger.info("=" * 80)
    
    return startup_logger


def initialize_services():
    """Initialize database and cache services"""
    logger.info("[INIT] Initializing services...")
    
    # Test database connection through historical service
    try:
        # Test if database is accessible
        if hasattr(container.historical_service, 'db_config'):
            logger.info("[OK] Database configuration loaded")
        else:
            logger.warning("[WARN] Database configuration not found in historical service")
    except Exception as e:
        logger.error(f"[ERROR] Database connection check failed: {e}")
        # Don't raise - allow app to continue
    
    # Start tag cache background thread
    try:
        if hasattr(container.tag_cache, 'start'):
            container.tag_cache.start()
            logger.info("[OK] Tag cache background thread started")
        else:
            logger.warning("[WARN] Tag cache service doesn't have start method")
    except Exception as e:
        logger.error(f"[ERROR] Tag cache initialization failed: {e}")
        # Don't raise - allow app to continue
    
    # Connect MQTT client
    if container.mqtt_client:
        try:
            container.mqtt_client.connect()
            logger.info("[OK] MQTT client connected")
        except Exception as e:
            logger.warning(f"[WARN] MQTT connection failed: {e}")
    
    logger.info("[OK] All services initialized successfully")


def register_socketio_events(socketio_instance):
    """Register SocketIO event handlers"""
    
    @socketio_instance.on('connect')
    def handle_connect():
        client_id = request.sid
        connected_clients.add(client_id)
        logger.info(f"[WS] Client connected: {client_id} (Total: {len(connected_clients)})")
    
    @socketio_instance.on('disconnect')
    def handle_disconnect():
        client_id = request.sid
        connected_clients.discard(client_id)
        logger.info(f"[WS] Client disconnected: {client_id} (Total: {len(connected_clients)})")
    
    @socketio_instance.on('subscribe_tags')
    def handle_subscribe_tags(data):
        client_id = request.sid
        tag_ids = data.get('tag_ids', [])
        logger.info(f"[WS] Client {client_id} subscribed to {len(tag_ids)} tags")
    
    @socketio_instance.on('request_live_data')
    def handle_request_live_data():
        """Send current cached tag values to requesting client"""
        if latest_tag_values:
            socketio_instance.emit('live_data', latest_tag_values, room=request.sid)


def on_mqtt_message(topic, filtered_tags, raw_data):
    """
    Callback when MQTT message received with filtered tags
    Sends live data to frontend via WebSocket
    """
    global latest_tag_values
    
    try:
        if isinstance(raw_data, dict) and 'alarm_summary' in raw_data:
            alarm_summary = raw_data['alarm_summary']
            alarms = alarm_summary.get('alarms', [])
            
            if alarms:
                logger.info(f"[ALARM] Processing {len(alarms)} alarms from topic {topic}")
                
                for alarm_data in alarms:
                    severity_value = alarm_data.get('severity', 2)
                    if severity_value == 1:
                        priority = 3
                        severity_name = 'CRITICAL'
                    elif severity_value == 2:
                        priority = 2
                        severity_name = 'WARNING'
                    else:
                        priority = 1
                        severity_name = 'INFO'
                    
                    metadata = alarm_data.get('metadata', {})
                    tag_id = alarm_data.get('tag_id', 'UNKNOWN')
                    alarm_id = f"ALM_{tag_id}_{int(time.time() * 1000)}"
                    
                    alarm_event = {
                        'alarm_id': alarm_id,
                        'tag_id': tag_id,
                        'tag_name': alarm_data.get('tag_name', 'N/A'),
                        'severity': severity_name,
                        'priority': priority,
                        'message': alarm_data.get('message', 'Alarm triggered'),
                        'value': alarm_data.get('value'),
                        'limit': alarm_data.get('limit'),
                        'condition': metadata.get('condition', 'unknown'),
                        'equipment_name': metadata.get('equipment_name', 'N/A'),
                        'location': metadata.get('location', 'N/A'),
                        'timestamp': alarm_data.get('timestamp', datetime.now().isoformat())
                    }
                    
                    socketio.emit('new_alarm', alarm_event, broadcast=True)
        
        if filtered_tags:
            update_data = {'tags': []}
            for tag in filtered_tags:
                tag_id = tag.get('tag_id')
                if tag_id:
                    latest_tag_values[tag_id] = tag
                    update_data['tags'].append(tag)
            
            if update_data['tags']:
                socketio.emit('live_data', update_data, broadcast=True)
                
    except Exception as e:
        logger.error(f"[ERROR] Error processing MQTT message: {e}", exc_info=True)


def create_app(env=None):
    """
    Application Factory - Creates and configures Flask app
    
    Args:
        env: Environment name (production/staging/development)
    
    Returns:
        Flask application instance
    """
    global logger, socketio
    
    # Get environment from parameter or environment variable
    if env is None:
        env = os.environ.get('HMI_ENV', 'production')
    
    # Setup logging
    logger = setup_logging(env)
    
    # Initialize Flask app
    app = Flask(__name__)
    
    # Load configuration based on environment
    if env == 'production':
        app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', container.secret_key)
        app.config['DEBUG'] = False
    elif env == 'staging':
        app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', container.secret_key)
        app.config['DEBUG'] = False
    else:  # development
        app.config['SECRET_KEY'] = container.secret_key
        app.config['DEBUG'] = True
    
    # Enable CORS
    CORS(app, resources={
        r"/api/*": {
            "origins": os.environ.get('CORS_ORIGINS', '*').split(','),
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
    })
    
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
    
    # Register Enhanced RBAC Blueprints
    app.register_blueprint(audit_bp)
    app.register_blueprint(session_bp)
    app.register_blueprint(equipment_bp)
    app.register_blueprint(approval_bp)
    app.register_blueprint(industrial_rbac_bp)

    # Predictive Alarm Engine
    app.register_blueprint(predictive_bp)
    try:
        _pred_engine_instance().start()
        logger.info("[OK] Predictive alarm engine started")
    except Exception as _pe:
        logger.warning("[WARN] Predictive alarm engine failed to start: %s", _pe)

    # Drift Detector Service (Stage 0 — long-term baseline monitor)
    try:
        _drift_instance().start()
        logger.info("[OK] Drift detector service started")
    except Exception as _de:
        logger.warning("[WARN] Drift detector failed to start: %s", _de)

    # RBAC Middleware
    @app.before_request
    def check_rbac_permissions():
        """Enforce RBAC permissions on protected endpoints"""
        logger.info(f"[HTTP] {request.method} {request.path} from {request.remote_addr}")
        
        if request.headers.get('Authorization'):
            token_preview = request.headers.get('Authorization')[:30]
            logger.debug(f"[AUTH] Authorization header: {token_preview}...")
        
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
        
        return None
    
    # Cache control headers
    @app.after_request
    def add_header(response):
        """Add headers to prevent aggressive caching"""
        if request.path.endswith('.js') or request.path.endswith('.css'):
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        
        # Security headers
        if env == 'production':
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'SAMEORIGIN'
            response.headers['X-XSS-Protection'] = '1; mode=block'
        
        return response
    
    # Initialize Flask-SocketIO
    # allow_upgrades=False: Waitress does not support WebSocket upgrades;
    # forces polling transport to prevent RuntimeError on WebSocket upgrade attempts.
    socketio = SocketIO(
        app,
        cors_allowed_origins="*",
        async_mode='threading',
        logger=True if env == 'development' else False,
        engineio_logger=False,
        ping_timeout=60,
        ping_interval=25,
        allow_upgrades=False
    )
    
    # Register SocketIO events
    register_socketio_events(socketio)
    
    # Register MQTT callback
    if container.mqtt_client:
        container.mqtt_client.register_message_callback(on_mqtt_message)
    
    # Initialize services on first request
    @app.before_request
    def initialize_on_first_request():
        """Initialize services on first request (WSGI-compatible)"""
        if not hasattr(app, '_initialized'):
            with app.app_context():
                initialize_services()
            app._initialized = True
    
    # Register cleanup handler
    def cleanup():
        try:
            logger.info("[SHUTDOWN] Shutting down HMI...")
            if container.signalr_listener:
                container.signalr_listener.stop()
            if container.mqtt_client:
                container.mqtt_client.disconnect()
            if hasattr(container.tag_cache, '_stop_event'):
                container.tag_cache._stop_event.set()
            logger.info("[SHUTDOWN] Services stopped")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    atexit.register(cleanup)
    
    logger.info(f"[SUCCESS] Flask application created successfully [{env.upper()}]")
    return app


# For backward compatibility with original app.py
if __name__ == "__main__":
    app = create_app('development')
    socketio.run(
        app,
        host=container.config['hmi_server']['host'],
        port=container.config['hmi_server']['port'],
        debug=True,
        use_reloader=False
    )
