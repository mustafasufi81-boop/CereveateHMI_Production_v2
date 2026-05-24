#!/usr/bin/env python3
"""
PLC Scanner - Web Interface
Real-time PLC data acquisition with web dashboard
"""

import sys
import os
import json
import threading
import time
from datetime import datetime, timezone, timedelta
from collections import deque, defaultdict
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from pycomm3 import LogixDriver

# ============================================================================
# CONFIGURATION
# ============================================================================

# PLC Configuration
PLC_IP = "192.168.0.20"
PLC_PATH = f"{PLC_IP}/1,0"  # Correct format for pycomm3
SCAN_INTERVAL_MS = 1000  # Default scan interval

# Database Configuration
DB_CONFIG = {
    'host': '192.168.0.120',
    'port': 5432,
    'database': 'Cereveate',
    'user': 'cereveate',
    'password': 'cereveate@222',
    'sslmode': 'disable',
    'connect_timeout': 5
}

# Cache Configuration
MAX_CACHE_SIZE = 10000  # Max values per tag
MAX_TOTAL_VALUES = 50000  # Emergency cleanup threshold
FORCED_WRITE_INTERVAL = 120.0  # Force write every 2 minutes
DB_WRITE_INTERVAL = 1.0  # Check for DB writes every 1 second

# Web Server Configuration
WEB_PORT = 7001

# ============================================================================
# TAG CACHE CLASS
# ============================================================================

