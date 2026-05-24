#!/usr/bin/env python3
"""
Enhanced PLC Tag Scanner - With Trends, DB Logging & Tag Selection
Based on proven working code from testing_app_FIXED.py
Author: Cereveate Tech | Shahnawaz Mustafa
"""

import os
import sys
import time
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import deque, defaultdict
from threading import RLock
from queue import Queue

# ================= DISPLAY ENVIRONMENT SETUP =================
if 'DISPLAY' not in os.environ:
    os.environ['DISPLAY'] = ':0'
    print("[SETUP] DISPLAY not set, attempting to use :0")

if 'THONNY_USER_DIR' in os.environ:
    print("[WARNING] Thonny detected - run directly: python3 plc_scanner_enhanced.py")
    
try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext, messagebox
    # Don't create test window - causes theme issues on Linux
    print("[OK] Display available - GUI mode enabled")
    HEADLESS_MODE = False
except Exception as e:
    print(f"[WARNING] Display test failed: {e}")
    print("[INFO] Running in HEADLESS mode (console logging only)")
    HEADLESS_MODE = True
    import tkinter as tk
    from tkinter import ttk, scrolledtext, messagebox
# ============================================================

from pycomm3 import LogixDriver
import psycopg2
from psycopg2.extras import execute_values

# ================= CONFIG =================
PLC_IP = "192.168.0.20"
PLC_PATH = f"{PLC_IP}/1,0"

# Database Config (from your working code)
DB_CONFIG = {
    'host': '192.168.0.120',
    'port': 5432,
    'database': 'Cereveate',
    'user': 'cereveate',
    'password': 'cereveate@222',
    'sslmode': 'disable'
}

# Default settings
DEFAULT_SCAN_INTERVAL = 1.0  # seconds
MAX_TREND_POINTS = 100  # Maximum points to show in trend
MAX_CACHE_SIZE = 10000  # Max values per tag in cache before cleanup
# ==========================================