class TagCache:
    """Thread-safe cache for tag values with emergency cleanup"""
    
    def __init__(self, max_size=MAX_CACHE_SIZE):
        self.cache = defaultdict(deque)
        self.max_size = max_size
        self.max_total_values = MAX_TOTAL_VALUES
        self.lock = threading.RLock()
        self.stats = {
            'reads': 0,
            'writes': 0,
            'cleanups': 0,
            'emergency_cleanups': 0
        }
    
    def put(self, tag_id, timestamp, value, quality='Good'):
        """Add value to cache"""
        with self.lock:
            self.cache[tag_id].append((timestamp, value, quality))
            self.stats['writes'] += 1
            
            # Auto-cleanup if tag exceeds limit
            if len(self.cache[tag_id]) > self.max_size:
                keep_count = self.max_size // 2
                self.cache[tag_id] = deque(list(self.cache[tag_id])[-keep_count:], maxlen=self.max_size)
                self.stats['cleanups'] += 1
    
    def get_batch(self, since_timestamp=None):
        """Get all cached values since timestamp"""
        with self.lock:
            self.stats['reads'] += 1
            result = []
            
            for tag_id, values in self.cache.items():
                for ts, val, quality in values:
                    if since_timestamp is None or ts > since_timestamp:
                        result.append({
                            'tag_id': tag_id,
                            'timestamp': ts,
                            'value': val,
                            'quality': quality
                        })
            
            return result
    
    def clear_old(self, before_timestamp):
        """Remove values older than timestamp, but keep at least the latest value per tag"""
        with self.lock:
            for tag_id in list(self.cache.keys()):
                original_len = len(self.cache[tag_id])
                newer_values = [item for item in self.cache[tag_id] if item[0] > before_timestamp]
                
                # CRITICAL FIX: Always keep at least the most recent value
                # This prevents tags with unchanging values from disappearing
                if len(newer_values) == 0 and len(self.cache[tag_id]) > 0:
                    # Keep only the latest value
                    newer_values = [self.cache[tag_id][-1]]
                
                self.cache[tag_id] = deque(newer_values, maxlen=self.max_size)
                
                # Only delete if truly empty (shouldn't happen now)
                if len(self.cache[tag_id]) == 0:
                    del self.cache[tag_id]
    
    def check_emergency_cleanup(self):
        """Check if emergency cleanup needed"""
        with self.lock:
            total_values = sum(len(v) for v in self.cache.values())
            return (total_values > self.max_total_values, total_values)
    
    def emergency_cleanup(self):
        """Remove 75% of old data, keep 25% newest"""
        with self.lock:
            total_before = sum(len(v) for v in self.cache.values())
            
            for tag_id in list(self.cache.keys()):
                values = list(self.cache[tag_id])
                keep_count = max(1, len(values) // 4)  # Keep 25%
                self.cache[tag_id] = deque(values[-keep_count:], maxlen=self.max_size)
            
            total_after = sum(len(v) for v in self.cache.values())
            self.stats['emergency_cleanups'] += 1
            
            return (total_before, total_after)
    
    def get_stats(self):
        """Get cache statistics"""
        with self.lock:
            return {
                'tags': len(self.cache),
                'total_values': sum(len(v) for v in self.cache.values()),
                'reads': self.stats['reads'],
                'writes': self.stats['writes'],
                'cleanups': self.stats['cleanups'],
                'emergency_cleanups': self.stats['emergency_cleanups']
            }
    
    def get_latest_values(self):
        """Get latest value for each tag"""
        with self.lock:
            result = {}
            for tag_id, values in self.cache.items():
                if values:
                    ts, val, quality = values[-1]
                    result[tag_id] = {
                        'value': val,
                        'quality': quality,
                        'timestamp': ts.isoformat() if hasattr(ts, 'isoformat') else str(ts)
                    }
            return result

# ============================================================================
# GLOBAL STATE
# ============================================================================

app = Flask(__name__)
app.config['SECRET_KEY'] = 'plc-scanner-secret-key'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', logger=False, engineio_logger=False)

# Shared state
tag_cache = TagCache()
plc_connected = False
db_connected = False
scan_interval_ms = SCAN_INTERVAL_MS
tag_list = []
last_scanned_values = {}  # Current PLC values - ALWAYS updated (for UI)
last_written_values_plc = {}  # For change detection in PLC scan loop
trend_data = defaultdict(lambda: deque(maxlen=100))  # Store last 100 points per tag
logged_errors = set()  # Track which tag errors have been logged (prevent spam)
statistics = {
    'plc_reads': 0,
    'plc_errors': 0,
    'db_writes': 0,
    'db_errors': 0,
    'values_cached': 0,
    'values_filtered': 0,
    'forced_writes': 0,
    'last_scan_time': None,
    'last_db_write': None
}

# ============================================================================
# DATABASE FUNCTIONS
# ============================================================================

def get_db_connection():
    """Get database connection"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"❌ DB Connection Error: {e}")
        return None

def write_to_database(batch):
    """Write batch to database - EXACT copy from plc_scanner_enhanced.py"""
    global db_connected, statistics
    
    if not batch:
        return True
    
    try:
        conn = get_db_connection()
        if not conn:
            db_connected = False
            statistics['db_errors'] += 1
            return False
        
        # Prepare rows for database - EXACT logic from enhanced version
        latest_dict = {}  # De-duplicate: keep only latest value per tag
        ts_rows = []
        
        for record in batch:
            tag_id = record['tag_id']
            ts = record['timestamp']
            value = record['value']
            quality = record['quality']
            
            # Determine value type - EXACT logic
            num = text = boolean = None
            
            if isinstance(value, bool):
                boolean = value
                num = 1.0 if value else 0.0
            elif isinstance(value, (int, float)):
                num = float(value)
            elif isinstance(value, str):
                text = value
            else:
                continue
            
            # For latest_value: keep only most recent per tag
            if tag_id not in latest_dict or ts > latest_dict[tag_id][1]:
                latest_dict[tag_id] = (tag_id, ts, num, text, boolean, quality)
            
            # For timeseries
            ts_rows.append((ts, tag_id, num, text, boolean, quality, 'P'))
        
        # Convert dict to list
        latest_rows = list(latest_dict.values())
        
        # Write to latest_value table - EXACT query from enhanced
        if latest_rows:
            cur = conn.cursor()
            query = """
                INSERT INTO historian_raw.historian_latest_value
                (tag_id, last_time, last_value_num, last_value_text, last_value_bool, last_quality, updated_at)
                VALUES %s
                ON CONFLICT (tag_id)
                DO UPDATE SET
                    last_time = EXCLUDED.last_time,
                    last_value_num = EXCLUDED.last_value_num,
                    last_value_text = EXCLUDED.last_value_text,
                    last_value_bool = EXCLUDED.last_value_bool,
                    last_quality = EXCLUDED.last_quality,
                    updated_at = EXCLUDED.updated_at
            """
            rows_with_updated = [(r[0], r[1], r[2], r[3], r[4], r[5], datetime.now(timezone.utc)) for r in latest_rows]
            execute_values(cur, query, rows_with_updated)
            cur.close()
        
        # Write to timeseries table - EXACT query from enhanced
        if ts_rows:
            cur = conn.cursor()
            query = """
                INSERT INTO historian_raw.historian_timeseries
                (time, tag_id, value_num, value_text, value_bool, quality, sample_source, mapping_version)
                VALUES %s
            """
            rows_with_mapping = [
                (ts, tag_id, num, text, boolean, quality, source, 1)
                for (ts, tag_id, num, text, boolean, quality, source) in ts_rows
            ]
            execute_values(cur, query, rows_with_mapping)
            cur.close()
        
        conn.commit()
        conn.close()
        
        db_connected = True
        statistics['db_writes'] += len(batch)
        statistics['last_db_write'] = datetime.now().isoformat()
        
        return True
        
    except Exception as e:
        db_connected = False
        statistics['db_errors'] += 1
        print(f"❌ DB Write Error: {e}")
        import traceback
        traceback.print_exc()
        if conn:
            try:
                conn.rollback()
                conn.close()
            except:
                pass
        return False

# ============================================================================
# PLC SCANNER THREAD
# ============================================================================

def plc_scanner_loop():
    """Main PLC scanning loop"""
    global plc_connected, tag_list, last_scanned_values, statistics, scan_interval_ms
    
    print(f"🔄 Starting PLC scanner thread...")
    
    while True:
        try:
            with LogixDriver(PLC_PATH) as plc:
                print(f"✅ Connected to PLC at {PLC_IP}")
                plc_connected = True
                
                # Get tag list from database OR PLC
                tag_list = get_tag_list_from_db()
                if not tag_list:
                    print("⚠️  No tags in database, reading from PLC directly...")
                    # Get tags from PLC
                    tags = plc.get_tag_list()
                    tag_list = []
                    for tag in tags:
                        name = getattr(tag, "tag_name", None) or tag.get("tag_name")
                        if not name:
                            continue
                        if getattr(tag, "array_dims", None) or getattr(tag, "structured", None):
                            continue
                        tag_list.append(name)
                    print(f"📊 Found {len(tag_list)} tags from PLC")
                    if not tag_list:
                        time.sleep(5)
                        continue
                
                print(f"📊 Scanning {len(tag_list)} tags at {scan_interval_ms}ms interval")
                
                while True:
                    scan_start = time.time()
                    
                    # Read all tags
                    results = plc.read(*tag_list)
                    if not isinstance(results, list):
                        results = [results]
                    
                    ts_utc = datetime.now(timezone.utc)
                    changed_count = 0
                    
                    # Process each result
                    for tag, res in zip(tag_list, results):
                        if res.error:
                            statistics['plc_errors'] += 1
                            # Only log each tag error once to prevent spam
                            if tag not in logged_errors:
                                print(f"⚠️  PLC Read Error - Tag: {tag}, Error: {res.error}")
                                logged_errors.add(tag)
                            continue
                        
                        statistics['plc_reads'] += 1
                        
                        # =====================================================
                        # SMART DATA VALIDATION & TYPE DETECTION
                        # =====================================================
                        raw_value = res.value
                        processed_value = None
                        is_valid = False
                        
                        # Step 1: Handle boolean
                        if isinstance(raw_value, bool):
                            processed_value = 1 if raw_value else 0
                            is_valid = True
                        
                        # Step 2: Handle numeric types directly
                        elif isinstance(raw_value, (int, float)):
                            # Validate numeric range (reject NaN, Inf, extreme values)
                            if not (raw_value != raw_value or  # NaN check
                                    abs(raw_value) == float('inf') or  # Infinity check
                                    abs(raw_value) > 1e15):  # Extreme value check
                                processed_value = float(raw_value)
                                is_valid = True
                        
                        # Step 3: Try to convert string to number
                        elif isinstance(raw_value, str):
                            # Clean whitespace
                            cleaned = raw_value.strip()
                            
                            # Reject garbage strings (empty or too long)
                            if not cleaned or len(cleaned) > 255:
                                continue
                            
                            # Check for garbage characters (control chars)
                            if any(ord(c) < 32 and c not in '\t\n\r' for c in cleaned):
                                continue
                            
                            # Try numeric conversion first
                            try:
                                # Try integer first
                                if '.' not in cleaned and 'e' not in cleaned.lower():
                                    processed_value = float(int(cleaned))
                                    is_valid = True
                                else:
                                    # Try float
                                    processed_value = float(cleaned)
                                    if not (processed_value != processed_value or abs(processed_value) == float('inf')):
                                        is_valid = True
                            except (ValueError, TypeError):
                                # Not a number - keep as text if valid
                                if cleaned.isprintable() and len(cleaned) <= 100:
                                    processed_value = cleaned
                                    is_valid = True
                        
                        # Step 4: Handle None or other types
                        elif raw_value is None:
                            # Keep None as None for string-type tags (Pipe_Id, WPS_ID, etc.)
                            # These will be filtered out and not cached
                            # Only log for welding parameter tags to help debug
                            if tag in ['Pipe_Id', 'WPS_ID', 'Joint_Id', 'Arc', 'Power']:
                                if tag not in logged_errors:
                                    print(f"ℹ️  Tag '{tag}' has null value - may not be initialized in PLC")
                                    logged_errors.add(tag)
                            continue
                        else:
                            # Try to convert unknown types
                            try:
                                processed_value = float(raw_value)
                                is_valid = True
                            except:
                                continue
                        
                        # Skip if validation failed
                        if not is_valid or processed_value is None:
                            continue
                        
                        # ALWAYS update last_scanned_values FIRST (for UI display)
                        # This ensures dashboard always has current values regardless of cache cleanup
                        last_scanned_values[tag] = processed_value
                        
                        # PLC-LEVEL CHANGE DETECTION (for DB optimization)
                        value_changed = True
                        if tag in last_written_values_plc:  # Use separate tracking for change detection
                            if processed_value == last_written_values_plc.get(tag):
                                value_changed = False
                                statistics['values_filtered'] += 1
                        
                        # ONLY cache when value changes (original design)
                        # DB writer handles forced writes every 2 minutes for unchanged values
                        if value_changed:
                            tag_cache.put(tag, ts_utc, processed_value, 'G')  # 'G' = Good (CHAR(1))
                            last_written_values_plc[tag] = processed_value  # Track for change detection
                            changed_count += 1
                            statistics['values_cached'] += 1
                            
                            # Add to trend data (only numeric for charts)
                            if isinstance(processed_value, (int, float)):
                                trend_data[tag].append((datetime.now().isoformat(), processed_value))
                    
                    statistics['last_scan_time'] = datetime.now().isoformat()
                    
                    # Always emit statistics to web clients
                    socketio.emit('stats_update', get_current_stats())
                    
                    # Emit ALL current tag values from last_scanned_values (not cache!)
                    # This ensures UI trends get updates even for unchanged values
                    socketio.emit('values_update', format_values_for_ui())
                    
                    # Sleep for remaining time
                    scan_time = time.time() - scan_start
                    sleep_time = max(0, (scan_interval_ms / 1000.0) - scan_time)
                    time.sleep(sleep_time)
                    
        except Exception as e:
            plc_connected = False
            print(f"❌ PLC Error: {e}")
            time.sleep(5)

# ============================================================================
# DATABASE WRITER THREAD
# ============================================================================

def db_writer_loop():
    """Database writer with smart filtering"""
    global statistics
    
    print(f"🔄 Starting DB writer thread...")
    
    last_write_time = datetime.now(timezone.utc)
    last_written_values = {}
    last_write_time_per_tag = {}
    
    while True:
        try:
            time.sleep(DB_WRITE_INTERVAL)
            
            current_time = datetime.now(timezone.utc)
            
            # Get only NEW values since last write
            batch = tag_cache.get_batch(since_timestamp=last_write_time)
            
            # ALWAYS update last_write_time to prevent re-processing
            last_write_time = current_time
            
            if not batch:
                continue
            
            # Filter batch: skip unchanged values unless forced write needed
            filtered_batch = []
            forced_write_count = 0
            
            for record in batch:
                tag_id = record['tag_id']
                value = record['value']
                
                # Check if value changed
                value_changed = True
                if tag_id in last_written_values:
                    if value == last_written_values[tag_id]:
                        value_changed = False
                
                # Check if forced write needed for THIS tag
                force_write = False
                if tag_id in last_write_time_per_tag:
                    time_since_last_write = (current_time - last_write_time_per_tag[tag_id]).total_seconds()
                    if time_since_last_write >= FORCED_WRITE_INTERVAL:
                        force_write = True
                        forced_write_count += 1
                        statistics['forced_writes'] += 1
                
                # Write if value changed OR forced write
                if value_changed or force_write:
                    filtered_batch.append(record)
                    last_written_values[tag_id] = value
                    last_write_time_per_tag[tag_id] = current_time
            
            if filtered_batch:
                db_success = write_to_database(filtered_batch)
                
                if db_success:
                    # Normal cleanup: keep last 10 SECONDS (cache only for DB, UI uses last_scanned_values)
                    cleanup_time = current_time - timedelta(seconds=10)
                    tag_cache.clear_old(cleanup_time)
                else:
                    # Emergency cleanup check
                    needs_cleanup, total_values = tag_cache.check_emergency_cleanup()
                    if needs_cleanup:
                        before, after = tag_cache.emergency_cleanup()
                        print(f"🚨 EMERGENCY CLEANUP: {before} → {after} values")
                
                # Emit stats update
                socketio.emit('stats_update', get_current_stats())
                
        except Exception as e:
            print(f"❌ DB Writer Error: {e}")
            time.sleep(1)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_tag_list_from_db():
    """Get enabled PLC tags from database - ONLY tags that exist in PLC"""
    try:
        conn = get_db_connection()
        if not conn:
            return []
        
        with conn.cursor() as cur:
            # ONLY get real PLC tags (not OPC simulation tags)
            # Exclude tags that contain these OPC simulation keywords
            cur.execute("""
                SELECT tag_id 
                FROM historian_meta.tag_master 
                WHERE enabled = true 
                AND tag_id NOT ILIKE '%Random%'
                AND tag_id NOT ILIKE '%Triangle%'
                AND tag_id NOT ILIKE '%Waves%'
                AND tag_id NOT ILIKE '%Brigade%'
                AND tag_id NOT LIKE '@%'
                ORDER BY tag_id
            """)
            tags = [row[0] for row in cur.fetchall()]
        
        conn.close()
        print(f"📋 Loaded {len(tags)} PLC tags (excluding OPC simulation tags)")
        return tags
        
    except Exception as e:
        print(f"❌ Error loading tags: {e}")
        return []

def format_values_for_ui():
    """Format last_scanned_values for dashboard UI.
    Dashboard JS expects {tag_id: {value, quality, timestamp}} objects.
    last_scanned_values only stores raw values, so we wrap them here.
    Reads from last_scanned_values (stable runtime dict), NOT from cache.
    """
    ts = datetime.now(timezone.utc).isoformat()
    result = {}
    for tag_id, value in last_scanned_values.items():
        result[tag_id] = {
            'value': value,
            'quality': 'G',
            'timestamp': ts
        }
    return result

def get_current_stats():
    """Get current statistics"""
    cache_stats = tag_cache.get_stats()
    total_reads = statistics['plc_reads'] or 1
    cache_efficiency = (statistics['values_filtered'] / total_reads * 100) if total_reads > 0 else 0
    
    return {
        'plc_connected': plc_connected,
        'db_connected': db_connected,
        'scan_interval_ms': scan_interval_ms,
        'tag_count': len(tag_list),
        'plc_reads': statistics['plc_reads'],
        'plc_errors': statistics['plc_errors'],
        'db_writes': statistics['db_writes'],
        'db_errors': statistics['db_errors'],
        'values_cached': statistics['values_cached'],
        'values_filtered': statistics['values_filtered'],
        'forced_writes': statistics['forced_writes'],
        'cache_tags': cache_stats['tags'],
        'cache_values': cache_stats['total_values'],
        'cache_cleanups': cache_stats['cleanups'],
        'cache_emergency': cache_stats['emergency_cleanups'],
        'cache_efficiency': round(cache_efficiency, 1),
        'last_scan_time': statistics['last_scan_time'],
        'last_db_write': statistics['last_db_write']
    }

# ============================================================================
# FLASK ROUTES
# ============================================================================

@app.route('/')
def index():
    """Main dashboard - enhanced SCADA view"""
    return render_template('dashboard.html')

@app.route('/enhanced')
def index_enhanced():
    """Enhanced dashboard view"""
    return render_template('index_enhanced.html')

@app.route('/simple')
def index_simple():
    """Simple dashboard view"""
    return render_template('index.html')

@app.route('/api/stats')
def get_stats():
    """Get current statistics"""
    return jsonify(get_current_stats())

@app.route('/api/values')
def get_values():
    """Get latest tag values - ONLY from last_scanned_values (runtime, independent of cache/DB)"""
    # UI displays ONLY what's in last_scanned_values (current PLC runtime state)
    # This has NOTHING to do with cache or database writes
    result = {}
    for tag_id, value in last_scanned_values.items():
        result[tag_id] = {
            'value': value,
            'quality': 'G',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    return jsonify(result)

@app.route('/api/tags')
def get_tags():
    """Get list of all tags"""
    return jsonify({'tags': tag_list})

@app.route('/api/trend/<tag_id>')
def get_trend(tag_id):
    """Get trend data for specific tag"""
    if tag_id in trend_data:
        return jsonify({'tag_id': tag_id, 'data': list(trend_data[tag_id])})
    return jsonify({'tag_id': tag_id, 'data': []})

@app.route('/api/set_interval', methods=['POST'])
def set_scan_interval():
    """Set scan interval in milliseconds"""
    global scan_interval_ms
    data = request.get_json()
    new_interval = data.get('interval_ms', 1000)
    if 100 <= new_interval <= 10000:
        scan_interval_ms = new_interval
        return jsonify({'success': True, 'interval_ms': scan_interval_ms})
    return jsonify({'success': False, 'error': 'Interval must be between 100-10000ms'}), 400

@app.route('/api/trends')
def get_trends():
    """Get trend data for all tags"""
    trends = {}
    for tag_id, points in trend_data.items():
        trends[tag_id] = list(points)
    return jsonify(trends)

# ============================================================================
# SOCKETIO EVENTS
# ============================================================================

@socketio.on('connect')
def handle_connect():
    """Client connected"""
    print(f"🔌 Client connected")
    emit('stats_update', get_current_stats())
    emit('values_update', format_values_for_ui())

@socketio.on('disconnect')
def handle_disconnect():
    """Client disconnected"""
    print(f"🔌 Client disconnected")

@socketio.on('request_stats')
def handle_request_stats():
    """Client requested stats"""
    emit('stats_update', get_current_stats())

@socketio.on('request_values')
def handle_request_values():
    """Client requested values - use last_scanned_values (stable), NOT cache (gets cleared after DB writes)"""
    emit('values_update', format_values_for_ui())

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    print("=" * 80)
    print("🏭 PLC SCANNER - WEB INTERFACE")
    print("=" * 80)
    print(f"PLC: {PLC_PATH}")
    print(f"Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}")
    print(f"Web Server: http://localhost:{WEB_PORT}")
    print(f"Scan Interval: {scan_interval_ms}ms")
    print("=" * 80)
    
    # Start background threads
    plc_thread = threading.Thread(target=plc_scanner_loop, daemon=True)
    plc_thread.start()
    
    db_thread = threading.Thread(target=db_writer_loop, daemon=True)
    db_thread.start()
    
    # Start web server
    socketio.run(app, host='0.0.0.0', port=WEB_PORT, debug=False, allow_unsafe_werkzeug=True)