class TagCache:
    """Thread-safe cache for PLC tag values with auto-cleanup"""
    def __init__(self, max_size=MAX_CACHE_SIZE):
        self.cache = {}  # {tag_id: deque([(ts, value, quality), ...])}
        self.lock = RLock()  # Reentrant lock for nested operations
        self.max_size = max_size
        self.stats = {'reads': 0, 'writes': 0, 'cleanups': 0, 'emergency_cleanups': 0}
        self.max_total_values = 50000  # Emergency threshold (50K values total)
    
    def put(self, tag_id, timestamp, value, quality='G'):
        """Add value to cache (thread-safe)"""
        with self.lock:
            if tag_id not in self.cache:
                self.cache[tag_id] = deque(maxlen=self.max_size)
            self.cache[tag_id].append((timestamp, value, quality))
            self.stats['writes'] += 1
            
            # Auto-cleanup if exceeded max size per tag
            if len(self.cache[tag_id]) >= self.max_size:
                # Keep only last 50% when full
                keep_size = self.max_size // 2
                self.cache[tag_id] = deque(list(self.cache[tag_id])[-keep_size:], maxlen=self.max_size)
                self.stats['cleanups'] += 1
    
    def check_emergency_cleanup(self):
        """Check if emergency cleanup is needed (prevent memory overflow)"""
        with self.lock:
            total_values = sum(len(v) for v in self.cache.values())
            if total_values > self.max_total_values:
                return True, total_values
            return False, total_values
    
    def emergency_cleanup(self):
        """Emergency cleanup - remove 75% of oldest data to prevent crash"""
        with self.lock:
            total_before = sum(len(v) for v in self.cache.values())
            
            for tag_id in list(self.cache.keys()):
                if tag_id in self.cache and len(self.cache[tag_id]) > 0:
                    # Keep only last 25% of values per tag
                    keep_size = max(1, len(self.cache[tag_id]) // 4)
                    self.cache[tag_id] = deque(list(self.cache[tag_id])[-keep_size:], maxlen=self.max_size)
                    
                    # Remove empty caches
                    if len(self.cache[tag_id]) == 0:
                        del self.cache[tag_id]
            
            total_after = sum(len(v) for v in self.cache.values())
            self.stats['emergency_cleanups'] += 1
            
            return total_before, total_after
    
    def get_latest(self, tag_id):
        """Get latest value for tag (thread-safe)"""
        with self.lock:
            self.stats['reads'] += 1
            if tag_id in self.cache and len(self.cache[tag_id]) > 0:
                return self.cache[tag_id][-1]  # (ts, value, quality)
            return None
    
    def get_batch(self, since_timestamp=None):
        """Get all values since timestamp for DB batch write (thread-safe)"""
        with self.lock:
            batch = []
            for tag_id, values in self.cache.items():
                for ts, value, quality in values:
                    if since_timestamp is None or ts > since_timestamp:
                        batch.append((tag_id, ts, value, quality))
            return batch
    
    def clear_old(self, before_timestamp):
        """Remove values older than timestamp (thread-safe)"""
        with self.lock:
            for tag_id in list(self.cache.keys()):
                if tag_id in self.cache:
                    # Keep only values newer than timestamp
                    self.cache[tag_id] = deque(
                        [(ts, val, q) for ts, val, q in self.cache[tag_id] if ts >= before_timestamp],
                        maxlen=self.max_size
                    )
                    # Remove empty caches
                    if len(self.cache[tag_id]) == 0:
                        del self.cache[tag_id]
    
    def get_stats(self):
        """Get cache statistics (thread-safe)"""
        with self.lock:
            return {
                'tags': len(self.cache),
                'total_values': sum(len(v) for v in self.cache.values()),
                **self.stats
            }


# Global thread-safe cache
tag_cache = TagCache()


# ---------- DATABASE FUNCTIONS ----------
def connect_db():
    """Connect to PostgreSQL database"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False
        return conn
    except Exception as e:
        print("[ERROR] DB connection failed:", e)
        return None


def insert_latest_values(rows):
    """
    Insert/update latest values in historian_latest_value table
    rows = [(tag_id, ts, num, text, boolean, quality), ...]
    """
    if not rows:
        return False

    conn = connect_db()
    if not conn:
        return False

    try:
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
        rows_with_updated = [(r[0], r[1], r[2], r[3], r[4], r[5], datetime.now(timezone.utc)) for r in rows]
        execute_values(cur, query, rows_with_updated)
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"[ERROR] Latest-value insert error: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False


def insert_timeseries(rows):
    """
    Insert timeseries data into historian_timeseries table
    rows = [(ts, tag_id, num, text, boolean, quality, source), ...]
    """
    if not rows:
        return False

    conn = connect_db()
    if not conn:
        return False

    try:
        cur = conn.cursor()
        query = """
            INSERT INTO historian_raw.historian_timeseries
            (time, tag_id, value_num, value_text, value_bool, quality, sample_source, mapping_version)
            VALUES %s
        """
        # Add mapping_version = 1 (production default)
        rows_with_mapping = [
            (ts, tag_id, num, text, boolean, quality, source, 1)
            for (ts, tag_id, num, text, boolean, quality, source) in rows
        ]
        execute_values(cur, query, rows_with_mapping)
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"[ERROR] Timeseries insert error: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False


class EnhancedUI:
    def __init__(self):
        self.headless = HEADLESS_MODE
        self.stats = {
            'plc_reads': 0,
            'db_writes': 0,
            'filtered': 0,
            'errors': 0,
            'start_time': datetime.now()
        }
        self.log_queue = deque(maxlen=500)
        self.scan_interval = DEFAULT_SCAN_INTERVAL
        self.db_enabled = True
        
        # PLC Performance Metrics
        self.plc_metrics = {
            'response_time_ms': 0,
            'last_update': None
        }
        
        # Tags visibility toggle
        self.tags_visible = True
        
        # Trend data storage: {tag_name: deque([(timestamp, value), ...], maxlen=MAX_TREND_POINTS)}
        self.trend_data = defaultdict(lambda: deque(maxlen=MAX_TREND_POINTS))
        self.selected_tags_for_trend = set()
        
        if self.headless:
            print("[HEADLESS] Running without GUI - console logging only")
            self.root = None
            return
            
        try:
            self.root = tk.Tk()
            self.root.title("PLC Tag Scanner - Enhanced with Trends & DB Logging")
            self.root.geometry("1600x900")
            self.root.configure(bg="#0D1117")
            self._build_gui()
        except Exception as e:
            print(f"[ERROR] Failed to create GUI: {e}")
            print("[FALLBACK] Switching to headless mode")
            self.headless = True
            self.root = None
    
    def _build_gui(self):
        # Initialize StringVar after root window exists
        self.tag_search_var = tk.StringVar()
        self.tag_search_var.trace('w', lambda *args: self.filter_tags())
        
        # ========== TOP HEADER ==========
        header_frame = tk.Frame(self.root, bg="#161B22", height=80)
        header_frame.pack(fill=tk.X, padx=0, pady=0)
        header_frame.pack_propagate(False)

        tk.Label(
            header_frame,
            text="PLC Tag Scanner - Enhanced",
            font=("Segoe UI", 22, "bold"),
            fg="#58A6FF",
            bg="#161B22"
        ).pack(side=tk.LEFT, padx=20, pady=15)

        # Connection Status Indicators
        self.connection_frame = tk.Frame(header_frame, bg="#161B22")
        self.connection_frame.pack(side=tk.RIGHT, padx=20)

        # PLC Status
        self.plc_status_dot = tk.Canvas(self.connection_frame, width=16, height=16, bg="#161B22", highlightthickness=0)
        self.plc_status_dot.pack(side=tk.LEFT, padx=5)
        self.plc_status_circle = self.plc_status_dot.create_oval(2, 2, 14, 14, fill="#6E7681", outline="")
        self.plc_status_label = tk.Label(
            self.connection_frame,
            text="PLC: Disconnected",
            font=("Segoe UI", 10, "bold"),
            fg="#6E7681",
            bg="#161B22"
        )
        self.plc_status_label.pack(side=tk.LEFT, padx=5)

        tk.Label(self.connection_frame, text="|", fg="#30363D", bg="#161B22", font=("Arial", 14)).pack(side=tk.LEFT, padx=10)

        # DB Status
        self.db_status_dot = tk.Canvas(self.connection_frame, width=16, height=16, bg="#161B22", highlightthickness=0)
        self.db_status_dot.pack(side=tk.LEFT, padx=5)
        self.db_status_circle = self.db_status_dot.create_oval(2, 2, 14, 14, fill="#6E7681", outline="")
        self.db_status_label = tk.Label(
            self.connection_frame,
            text="DB: Disconnected",
            font=("Segoe UI", 10, "bold"),
            fg="#6E7681",
            bg="#161B22"
        )
        self.db_status_label.pack(side=tk.LEFT, padx=5)

        # ========== CONTROL BAR (Scan Interval & DB Toggle) ==========
        control_frame = tk.Frame(self.root, bg="#161B22", height=50)
        control_frame.pack(fill=tk.X, padx=10, pady=(5, 0))
        control_frame.pack_propagate(False)

        # Scan Interval Control
        tk.Label(
            control_frame,
            text="Scan Interval:",
            font=("Segoe UI", 10, "bold"),
            fg="#C9D1D9",
            bg="#161B22"
        ).pack(side=tk.LEFT, padx=(20, 5))

        self.scan_interval_var = tk.StringVar(value="1000ms")
        scan_options = ["1ms", "5ms", "10ms", "50ms", "100ms", "500ms", "1000ms", "2000ms"]
        self.scan_dropdown = ttk.Combobox(
            control_frame,
            textvariable=self.scan_interval_var,
            values=scan_options,
            state="readonly",
            width=12
        )
        self.scan_dropdown.pack(side=tk.LEFT, padx=5)
        self.scan_dropdown.bind("<<ComboboxSelected>>", self.on_scan_interval_changed)

        # DB Logging Toggle
        self.db_toggle_var = tk.BooleanVar(value=True)
        self.db_toggle = tk.Checkbutton(
            control_frame,
            text="Enable Database Logging",
            variable=self.db_toggle_var,
            command=self.on_db_toggle,
            font=("Segoe UI", 10, "bold"),
            fg="#C9D1D9",
            bg="#161B22",
            selectcolor="#0D1117",
            activebackground="#161B22",
            activeforeground="#58A6FF"
        )
        self.db_toggle.pack(side=tk.LEFT, padx=20)

        # ========== STATS BAR (SINGLE ROW - FIXED WIDTH) ==========
        stats_frame = tk.Frame(self.root, bg="#0D1117", height=70)
        stats_frame.pack(fill=tk.X, padx=10, pady=(5, 0))
        stats_frame.pack_propagate(False)

        self.stat_labels = {}
        
        # All stats in one row with fixed widths
        stat_items = [
            ("Tags", "tags", "0", 80),
            ("Selected", "selected", "0", 90),
            ("PLC Reads", "plc_reads", "0", 110),
            ("DB Writes", "db_writes", "0", 110),
            ("Skipped", "filtered", "0", 90),
            ("Errors", "errors", "0", 80),
            ("Response", "response_time", "0ms", 110),
            ("Uptime", "uptime", "00:00:00", 120)
        ]
        
        for label_text, key, default_value, width in stat_items:
            stat_box = tk.Frame(stats_frame, bg="#161B22", relief=tk.RIDGE, bd=1, width=width)
            stat_box.pack(side=tk.LEFT, fill=tk.Y, padx=3, pady=5)
            stat_box.pack_propagate(False)

            tk.Label(
                stat_box,
                text=label_text,
                font=("Segoe UI", 8),
                fg="#8B949E",
                bg="#161B22"
            ).pack(pady=(3, 0))

            # Color code: errors=red, response=orange, filtered=yellow, others=blue
            if key == "errors":
                color = "#F85149"
            elif key == "response_time":
                color = "#FF6B35"
            elif key == "filtered":
                color = "#D29922"
            else:
                color = "#58A6FF"
            
            self.stat_labels[key] = tk.Label(
                stat_box,
                text=default_value,
                font=("Segoe UI", 11, "bold"),
                fg=color,
                bg="#161B22"
            )
            self.stat_labels[key].pack(pady=(0, 3))

        # ========== MAIN CONTENT: TRENDS TOP (70%), TAGS BOTTOM (30%) ==========
        main_container = tk.Frame(self.root, bg="#0D1117")
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # ========== TOP: LARGE TREND VISUALIZATION (70% height) ==========
        trend_container = tk.Frame(main_container, bg="#0D1117")
        trend_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(5, 10))

        trend_header = tk.Frame(trend_container, bg="#0D1117", height=40)
        trend_header.pack(fill=tk.X, pady=(5, 8))
        trend_header.pack_propagate(False)

        tk.Label(
            trend_header,
            text="📈 Live Trends - SCADA View",
            font=("Segoe UI", 16, "bold"),
            fg="#58A6FF",
            bg="#0D1117",
            anchor="w"
        ).pack(side=tk.LEFT, padx=(5, 0))

        tk.Label(
            trend_header,
            text="(Click checkboxes below to select tags for trending)",
            font=("Segoe UI", 10, "italic"),
            fg="#8B949E",
            bg="#0D1117"
        ).pack(side=tk.LEFT, padx=(15, 0))

        # Trend Canvas - LARGE for professional display
        trend_frame = tk.Frame(trend_container, bg="#161B22", relief=tk.RIDGE, bd=2)
        trend_frame.pack(fill=tk.BOTH, expand=True)

        trend_scrollbar = ttk.Scrollbar(trend_frame)
        trend_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.trend_canvas = tk.Canvas(
            trend_frame,
            bg="#0D1117",
            highlightthickness=0,
            yscrollcommand=trend_scrollbar.set
        )
        self.trend_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        trend_scrollbar.config(command=self.trend_canvas.yview)

        # ========== BOTTOM: TAG TABLE (30% height) ==========
        table_container = tk.Frame(main_container, bg="#0D1117", height=300)
        table_container.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=False)
        table_container.pack_propagate(False)

        table_header = tk.Frame(table_container, bg="#0D1117")
        table_header.pack(fill=tk.X, pady=(0, 5))

        tk.Label(
            table_header,
            text="Live Tag Values",
            font=("Segoe UI", 12, "bold"),
            fg="#C9D1D9",
            bg="#0D1117",
            anchor="w"
        ).pack(side=tk.LEFT)
        
        # Hide/Show Tags Button
        self.toggle_tags_btn = tk.Button(
            table_header,
            text="Hide Tags ▼",
            command=self.toggle_tags_visibility,
            bg="#21262D",
            fg="#58A6FF",
            activebackground="#30363D",
            relief=tk.FLAT,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
            padx=10,
            pady=2
        )
        self.toggle_tags_btn.pack(side=tk.RIGHT, padx=5)
        
        # Search box
        tk.Label(
            table_header,
            text="Search:",
            font=("Segoe UI", 9),
            fg="#8B949E",
            bg="#0D1117"
        ).pack(side=tk.RIGHT, padx=(10, 2))
        
        search_entry = tk.Entry(
            table_header,
            textvariable=self.tag_search_var,
            bg="#161B22",
            fg="#C9D1D9",
            insertbackground="#58A6FF",
            relief=tk.FLAT,
            font=("Consolas", 10),
            width=20
        )
        search_entry.pack(side=tk.RIGHT, padx=2)

        # Selection buttons
        select_btn_frame = tk.Frame(table_header, bg="#0D1117")
        select_btn_frame.pack(side=tk.RIGHT, padx=10)

        tk.Button(
            select_btn_frame,
            text="Select All",
            command=self.select_all_tags,
            bg="#21262D",
            fg="#C9D1D9",
            activebackground="#30363D",
            relief=tk.FLAT,
            font=("Segoe UI", 9),
            cursor="hand2",
            padx=10,
            pady=2
        ).pack(side=tk.LEFT, padx=2)

        tk.Button(
            select_btn_frame,
            text="Clear All",
            command=self.clear_all_tags,
            bg="#21262D",
            fg="#C9D1D9",
            activebackground="#30363D",
            relief=tk.FLAT,
            font=("Segoe UI", 9),
            cursor="hand2",
            padx=10,
            pady=2
        ).pack(side=tk.LEFT, padx=2)

        # Tag tree container (for hide/show functionality)
        self.tag_tree_container = tk.Frame(table_container, bg="#0D1117")
        self.tag_tree_container.pack(fill=tk.BOTH, expand=True)

        tree_frame = tk.Frame(self.tag_tree_container, bg="#161B22", relief=tk.RIDGE, bd=1)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        tree_scrollbar = ttk.Scrollbar(tree_frame)
        tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Configure ttk style with Linux/Windows compatibility
        try:
            style = ttk.Style()
            # Use 'clam' theme on all platforms (cross-platform compatible)
            available_themes = style.theme_names()
            if 'clam' in available_themes:
                style.theme_use("clam")
            elif 'alt' in available_themes:
                style.theme_use("alt")  # Fallback for Linux
            
            style.configure(
                "Treeview",
                background="#0D1117",
                foreground="#C9D1D9",
                fieldbackground="#0D1117",
                borderwidth=0,
                font=("Consolas", 10)
            )
            style.configure("Treeview.Heading", background="#161B22", foreground="#58A6FF", font=("Segoe UI", 10, "bold"))
            style.map("Treeview", background=[("selected", "#1F6FEB")])
        except Exception as e:
            print(f"[WARNING] TTK theme configuration failed: {e} - using defaults")

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("Select", "Tag", "Value", "Type", "Time"),
            show="tree headings",
            yscrollcommand=tree_scrollbar.set,
            selectmode="browse"  # Single click selection
        )
        self.tree.heading("#0", text="")
        self.tree.heading("Select", text="✓")
        self.tree.heading("Tag", text="Tag Name")
        self.tree.heading("Value", text="Value")
        self.tree.heading("Type", text="Type")
        self.tree.heading("Time", text="Last Update")
        
        self.tree.column("#0", width=0, stretch=tk.NO)
        self.tree.column("Select", width=40, anchor="center")
        self.tree.column("Tag", width=350, anchor="w")
        self.tree.column("Value", width=120, anchor="center")
        self.tree.column("Type", width=70, anchor="center")
        self.tree.column("Time", width=120, anchor="center")
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scrollbar.config(command=self.tree.yview)
        
        # Bind click event for checkbox toggle
        self.tree.bind("<Button-1>", self.on_tree_click)

        self.tree_items = {}
        
        # Canvas hover support for tooltips
        self.trend_canvas.bind("<Motion>", self.on_canvas_hover)
        self.hover_tooltip = None
        self.trend_hover_data = {}  # Store trend regions for hover detection

        # System log - Simple text widget for console output (no UI overlap)
        self.log_text = scrolledtext.ScrolledText(
            self.root,
            bg="#0D1117",
            fg="#C9D1D9",
            font=("Consolas", 8),
            wrap=tk.WORD,
            relief=tk.FLAT,
            state=tk.DISABLED,
            height=1,  # Minimal - just for log() function to work
            width=1
        )
        # Don't pack it - keep it hidden but functional

        self.log_text.tag_config("INFO", foreground="#58A6FF")
        self.log_text.tag_config("SUCCESS", foreground="#3FB950")
        self.log_text.tag_config("WARNING", foreground="#D29922")
        self.log_text.tag_config("ERROR", foreground="#F85149")
        self.log_text.tag_config("TIMESTAMP", foreground="#8B949E")

        self.update_uptime()
        self.log("INFO", "System initialized - Enhanced scanner ready")
        
        # Start trend update timer
        self.update_trend_display()

    def on_scan_interval_changed(self, event=None):
        """Handle scan interval dropdown change"""
        try:
            selected = self.scan_interval_var.get()
            # Parse milliseconds (e.g., "1000ms" -> 1.0 seconds)
            ms_value = int(selected.replace('ms', ''))
            new_interval = ms_value / 1000.0
            self.scan_interval = new_interval
            
            # Info about caching
            if ms_value < 100:
                self.log("INFO", f"Fast scan {ms_value}ms → Cache → DB batch writes every 1s")
            else:
                self.log("SUCCESS", f"Scan interval: {ms_value}ms ({new_interval}s)")
        except ValueError as e:
            self.log("ERROR", f"Invalid scan interval value: {e}")

    def on_db_toggle(self):
        """Handle database logging toggle"""
        self.db_enabled = self.db_toggle_var.get()
        status = "ENABLED" if self.db_enabled else "DISABLED"
        self.log("INFO", f"Database logging {status}")
    
    def toggle_tags_visibility(self):
        """Toggle tag table visibility"""
        if self.tags_visible:
            self.tag_tree_container.pack_forget()
            self.toggle_tags_btn.config(text="Show Tags ▲")
            self.tags_visible = False
        else:
            self.tag_tree_container.pack(fill=tk.BOTH, expand=True)
            self.toggle_tags_btn.config(text="Hide Tags ▼")
            self.tags_visible = True
    
    def filter_tags(self):
        """Filter tag tree based on search text"""
        if self.headless:
            return
        
        search_text = self.tag_search_var.get().lower()
        
        # If empty, show all
        if not search_text:
            for item in self.tree.get_children():
                self.tree.item(item, tags=())
            return
        
        # Filter tags
        for item in self.tree.get_children():
            tag_name = self.tree.item(item, "values")[1].lower()
            if search_text in tag_name:
                self.tree.item(item, tags=())
                self.tree.see(item)  # Scroll to visible matches
            else:
                self.tree.item(item, tags=("hidden",))
        
        # Configure hidden tag style
        self.tree.tag_configure("hidden", foreground="#21262D")

    def on_tree_click(self, event):
        """Handle tree item click for checkbox toggle"""
        region = self.tree.identify("region", event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            if column == "#1":  # Select column
                item = self.tree.identify_row(event.y)
                if item:
                    tag_name = self.tree.set(item, "Tag")
                    if tag_name in self.selected_tags_for_trend:
                        self.selected_tags_for_trend.remove(tag_name)
                        self.tree.set(item, "Select", "")
                    else:
                        self.selected_tags_for_trend.add(tag_name)
                        self.tree.set(item, "Select", "✓")
                    
                    self.stat_labels['selected'].config(text=str(len(self.selected_tags_for_trend)))
                    self.log("INFO", f"Tag '{tag_name}' {'selected' if tag_name in self.selected_tags_for_trend else 'deselected'} for trend")
    
    def on_canvas_hover(self, event):
        """Show tooltip on canvas hover with value and timestamp"""
        if self.headless or not hasattr(self, 'trend_hover_data'):
            return
        
        # Remove old tooltip
        if self.hover_tooltip:
            if isinstance(self.hover_tooltip, list):
                for item in self.hover_tooltip:
                    self.trend_canvas.delete(item)
            else:
                self.trend_canvas.delete(self.hover_tooltip)
            self.hover_tooltip = None
        
        # Check if mouse is over any trend region
        for tag_name, region_data in self.trend_hover_data.items():
            y_min, y_max, points, timestamps = region_data
            
            if y_min <= event.y <= y_max:
                # Find closest point
                min_dist = float('inf')
                closest_idx = 0
                
                for i in range(0, len(points), 2):
                    x, y = points[i], points[i+1]
                    dist = abs(x - event.x)
                    if dist < min_dist:
                        min_dist = dist
                        closest_idx = i // 2
                
                if min_dist < 30:  # Within 30 pixels
                    timestamp, value = timestamps[closest_idx]
                    
                    # Format timestamp to show milliseconds
                    time_str = timestamp.strftime("%H:%M:%S.%f")[:-3]  # Remove last 3 digits (microseconds)
                    
                    # Format value
                    if isinstance(value, float):
                        value_str = f"{value:.3f}"
                    elif isinstance(value, bool):
                        value_str = "TRUE" if value else "FALSE"
                    else:
                        value_str = str(value)
                    
                    # Create tooltip
                    tooltip_text = f"{tag_name}\\n{value_str}\\n{time_str}"
                    
                    # Draw tooltip box first
                    txt_id = self.trend_canvas.create_text(
                        event.x + 10, event.y - 10,
                        text=tooltip_text,
                        fill="#C9D1D9",
                        font=("Consolas", 9),
                        anchor="nw"
                    )
                    
                    bbox = self.trend_canvas.bbox(txt_id)
                    if bbox:
                        self.trend_canvas.delete(txt_id)
                        
                        box_id = self.trend_canvas.create_rectangle(
                            bbox[0] - 5, bbox[1] - 2,
                            bbox[2] + 5, bbox[3] + 2,
                            fill="#21262D",
                            outline="#58A6FF",
                            width=2
                        )
                        
                        txt_id = self.trend_canvas.create_text(
                            event.x + 10, event.y - 10,
                            text=tooltip_text,
                            fill="#C9D1D9",
                            font=("Consolas", 9, "bold"),
                            anchor="nw"
                        )
                        
                        self.hover_tooltip = [box_id, txt_id]
                    break

    def select_all_tags(self):
        """Select all tags for trending"""
        for item in self.tree.get_children():
            tag_name = self.tree.set(item, "Tag")
            self.selected_tags_for_trend.add(tag_name)
            self.tree.set(item, "Select", "✓")
        self.stat_labels['selected'].config(text=str(len(self.selected_tags_for_trend)))
        self.log("INFO", f"All {len(self.selected_tags_for_trend)} tags selected for trending")

    def clear_all_tags(self):
        """Clear all tag selections"""
        for item in self.tree.get_children():
            self.tree.set(item, "Select", "")
        self.selected_tags_for_trend.clear()
        self.stat_labels['selected'].config(text="0")
        self.log("INFO", "All tag selections cleared")

    def update_trend_display(self):
        """Update the trend chart display"""
        if self.headless:
            return
            
        try:
            # Clear canvas and hover data
            self.trend_canvas.delete("all")
            self.trend_hover_data = {}
            
            if len(self.selected_tags_for_trend) > 0:
                canvas_width = self.trend_canvas.winfo_width()
                canvas_height = self.trend_canvas.winfo_height()
                
                if canvas_width < 100 or canvas_height < 100:
                    # Not ready yet
                    self.root.after(300, self.update_trend_display)
                    return
                
                # Draw title
                self.trend_canvas.create_text(
                    10, 10,
                    text=f"Live Trends - {len(self.selected_tags_for_trend)} Selected",
                    fill="#58A6FF",
                    font=("Segoe UI", 11, "bold"),
                    anchor="nw"
                )
                
                # Draw trends for selected tags + PLC metrics - SCADA DISPLAY
                y_pos = 40  # Start with more space
                sparkline_height = 80  # Large sparklines
                line_height = sparkline_height + 65  # Tag name (20) + sparkline (80) + time axis (20) + gap (15)
                
                tags_drawn = 0
                tags_no_data = []
                
                # Always show PLC Response Time if available - AT TOP
                if '_PLC_ResponseTime' in self.trend_data and len(self.trend_data['_PLC_ResponseTime']) > 0:
                    tags_drawn += 1
                    recent_values = list(self.trend_data['_PLC_ResponseTime'])[-50:]  # More points for smoothness
                    
                    # Tag name ABOVE trend with clear spacing
                    self.trend_canvas.create_text(
                        20, y_pos,
                        text="⚡ PLC Response Time",
                        fill="#FF6B35",
                        font=("Segoe UI", 11, "bold"),
                        anchor="nw"
                    )
                    
                    # Move down for sparkline
                    y_pos += 20
                    
                    # Draw LARGE sparkline
                    x_start = 20
                    x_width = canvas_width - 200  # Full width minus margins
                    
                    values = [float(v[1]) for v in recent_values]
                    if len(values) >= 2:
                        min_val = min(values)
                        max_val = max(values)
                        is_constant = (max_val == min_val)
                        val_range = max_val - min_val if not is_constant else 1
                        
                        # Draw background box with grid
                        self.trend_canvas.create_rectangle(
                            x_start, y_pos,
                            x_start + x_width, y_pos + sparkline_height,
                            outline="#30363D",
                            fill="#0D1117",
                            width=2
                        )
                        
                        # Draw horizontal grid lines
                        for i in range(5):
                            grid_y = y_pos + (i * sparkline_height / 4)
                            self.trend_canvas.create_line(
                                x_start, grid_y,
                                x_start + x_width, grid_y,
                                fill="#21262D",
                                width=1,
                                dash=(2, 4)
                            )
                        
                        # Draw sparkline - THICK LINE
                        if is_constant:
                            # For constant values, draw horizontal line at mid-height
                            y_mid = y_pos + (sparkline_height / 2)
                            self.trend_canvas.create_line(
                                x_start, y_mid,
                                x_start + x_width, y_mid,
                                fill="#FF6B35",
                                width=3,
                                dash=(5, 3)
                            )
                            
                            self.trend_canvas.create_text(
                                x_start + x_width - 80, y_mid - 15,
                                text="CONSTANT",
                                fill="#FF6B35",
                                font=("Consolas", 8, "italic"),
                                anchor="w"
                            )
                            
                            points = [x_start, y_mid, x_start + x_width, y_mid]
                            self.trend_hover_data['PLC Response Time'] = (
                                y_pos, 
                                y_pos + sparkline_height, 
                                points, 
                                recent_values
                            )
                        else:
                            # For varying values, draw normal sparkline
                            points = []
                            for i, val in enumerate(values):
                                x = x_start + (i * x_width / max(len(values) - 1, 1))
                                normalized = (val - min_val) / val_range
                                y = y_pos + sparkline_height - (normalized * sparkline_height)
                                points.extend([x, y])
                            
                            if len(points) >= 4:
                                self.trend_canvas.create_line(
                                    points,
                                    fill="#FF6B35",
                                    width=3,  # Thicker line
                                    smooth=True
                                )
                                
                                # Store hover data
                                self.trend_hover_data['PLC Response Time'] = (
                                    y_pos, 
                                    y_pos + sparkline_height, 
                                    points, 
                                    recent_values
                                )
                                
                                # Draw dots at key points
                                for i in range(0, len(points), 10):  # Every 10th point
                                    self.trend_canvas.create_oval(
                                        points[i]-3, points[i+1]-3,
                                        points[i]+3, points[i+1]+3,
                                        fill="#FF6B35",
                                        outline=""
                                    )
                        
                        # Draw time axis below sparkline
                        time_axis_y = y_pos + sparkline_height + 10
                        # Show first, middle, last timestamps
                        first_time = recent_values[0][0].strftime("%H:%M:%S.%f")[:-3]
                        mid_time = recent_values[len(recent_values)//2][0].strftime("%H:%M:%S.%f")[:-3]
                        last_time = recent_values[-1][0].strftime("%H:%M:%S.%f")[:-3]
                        
                        self.trend_canvas.create_text(
                            x_start, time_axis_y,
                            text=first_time,
                            fill="#8B949E",
                            font=("Consolas", 7),
                            anchor="w"
                        )
                        self.trend_canvas.create_text(
                            x_start + x_width/2, time_axis_y,
                            text=mid_time,
                            fill="#8B949E",
                            font=("Consolas", 7),
                            anchor="center"
                        )
                        self.trend_canvas.create_text(
                            x_start + x_width, time_axis_y,
                            text=last_time,
                            fill="#8B949E",
                            font=("Consolas", 7),
                            anchor="e"
                        )
                        
                        # Current value - LARGE
                        current_val = values[-1]
                        self.trend_canvas.create_text(
                            x_start + x_width + 10, y_pos + sparkline_height/2,
                            text=f"{current_val:.1f}ms",
                            fill="#FF6B35",
                            font=("Consolas", 14, "bold"),
                            anchor="w"
                        )
                        
                        # Min/Max labels
                        self.trend_canvas.create_text(
                            x_start + x_width + 10, y_pos,
                            text=f"Max: {max_val:.1f}",
                            fill="#8B949E",
                            font=("Consolas", 9),
                            anchor="nw"
                        )
                        self.trend_canvas.create_text(
                            x_start + x_width + 10, y_pos + sparkline_height,
                            text=f"Min: {min_val:.1f}",
                            fill="#8B949E",
                            font=("Consolas", 9),
                            anchor="sw"
                        )
                    
                    # Move to next trend (subtract 20 because we already added it above)
                    y_pos += line_height - 20
                
                # Draw all selected tag trends - SCADA FORMAT
                for idx, tag in enumerate(self.selected_tags_for_trend):
                    # Check if tag exists in trend_data
                    if tag not in self.trend_data:
                        tags_no_data.append(tag)
                        continue
                    if len(self.trend_data[tag]) == 0:
                        tags_no_data.append(tag)
                        continue
                    
                    tags_drawn += 1
                    recent_values = list(self.trend_data[tag])[-50:]  # Last 50 points for smooth curves
                    
                    # Tag name with color - ABOVE trend
                    colors = ["#3FB950", "#58A6FF", "#D29922", "#F778BA", "#BC8CFF", "#F85149"]
                    tag_color = colors[tags_drawn % len(colors)]
                    
                    self.trend_canvas.create_text(
                        20, y_pos,
                        text=f"{tag}",
                        fill=tag_color,
                        font=("Segoe UI", 11, "bold"),
                        anchor="nw"
                    )
                    
                    # Move down for sparkline
                    y_pos += 20
                    
                    # Draw LARGE sparkline - same as PLC Response Time
                    x_start = 20
                    x_width = canvas_width - 200
                    
                    if len(recent_values) >= 2:
                        # Get numeric values only
                        values = []
                        for v in recent_values:
                            if isinstance(v[1], (int, float)):
                                values.append(float(v[1]))
                            elif isinstance(v[1], bool):
                                values.append(1.0 if v[1] else 0.0)
                        
                        if len(values) >= 2:
                            min_val = min(values)
                            max_val = max(values)
                            is_constant = (max_val == min_val)
                            val_range = max_val - min_val if not is_constant else 1
                            
                            # Draw background box with grid
                            self.trend_canvas.create_rectangle(
                                x_start, y_pos,
                                x_start + x_width, y_pos + sparkline_height,
                                outline="#30363D",
                                fill="#0D1117",
                                width=2
                            )
                            
                            # Draw horizontal grid lines
                            for i in range(5):
                                grid_y = y_pos + (i * sparkline_height / 4)
                                self.trend_canvas.create_line(
                                    x_start, grid_y,
                                    x_start + x_width, grid_y,
                                    fill="#21262D",
                                    width=1,
                                    dash=(2, 4)
                                )
                            
                            # Draw sparkline - THICK
                            if is_constant:
                                # For constant values, draw horizontal line at mid-height
                                y_mid = y_pos + (sparkline_height / 2)
                                self.trend_canvas.create_line(
                                    x_start, y_mid,
                                    x_start + x_width, y_mid,
                                    fill=tag_color,
                                    width=3,
                                    dash=(5, 3)  # Dashed to indicate constant
                                )
                                
                                # Show "CONSTANT" label
                                self.trend_canvas.create_text(
                                    x_start + x_width - 80, y_mid - 15,
                                    text="CONSTANT",
                                    fill=tag_color,
                                    font=("Consolas", 8, "italic"),
                                    anchor="w"
                                )
                                
                                # Store hover data for constant line
                                points = [x_start, y_mid, x_start + x_width, y_mid]
                                self.trend_hover_data[tag] = (
                                    y_pos,
                                    y_pos + sparkline_height,
                                    points,
                                    recent_values
                                )
                            else:
                                # For varying values, draw normal sparkline
                                points = []
                                for i, val in enumerate(values):
                                    x = x_start + (i * x_width / max(len(values) - 1, 1))
                                    normalized = (val - min_val) / val_range
                                    y = y_pos + sparkline_height - (normalized * sparkline_height)
                                    points.extend([x, y])
                                
                                if len(points) >= 4:
                                    self.trend_canvas.create_line(
                                        points,
                                        fill=tag_color,
                                        width=3,  # THICKER
                                        smooth=True
                                    )
                                    
                                    # Store hover data
                                    self.trend_hover_data[tag] = (
                                        y_pos,
                                        y_pos + sparkline_height,
                                        points,
                                        recent_values
                                    )
                                    
                                    # Draw dots at key points only
                                    for i in range(0, len(points), 10):
                                        self.trend_canvas.create_oval(
                                            points[i]-3, points[i+1]-3,
                                            points[i]+3, points[i+1]+3,
                                            fill=tag_color,
                                            outline=""
                                        )
                            
                            # Draw time axis
                            time_axis_y = y_pos + sparkline_height + 10
                            first_time = recent_values[0][0].strftime("%H:%M:%S.%f")[:-3]
                            mid_time = recent_values[len(recent_values)//2][0].strftime("%H:%M:%S.%f")[:-3]
                            last_time = recent_values[-1][0].strftime("%H:%M:%S.%f")[:-3]
                            
                            self.trend_canvas.create_text(
                                x_start, time_axis_y,
                                text=first_time,
                                fill="#8B949E",
                                font=("Consolas", 7),
                                anchor="w"
                            )
                            self.trend_canvas.create_text(
                                x_start + x_width/2, time_axis_y,
                                text=mid_time,
                                fill="#8B949E",
                                font=("Consolas", 7),
                                anchor="center"
                            )
                            self.trend_canvas.create_text(
                                x_start + x_width, time_axis_y,
                                text=last_time,
                                fill="#8B949E",
                                font=("Consolas", 7),
                                anchor="e"
                            )
                            
                            # Current value display - LARGE
                            current_val = values[-1]
                            if abs(current_val) < 0.01:
                                display_val = f"{current_val:.4f}"
                            elif abs(current_val) > 1000:
                                display_val = f"{current_val:.0f}"
                            else:
                                display_val = f"{current_val:.2f}"
                            
                            self.trend_canvas.create_text(
                                x_start + x_width + 10, y_pos + sparkline_height/2,
                                text=display_val,
                                fill=tag_color,
                                font=("Consolas", 14, "bold"),
                                anchor="w"
                            )
                            
                            # Min/Max labels
                            self.trend_canvas.create_text(
                                x_start + x_width + 10, y_pos,
                                text=f"Max: {max_val:.2f}",
                                fill="#8B949E",
                                font=("Consolas", 9),
                                anchor="nw"
                            )
                            self.trend_canvas.create_text(
                                x_start + x_width + 10, y_pos + sparkline_height,
                                text=f"Min: {min_val:.2f}",
                                fill="#8B949E",
                                font=("Consolas", 9),
                                anchor="sw"
                            )
                    elif len(recent_values) == 1:
                        # Single value - just show it
                        current_val = recent_values[-1][1]
                        if isinstance(current_val, (int, float)):
                            display_val = f"{current_val:.2f}"
                        elif isinstance(current_val, bool):
                            display_val = "TRUE" if current_val else "FALSE"
                        else:
                            display_val = str(current_val)
                        
                        self.trend_canvas.create_text(
                            x_start, y_pos + 10,
                            text=f"→ {display_val}",
                            fill=tag_color,
                            font=("Consolas", 9),
                            anchor="w"
                        )
                    
                    # Move to next trend (subtract 20 because we already added it above)
                    y_pos += line_height - 20
                
                # Show messages
                if tags_drawn == 0 and len(self.selected_tags_for_trend) > 0:
                    # Selected but no data yet  
                    tags_list = ", ".join(list(tags_no_data)[:5])
                    self.trend_canvas.create_text(
                        canvas_width / 2, canvas_height / 2,
                        text=f"⏳ Collecting data for {len(self.selected_tags_for_trend)} selected tag(s)...\n\n{tags_list}\n\n(Sparklines will appear within 1-2 scans)",
                        fill="#D29922",
                        font=("Segoe UI", 10),
                        justify=tk.CENTER
                    )
            else:
                # No tags selected
                canvas_width = self.trend_canvas.winfo_width()
                canvas_height = self.trend_canvas.winfo_height()
                self.trend_canvas.create_text(
                    canvas_width / 2, canvas_height / 2,
                    text="✓ Select tags from the left panel\n(Click checkboxes to enable trends)",
                    fill="#8B949E",
                    font=("Segoe UI", 11),
                    justify=tk.CENTER
                )
            
            # Schedule next update (faster for smooth animation)
            self.root.after(300, self.update_trend_display)
        except Exception as e:
            print(f"[ERROR] Trend update error: {e}")
            self.root.after(1000, self.update_trend_display)

    def update(self, tag, value, value_type):
        """Update tag value in treeview and trend data"""
        if self.headless:
            if len(self.stats.get('_tag_cache', {})) < 50:
                print(f"[TAG] {tag} = {value} ({value_type})")
            if '_tag_cache' not in self.stats:
                self.stats['_tag_cache'] = {}
            self.stats['_tag_cache'][tag] = True
            
            # Store trend data even in headless mode
            if isinstance(value, (int, float, bool)):
                numeric_value = float(value) if not isinstance(value, bool) else (1.0 if value else 0.0)
                self.trend_data[tag].append((datetime.now(), numeric_value))
            return
            
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            # Format display value for tree
            if isinstance(value, bool):
                display_value = "TRUE" if value else "FALSE"
            elif isinstance(value, float):
                if abs(value) < 0.001:
                    display_value = f"{value:.6f}".rstrip('0').rstrip('.')
                elif abs(value) < 1:
                    display_value = f"{value:.4f}".rstrip('0').rstrip('.')
                elif abs(value) > 1e9:
                    display_value = f"{value:.2e}"
                else:
                    display_value = f"{value:.2f}".rstrip('0').rstrip('.')
            else:
                display_value = str(value)
            
            if tag not in self.tree_items:
                item_id = self.tree.insert("", "end", values=("", tag, display_value, value_type, timestamp))
                self.tree_items[tag] = item_id
                self.stat_labels['tags'].config(text=str(len(self.tree_items)))
            else:
                item_id = self.tree_items[tag]
                current_select = self.tree.set(item_id, "Select")
                self.tree.set(item_id, "Value", display_value)
                self.tree.set(item_id, "Time", timestamp)
            
            # Store trend data for numeric values (ALL tags, not just selected)
            if isinstance(value, (int, float, bool)):
                numeric_value = float(value) if not isinstance(value, bool) else (1.0 if value else 0.0)
                self.trend_data[tag].append((datetime.now(), numeric_value))
                
        except Exception as e:
            self.log("ERROR", f"UI update error for tag {tag}: {e}")

    def set_plc_status(self, connected):
        """Update PLC connection indicator"""
        if self.headless:
            status = "CONNECTED" if connected else "DISCONNECTED"
            print(f"[PLC] Status: {status} ({PLC_IP})")
            return
            
        try:
            if connected:
                self.plc_status_dot.itemconfig(self.plc_status_circle, fill="#3FB950")
                self.plc_status_label.config(text="PLC: Connected", fg="#3FB950")
            else:
                self.plc_status_dot.itemconfig(self.plc_status_circle, fill="#F85149")
                self.plc_status_label.config(text="PLC: Disconnected", fg="#F85149")
        except:
            pass

    def set_db_status(self, connected):
        """Update database connection indicator"""
        if self.headless:
            status = "CONNECTED" if connected else "DISCONNECTED"
            print(f"[DATABASE] Status: {status} ({DB_CONFIG['host']}:{DB_CONFIG['port']})")
            return
            
        try:
            if connected:
                self.db_status_dot.itemconfig(self.db_status_circle, fill="#3FB950")
                self.db_status_label.config(text="DB: Connected", fg="#3FB950")
            else:
                self.db_status_dot.itemconfig(self.db_status_circle, fill="#6E7681")
                self.db_status_label.config(text="DB: Disconnected", fg="#6E7681")
        except:
            pass

    def update_plc_metrics_display(self):
        """Update PLC performance metrics in UI"""
        if self.headless or not hasattr(self, 'stat_labels'):
            return
            
        try:
            # Update response time
            response_ms = self.plc_metrics.get('response_time_ms', 0)
            self.stat_labels['response_time'].config(text=f"{response_ms:.1f}ms")
            
            # Color code response time
            if response_ms < 50:
                self.stat_labels['response_time'].config(fg="#3FB950")  # Green
            elif response_ms < 100:
                self.stat_labels['response_time'].config(fg="#D29922")  # Yellow
            else:
                self.stat_labels['response_time'].config(fg="#F85149")  # Red
            
            # Update uptime
            uptime = str(datetime.now() - self.stats['start_time']).split('.')[0]
            self.stat_labels['uptime'].config(text=uptime)
            
        except Exception as e:
            print(f"[ERROR] Failed to update PLC metrics: {e}")

    def log(self, level, message):
        """Add message to log viewer"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        
        self.log_queue.append((level, log_entry))
        
        if self.headless:
            print(log_entry)
            if level == "ERROR":
                self.stats['errors'] += 1
            return
        
        try:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, f"[{timestamp}] ", "TIMESTAMP")
            self.log_text.insert(tk.END, f"[{level}] ", level)
            self.log_text.insert(tk.END, f"{message}\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)

            if level == "ERROR":
                self.stats['errors'] += 1
                self.stat_labels['errors'].config(text=str(self.stats['errors']))
        except:
            print(log_entry)

    def clear_log(self):
        """Clear log viewer"""
        if self.headless:
            print("[SYSTEM] Log cleared")
            self.log_queue.clear()
            return
            
        try:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.delete(1.0, tk.END)
            self.log_text.config(state=tk.DISABLED)
            self.log_queue.clear()
            self.log("INFO", "Log cleared")
        except:
            pass

    def increment_stat(self, stat_name):
        """Increment statistics counter"""
        if stat_name in self.stats:
            self.stats[stat_name] += 1
            if self.headless and self.stats[stat_name] % 100 == 0:
                print(f"[STATS] {stat_name.upper()}: {self.stats[stat_name]}")
                return
                
        try:
            if stat_name in self.stat_labels:
                self.stat_labels[stat_name].config(text=str(self.stats[stat_name]))
        except:
            pass

    def update_uptime(self):
        """Update uptime counter every second"""
        if self.headless:
            return
            
        try:
            uptime = datetime.now() - self.stats['start_time']
            hours, remainder = divmod(int(uptime.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            self.stat_labels['uptime'].config(text=f"{hours:02d}:{minutes:02d}:{seconds:02d}")
            self.root.after(1000, self.update_uptime)
        except:
            pass

    def start(self):
        """Start UI - GUI or headless mode"""
        if self.headless:
            print("[HEADLESS MODE] UI running in console-only mode")
            print("[SYSTEM] Press Ctrl+C to stop")
            try:
                while True:
                    time.sleep(1)
                    uptime = datetime.now() - self.stats['start_time']
                    if int(uptime.total_seconds()) % 60 == 0:
                        print(f"[UPTIME] {int(uptime.total_seconds() / 60)} minutes | "
                              f"PLC Reads: {self.stats['plc_reads']} | "
                              f"DB Writes: {self.stats['db_writes']} | "
                              f"Errors: {self.stats['errors']}")
            except KeyboardInterrupt:
                print("\n[SHUTDOWN] Shutting down gracefully...")
                sys.exit(0)
        else:
            self.root.mainloop()


ui = EnhancedUI()


def db_writer_loop():
    """Database writer thread - writes cache to DB every 1 second, forces unchanged values every 2 minutes"""
    last_write_time = datetime.now(timezone.utc)
    write_interval = 1.0  # Check every 1 second
    forced_write_interval = 120.0  # Force write unchanged values every 2 minutes
    last_written_values = {}  # Track last written value per tag {tag_id: value}
    last_write_time_per_tag = {}  # Track last write timestamp per tag {tag_id: timestamp}
    
    while True:
        try:
            time.sleep(write_interval)
            
            current_time = datetime.now(timezone.utc)
            
            # Get only NEW values since last write
            batch = tag_cache.get_batch(since_timestamp=last_write_time)
            
            # ALWAYS update last_write_time to prevent re-processing same data
            last_write_time = current_time
            
            if not batch or not ui.db_enabled:
                continue
            
            # Prepare rows for database
            latest_dict = {}  # De-duplicate: keep only latest value per tag
            ts_rows = []
            filtered_count = 0
            forced_write_count = 0
            
            for tag_id, ts, value, quality in batch:
                # Determine value type
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
                
                # VALUE CHANGE DETECTION - Check per-tag forced write timing
                value_changed = True
                force_write = False
                
                # Check if value changed
                if tag_id in last_written_values:
                    last_val = last_written_values[tag_id]
                    # Compare based on type
                    if isinstance(value, bool):
                        value_changed = (value != last_val)
                    elif isinstance(value, (int, float)):
                        value_changed = (value != last_val)
                    elif isinstance(value, str):
                        value_changed = (value != last_val)
                
                # Check if forced write needed for THIS tag (2 minutes elapsed)
                if tag_id in last_write_time_per_tag:
                    time_since_last_write = (current_time - last_write_time_per_tag[tag_id]).total_seconds()
                    if time_since_last_write >= forced_write_interval:
                        force_write = True
                        forced_write_count += 1
                
                # Skip if value unchanged AND not time for forced write
                if not value_changed and not force_write:
                    filtered_count += 1
                    continue  # Skip unchanged values
                
                # Update last written value and timestamp
                last_written_values[tag_id] = value
                last_write_time_per_tag[tag_id] = current_time
                
                # For latest_value: keep only most recent per tag (overwrite if exists)
                if tag_id not in latest_dict or ts > latest_dict[tag_id][1]:
                    latest_dict[tag_id] = (tag_id, ts, num, text, boolean, quality)
                
                # For timeseries: write samples (filtered or all based on UI setting)
                ts_rows.append((ts, tag_id, num, text, boolean, quality, 'P'))
            
            # Convert dict to list for insert
            latest_rows = list(latest_dict.values())
            
            # Write to database
            if latest_rows or ts_rows:
                db_success = False
                if latest_rows:
                    if insert_latest_values(latest_rows):
                        db_success = True
                if ts_rows:
                    if insert_timeseries(ts_rows):
                        db_success = True
                
                if db_success:
                    ui.set_db_status(True)
                    ui.increment_stat('db_writes')
                    
                    # Update filtered counter
                    if filtered_count > 0:
                        ui.stats['filtered'] += filtered_count
                        if not ui.headless:
                            ui.stat_labels['filtered'].config(text=str(ui.stats['filtered']))
                    
                    total_samples = len(batch)
                    if forced_write_count > 0:
                        ui.log("INFO", f"DB write: {len(ts_rows)} total ({len(ts_rows) - forced_write_count} changed, {forced_write_count} forced 2-min), {filtered_count} skipped, {total_samples} scanned")
                    else:
                        ui.log("INFO", f"DB write: {len(ts_rows)} changed, {filtered_count} skipped (unchanged), {total_samples} scanned")
                    
                    # Clean old cache (keep last 10 seconds) - ONLY when DB write succeeds
                    cleanup_time = current_time - timedelta(seconds=10)
                    tag_cache.clear_old(cleanup_time)
                else:
                    # DATABASE WRITE FAILED - Check if emergency cleanup needed
                    ui.set_db_status(False)
                    ui.log("ERROR", f"Database write failed - Latest: {len(latest_rows)} rows, Timeseries: {len(ts_rows)} rows")
                    
                    # Check cache size - emergency cleanup ONLY if cache too large
                    needs_cleanup, total_values = tag_cache.check_emergency_cleanup()
                    if needs_cleanup:
                        before, after = tag_cache.emergency_cleanup()
                        ui.log("WARNING", f"🚨 EMERGENCY CACHE CLEANUP: {before} → {after} values (DB connection lost, preventing memory overflow)")
        
        except Exception as e:
            ui.log("ERROR", f"DB writer error: {e}")
            import traceback
            print(f"[DB WRITER EXCEPTION] {traceback.format_exc()}")
            
            # Emergency cleanup on exception too (prevent crash)
            needs_cleanup, total_values = tag_cache.check_emergency_cleanup()
            if needs_cleanup:
                before, after = tag_cache.emergency_cleanup()
                ui.log("WARNING", f"🚨 EMERGENCY CACHE CLEANUP (Exception): {before} → {after} values")
            
            time.sleep(1)


def plc_loop():
    """Smart PLC scanning loop - only caches CHANGED values"""
    retry_count = 0
    max_retries = 5
    
    while retry_count < max_retries:
        try:
            ui.log("INFO", f"Connecting to PLC at {PLC_IP} (Attempt {retry_count + 1}/{max_retries})")
            
            with LogixDriver(PLC_PATH) as plc:
                ui.set_plc_status(True)
                ui.log("SUCCESS", f"PLC connected: {PLC_IP}")
                
                tags = plc.get_tag_list()
                tag_names = []

                for tag in tags:
                    name = getattr(tag, "tag_name", None) or tag.get("tag_name")
                    if not name:
                        continue
                    if getattr(tag, "array_dims", None) or getattr(tag, "structured", None):
                        continue
                    tag_names.append(name)

                ui.log("SUCCESS", f"Started monitoring {len(tag_names)} tags from PLC")
                
                # Try to read controller diagnostics (Allen-Bradley ControlLogix)
                controller_info = plc.get_plc_info()
                if controller_info:
                    ui.log("INFO", f"Controller: {controller_info}")
                
                retry_count = 0
                scan_count = 0
                last_log_time = 0
                log_interval = 5.0  # Log every 5 seconds
                
                # PLC-LEVEL CHANGE DETECTION - Track last scanned value per tag
                last_scanned_values = {}  # {tag_name: last_value}

                while True:
                    scan_count += 1
                    scan_start_time = time.time()
                    
                    # Measure PLC response time
                    read_start = time.time()
                    results = plc.read(*tag_names)
                    read_end = time.time()
                    response_ms = (read_end - read_start) * 1000
                    
                    # Update PLC metrics
                    ui.plc_metrics['response_time_ms'] = response_ms
                    ui.plc_metrics['last_update'] = datetime.now()
                    
                    # Store response time as trendable data
                    ui.trend_data['_PLC_ResponseTime'].append((datetime.now(), response_ms))
                    
                    ts_utc = datetime.now(timezone.utc)
                    value_count = 0
                    changed_count = 0

                    for tag, res in zip(tag_names, results):
                        if res.error:
                            continue

                        val = res.value
                        if val is None:
                            continue

                        quality = 'G'
                        value_type = ""
                        
                        # Determine value type and raw value
                        if isinstance(val, bool):
                            raw_value = val
                            value_type = "BOOL"
                        elif isinstance(val, (int, float)):
                            raw_value = float(val)
                            if abs(raw_value) < 1e-10:
                                raw_value = 0.0
                            value_type = "REAL" if isinstance(val, float) else "INT"
                        elif isinstance(val, str):
                            raw_value = val
                            value_type = "STRING"
                        else:
                            continue
                        
                        # PLC-LEVEL CHANGE DETECTION - Only cache if value changed
                        value_changed = True
                        if tag in last_scanned_values:
                            if raw_value == last_scanned_values[tag]:
                                value_changed = False
                        
                        # Only write CHANGED values to cache (optimization)
                        if value_changed:
                            tag_cache.put(tag, ts_utc, raw_value, quality)
                            last_scanned_values[tag] = raw_value
                            changed_count += 1
                        
                        # Update UI (less frequent updates for performance)
                        if scan_count % 10 == 0 or ui.scan_interval >= 0.1:  # Every 10 scans or slow mode
                            ui.update(tag, raw_value, value_type)
                        
                        value_count += 1

                    if value_count > 0:
                        ui.increment_stat('plc_reads')
                        ui.update_plc_metrics_display()
                        
                        # Rate-limited logging (every 5 seconds)
                        current_time = time.time()
                        if current_time - last_log_time >= log_interval:
                            cache_stats = tag_cache.get_stats()
                            ui.log("INFO", f"Scan: {scan_count} | Tags: {value_count} scanned, {changed_count} changed | Cache: {cache_stats['total_values']} values | Response: {response_ms:.1f}ms")
                            last_log_time = current_time
                    
                    # Adaptive sleep (compensate for processing time)
                    scan_duration = time.time() - scan_start_time
                    sleep_time = max(0.001, ui.scan_interval - scan_duration)
                    time.sleep(sleep_time)

        except Exception as e:
            retry_count += 1
            error_msg = f"PLC connection error (Retry {retry_count}/{max_retries}): {str(e)}"
            ui.log("ERROR", error_msg)
            ui.set_plc_status(False)
            
            if retry_count < max_retries:
                time.sleep(5)
            else:
                break
    
    ui.log("ERROR", "Max PLC connection retries reached - system stopped")
    ui.set_plc_status(False)


if __name__ == "__main__":
    print("=" * 70)
    print("  PLC Tag Scanner - Enhanced Edition")
    print("  Features: Live Trends | DB Logging | Tag Selection")
    print("  PLC: Allen-Bradley ControlLogix")
    print("  Database: PostgreSQL TimescaleDB")
    print("=" * 70)
    
    if not HEADLESS_MODE:
        ui.log("INFO", "=" * 60)
        ui.log("INFO", "System Starting - Enhanced PLC Scanner")
        ui.log("INFO", f"PLC Target: {PLC_IP}")
        ui.log("INFO", f"Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
        ui.log("INFO", f"Default Scan Interval: {DEFAULT_SCAN_INTERVAL}s")
        ui.log("INFO", "=" * 60)
    
    # Start PLC scanner thread (fast scanning → cache)
    plc_thread = threading.Thread(target=plc_loop, daemon=True, name="PLCScanner")
    plc_thread.start()
    
    # Start DB writer thread (cache → DB every 1 second)
    db_thread = threading.Thread(target=db_writer_loop, daemon=True, name="DBWriter")
    db_thread.start()
    
    # Give threads time to start
    time.sleep(0.5)
    
    ui.log("INFO", "Modular architecture: PLC Scanner → Cache → DB Writer (1s batches)")
    
    # Start UI (blocks here)
    ui.start()
