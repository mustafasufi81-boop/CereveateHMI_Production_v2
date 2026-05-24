#!/usr/bin/env python3
"""
🏭 Professional PLC Scanner - Enterprise Edition
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Real-time Industrial Data Acquisition & Monitoring
Author: Cereveate Tech | Shahnawaz Mustafa
Version: 2.0 - Professional UI
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

try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext, messagebox, font
    HEADLESS_MODE = False
except Exception as e:
    print(f"[WARNING] Display not available: {e}")
    HEADLESS_MODE = True
    import tkinter as tk
    from tkinter import ttk, scrolledtext, messagebox

from pycomm3 import LogixDriver
import psycopg2
from psycopg2.extras import execute_values

# ================= CONFIGURATION =================
PLC_IP = "192.168.0.20"
PLC_PATH = f"{PLC_IP}/1,0"

DB_CONFIG = {
    'host': '192.168.0.120',
    'port': 5432,
    'database': 'Cereveate',
    'user': 'cereveate',
    'password': 'cereveate@222',
    'sslmode': 'disable'
}

DEFAULT_SCAN_INTERVAL = 1.0
MAX_TREND_POINTS = 100
MAX_CACHE_SIZE = 10000
FORCED_WRITE_INTERVAL = 120.0  # 2 minutes

# Modern Color Palette
COLORS = {
    'bg_dark': '#1A1D23',
    'bg_medium': '#252932',
    'bg_light': '#2D3139',
    'accent_blue': '#4A9EFF',
    'accent_green': '#00D084',
    'accent_orange': '#FF9F40',
    'accent_red': '#FF5757',
    'accent_yellow': '#FFD93D',
    'accent_purple': '#A78BFA',
    'text_primary': '#E8EAED',
    'text_secondary': '#9BA3AF',
    'border': '#3E4451',
    'success': '#00D084',
    'warning': '#FFB020',
    'error': '#FF5757',
    'info': '#4A9EFF'
}


class TagCache:
    """Thread-safe cache for PLC tag values with emergency cleanup"""
    def __init__(self, max_size=MAX_CACHE_SIZE):
        self.cache = {}
        self.lock = RLock()
        self.max_size = max_size
        self.stats = {'reads': 0, 'writes': 0, 'cleanups': 0, 'emergency_cleanups': 0}
        self.max_total_values = 50000  # Emergency threshold (50K values total)
    
    def put(self, tag_id, timestamp, value, quality='G'):
        with self.lock:
            if tag_id not in self.cache:
                self.cache[tag_id] = deque(maxlen=self.max_size)
            self.cache[tag_id].append((timestamp, value, quality))
            self.stats['writes'] += 1
            
            if len(self.cache[tag_id]) >= self.max_size:
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
        with self.lock:
            self.stats['reads'] += 1
            if tag_id in self.cache and len(self.cache[tag_id]) > 0:
                return self.cache[tag_id][-1]
            return None
    
    def get_batch(self, since_timestamp=None):
        with self.lock:
            batch = []
            for tag_id, values in self.cache.items():
                for ts, value, quality in values:
                    if since_timestamp is None or ts > since_timestamp:
                        batch.append((tag_id, ts, value, quality))
            return batch
    
    def clear_old(self, before_timestamp):
        with self.lock:
            for tag_id in list(self.cache.keys()):
                if tag_id in self.cache:
                    self.cache[tag_id] = deque(
                        [(ts, val, q) for ts, val, q in self.cache[tag_id] if ts >= before_timestamp],
                        maxlen=self.max_size
                    )
                    if len(self.cache[tag_id]) == 0:
                        del self.cache[tag_id]
    
    def get_stats(self):
        with self.lock:
            return {
                'tags': len(self.cache),
                'total_values': sum(len(v) for v in self.cache.values()),
                **self.stats
            }


tag_cache = TagCache()


# ================= DATABASE FUNCTIONS =================
def connect_db():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False
        return conn
    except Exception as e:
        print(f"[ERROR] DB connection failed: {e}")
        return None


def insert_latest_values(rows):
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
        print(f"[ERROR] Latest-value insert: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False


def insert_timeseries(rows):
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
        print(f"[ERROR] Timeseries insert: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False


class ProfessionalUI:
    def __init__(self):
        self.headless = HEADLESS_MODE
        self.stats = {
            'plc_reads': 0,
            'db_writes': 0,
            'filtered': 0,
            'errors': 0,
            'start_time': datetime.now()
        }
        self.log_queue = deque(maxlen=1000)
        self.scan_interval = DEFAULT_SCAN_INTERVAL
        self.db_enabled = True
        
        self.plc_metrics = {
            'response_time_ms': 0,
            'last_update': None
        }
        
        self.tags_visible = True
        self.trend_data = defaultdict(lambda: deque(maxlen=MAX_TREND_POINTS))
        self.selected_tags_for_trend = set()
        
        if self.headless:
            print("[HEADLESS MODE] Running without GUI")
            self.root = None
            return
            
        try:
            self.root = tk.Tk()
            self.root.title("🏭 Professional PLC Scanner - Enterprise Edition")
            self.root.geometry("1800x1000")
            self.root.configure(bg=COLORS['bg_dark'])
            self.root.minsize(1400, 800)
            self._build_professional_gui()
        except Exception as e:
            print(f"[ERROR] Failed to create GUI: {e}")
            self.headless = True
            self.root = None
    
    def _build_professional_gui(self):
        """Build modern professional UI"""
        self.tag_search_var = tk.StringVar()
        self.tag_search_var.trace('w', lambda *args: self.filter_tags())
        
        # Custom fonts
        self.font_header = font.Font(family="Segoe UI", size=24, weight="bold")
        self.font_title = font.Font(family="Segoe UI", size=14, weight="bold")
        self.font_normal = font.Font(family="Segoe UI", size=10)
        self.font_mono = font.Font(family="Consolas", size=10)
        
        # ========== TOP HEADER WITH GRADIENT EFFECT ==========
        header_frame = tk.Frame(self.root, bg=COLORS['bg_medium'], height=100)
        header_frame.pack(fill=tk.X, padx=0, pady=0)
        header_frame.pack_propagate(False)

        # Logo and Title
        title_frame = tk.Frame(header_frame, bg=COLORS['bg_medium'])
        title_frame.pack(side=tk.LEFT, padx=30, pady=20)
        
        tk.Label(
            title_frame,
            text="🏭",
            font=("Segoe UI", 32),
            bg=COLORS['bg_medium'],
            fg=COLORS['accent_blue']
        ).pack(side=tk.LEFT, padx=(0, 15))
        
        title_container = tk.Frame(title_frame, bg=COLORS['bg_medium'])
        title_container.pack(side=tk.LEFT)
        
        tk.Label(
            title_container,
            text="Professional PLC Scanner",
            font=self.font_header,
            fg=COLORS['text_primary'],
            bg=COLORS['bg_medium']
        ).pack(anchor=tk.W)
        
        tk.Label(
            title_container,
            text="Real-time Industrial Data Acquisition • Enterprise Edition",
            font=("Segoe UI", 9),
            fg=COLORS['text_secondary'],
            bg=COLORS['bg_medium']
        ).pack(anchor=tk.W)

        # Status Indicators (Right side)
        status_frame = tk.Frame(header_frame, bg=COLORS['bg_medium'])
        status_frame.pack(side=tk.RIGHT, padx=30)
        
        self._create_status_indicator(status_frame, "PLC", COLORS['text_secondary'])
        self._create_status_indicator(status_frame, "DATABASE", COLORS['text_secondary'])

        # ========== CONTROL BAR ==========
        control_frame = tk.Frame(self.root, bg=COLORS['bg_light'], height=60)
        control_frame.pack(fill=tk.X, padx=0, pady=0)
        control_frame.pack_propagate(False)

        # Scan Interval
        self._create_control_group(control_frame, "Scan Interval", ["1ms", "5ms", "10ms", "50ms", "100ms", "500ms", "1000ms", "2000ms"])
        
        # DB Toggle
        self.db_toggle_var = tk.BooleanVar(value=True)
        db_frame = tk.Frame(control_frame, bg=COLORS['bg_light'])
        db_frame.pack(side=tk.LEFT, padx=20)
        
        self._create_modern_checkbox(db_frame, "Database Logging", self.db_toggle_var, self.on_db_toggle)

        # ========== STATISTICS DASHBOARD ==========
        stats_frame = tk.Frame(self.root, bg=COLORS['bg_dark'])
        stats_frame.pack(fill=tk.X, padx=20, pady=(10, 0))
        
        self.stat_cards = {}
        stat_configs = [
            ("📊 Tags", "tags", "0", COLORS['accent_blue']),
            ("✓ Selected", "selected", "0", COLORS['accent_purple']),
            ("⚡ PLC Reads", "plc_reads", "0", COLORS['accent_green']),
            ("💾 DB Writes", "db_writes", "0", COLORS['success']),
            ("⏭ Skipped", "filtered", "0", COLORS['accent_yellow']),
            ("⚠ Errors", "errors", "0", COLORS['error']),
            ("📡 Response", "response_time", "0ms", COLORS['accent_orange']),
            ("⏱ Uptime", "uptime", "00:00:00", COLORS['info'])
        ]
        
        for label, key, value, color in stat_configs:
            self._create_stat_card(stats_frame, label, key, value, color)

        # ========== MAIN CONTENT ==========
        main_container = tk.Frame(self.root, bg=COLORS['bg_dark'])
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # TRENDS (Top 60%)
        self._create_trends_section(main_container)
        
        # TAGS TABLE (Bottom 40%)
        self._create_tags_section(main_container)

        # Hidden log
        self.log_text = scrolledtext.ScrolledText(
            self.root, bg=COLORS['bg_dark'], fg=COLORS['text_primary'],
            font=self.font_mono, wrap=tk.WORD, relief=tk.FLAT,
            state=tk.DISABLED, height=1, width=1
        )
        
        self.update_uptime()
        self.log("INFO", "🚀 Professional PLC Scanner initialized")
        self.update_trend_display()

    def _create_status_indicator(self, parent, label, color):
        """Create modern status indicator"""
        container = tk.Frame(parent, bg=COLORS['bg_light'], relief=tk.FLAT, bd=0)
        container.pack(side=tk.LEFT, padx=10, pady=10)
        
        # Status dot
        canvas = tk.Canvas(container, width=12, height=12, bg=COLORS['bg_light'], highlightthickness=0)
        canvas.pack(side=tk.LEFT, padx=(5, 8))
        circle = canvas.create_oval(2, 2, 10, 10, fill=color, outline="")
        
        # Label
        lbl = tk.Label(
            container, text=label,
            font=("Segoe UI", 10, "bold"),
            fg=color, bg=COLORS['bg_light']
        )
        lbl.pack(side=tk.LEFT)
        
        # Store references
        if label == "PLC":
            self.plc_status_dot = canvas
            self.plc_status_circle = circle
            self.plc_status_label = lbl
        else:
            self.db_status_dot = canvas
            self.db_status_circle = circle
            self.db_status_label = lbl

    def _create_control_group(self, parent, label, options):
        """Create control group with dropdown"""
        frame = tk.Frame(parent, bg=COLORS['bg_light'])
        frame.pack(side=tk.LEFT, padx=20, pady=10)
        
        tk.Label(
            frame, text=label,
            font=("Segoe UI", 10, "bold"),
            fg=COLORS['text_primary'], bg=COLORS['bg_light']
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        self.scan_interval_var = tk.StringVar(value="1000ms")
        dropdown = ttk.Combobox(
            frame, textvariable=self.scan_interval_var,
            values=options, state="readonly", width=12, font=self.font_normal
        )
        dropdown.pack(side=tk.LEFT)
        dropdown.bind("<<ComboboxSelected>>", self.on_scan_interval_changed)
        
        # Style dropdown
        style = ttk.Style()
        style.configure('TCombobox', fieldbackground=COLORS['bg_medium'], background=COLORS['bg_medium'])

    def _create_modern_checkbox(self, parent, text, variable, command):
        """Create modern styled checkbox"""
        cb = tk.Checkbutton(
            parent, text=text, variable=variable, command=command,
            font=("Segoe UI", 10, "bold"),
            fg=COLORS['text_primary'], bg=COLORS['bg_light'],
            selectcolor=COLORS['bg_medium'],
            activebackground=COLORS['bg_light'],
            activeforeground=COLORS['accent_blue'],
            cursor="hand2"
        )
        cb.pack()
        return cb

    def _create_stat_card(self, parent, label, key, value, color):
        """Create modern statistic card"""
        card = tk.Frame(parent, bg=COLORS['bg_medium'], relief=tk.FLAT, bd=0)
        card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Inner padding
        inner = tk.Frame(card, bg=COLORS['bg_medium'])
        inner.pack(fill=tk.BOTH, expand=True, padx=15, pady=12)
        
        # Label
        tk.Label(
            inner, text=label,
            font=("Segoe UI", 9),
            fg=COLORS['text_secondary'], bg=COLORS['bg_medium']
        ).pack(anchor=tk.W)
        
        # Value
        value_lbl = tk.Label(
            inner, text=value,
            font=("Segoe UI", 16, "bold"),
            fg=color, bg=COLORS['bg_medium']
        )
        value_lbl.pack(anchor=tk.W, pady=(5, 0))
        
        self.stat_cards[key] = value_lbl

    def _create_trends_section(self, parent):
        """Create professional trends section"""
        trend_container = tk.Frame(parent, bg=COLORS['bg_dark'])
        trend_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Header
        header = tk.Frame(trend_container, bg=COLORS['bg_dark'], height=50)
        header.pack(fill=tk.X, pady=(0, 10))
        header.pack_propagate(False)
        
        tk.Label(
            header, text="📈 Live Trends",
            font=self.font_title, fg=COLORS['accent_blue'], bg=COLORS['bg_dark']
        ).pack(side=tk.LEFT, padx=10, anchor=tk.W)
        
        tk.Label(
            header, text="Select tags below to visualize real-time data",
            font=("Segoe UI", 9, "italic"),
            fg=COLORS['text_secondary'], bg=COLORS['bg_dark']
        ).pack(side=tk.LEFT, padx=10)
        
        # Canvas
        canvas_frame = tk.Frame(trend_container, bg=COLORS['bg_medium'], relief=tk.FLAT, bd=0)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(canvas_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.trend_canvas = tk.Canvas(
            canvas_frame, bg=COLORS['bg_medium'],
            highlightthickness=0, yscrollcommand=scrollbar.set
        )
        self.trend_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.trend_canvas.yview)
        
        self.trend_canvas.bind("<Motion>", self.on_canvas_hover)
        self.hover_tooltip = None
        self.trend_hover_data = {}

    def _create_tags_section(self, parent):
        """Create professional tags table section"""
        table_container = tk.Frame(parent, bg=COLORS['bg_dark'])
        table_container.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True)
        
        # Header
        header = tk.Frame(table_container, bg=COLORS['bg_dark'])
        header.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(
            header, text="🏷 Live Tag Values",
            font=self.font_title, fg=COLORS['text_primary'], bg=COLORS['bg_dark']
        ).pack(side=tk.LEFT)
        
        # Search
        search_frame = tk.Frame(header, bg=COLORS['bg_medium'])
        search_frame.pack(side=tk.RIGHT, padx=10)
        
        tk.Label(
            search_frame, text="🔍",
            font=("Segoe UI", 12), fg=COLORS['text_secondary'], bg=COLORS['bg_medium']
        ).pack(side=tk.LEFT, padx=5)
        
        search_entry = tk.Entry(
            search_frame, textvariable=self.tag_search_var,
            bg=COLORS['bg_light'], fg=COLORS['text_primary'],
            insertbackground=COLORS['accent_blue'],
            relief=tk.FLAT, font=self.font_mono, width=25
        )
        search_entry.pack(side=tk.LEFT, padx=5, ipady=5)
        
        # Buttons
        btn_frame = tk.Frame(header, bg=COLORS['bg_dark'])
        btn_frame.pack(side=tk.RIGHT, padx=10)
        
        self._create_modern_button(btn_frame, "Select All", self.select_all_tags, COLORS['accent_green'])
        self._create_modern_button(btn_frame, "Clear All", self.clear_all_tags, COLORS['accent_orange'])
        
        # Table
        self.tag_tree_container = tk.Frame(table_container, bg=COLORS['bg_medium'])
        self.tag_tree_container.pack(fill=tk.BOTH, expand=True)
        
        tree_frame = tk.Frame(self.tag_tree_container, bg=COLORS['bg_medium'])
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Style tree
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background=COLORS['bg_medium'],
            foreground=COLORS['text_primary'],
            fieldbackground=COLORS['bg_medium'],
            borderwidth=0,
            font=self.font_mono
        )
        style.configure("Treeview.Heading",
            background=COLORS['bg_light'],
            foreground=COLORS['accent_blue'],
            font=self.font_title
        )
        style.map("Treeview", background=[("selected", COLORS['accent_blue'])])
        
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("Select", "Tag", "Value", "Type", "Time"),
            show="tree headings",
            yscrollcommand=scrollbar.set,
            selectmode="browse"
        )
        
        self.tree.heading("#0", text="")
        self.tree.heading("Select", text="✓")
        self.tree.heading("Tag", text="Tag Name")
        self.tree.heading("Value", text="Value")
        self.tree.heading("Type", text="Type")
        self.tree.heading("Time", text="Last Update")
        
        self.tree.column("#0", width=0, stretch=tk.NO)
        self.tree.column("Select", width=50, anchor="center")
        self.tree.column("Tag", width=400, anchor="w")
        self.tree.column("Value", width=150, anchor="center")
        self.tree.column("Type", width=80, anchor="center")
        self.tree.column("Time", width=150, anchor="center")
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.tree.yview)
        
        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree_items = {}

    def _create_modern_button(self, parent, text, command, color):
        """Create modern flat button"""
        btn = tk.Button(
            parent, text=text, command=command,
            bg=COLORS['bg_medium'], fg=color,
            activebackground=COLORS['bg_light'],
            activeforeground=color,
            relief=tk.FLAT, font=("Segoe UI", 9, "bold"),
            cursor="hand2", padx=15, pady=5
        )
        btn.pack(side=tk.LEFT, padx=3)
        return btn

    # ========== EVENT HANDLERS ==========
    def on_scan_interval_changed(self, event=None):
        try:
            selected = self.scan_interval_var.get()
            ms_value = int(selected.replace('ms', ''))
            self.scan_interval = ms_value / 1000.0
            self.log("INFO", f"⚙ Scan interval: {ms_value}ms")
        except ValueError as e:
            self.log("ERROR", f"Invalid scan interval: {e}")

    def on_db_toggle(self):
        self.db_enabled = self.db_toggle_var.get()
        status = "ENABLED" if self.db_enabled else "DISABLED"
        self.log("INFO", f"💾 Database logging {status}")

    def on_tree_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            if column == "#1":
                item = self.tree.identify_row(event.y)
                if item:
                    tag_name = self.tree.set(item, "Tag")
                    if tag_name in self.selected_tags_for_trend:
                        self.selected_tags_for_trend.remove(tag_name)
                        self.tree.set(item, "Select", "")
                    else:
                        self.selected_tags_for_trend.add(tag_name)
                        self.tree.set(item, "Select", "✓")
                    
                    self.stat_cards['selected'].config(text=str(len(self.selected_tags_for_trend)))

    def on_canvas_hover(self, event):
        """Tooltip on hover"""
        if self.hover_tooltip:
            if isinstance(self.hover_tooltip, list):
                for item in self.hover_tooltip:
                    self.trend_canvas.delete(item)
            else:
                self.trend_canvas.delete(self.hover_tooltip)
            self.hover_tooltip = None

    def select_all_tags(self):
        for item in self.tree.get_children():
            tag_name = self.tree.set(item, "Tag")
            self.selected_tags_for_trend.add(tag_name)
            self.tree.set(item, "Select", "✓")
        self.stat_cards['selected'].config(text=str(len(self.selected_tags_for_trend)))
        self.log("INFO", f"✓ All {len(self.selected_tags_for_trend)} tags selected")

    def clear_all_tags(self):
        for item in self.tree.get_children():
            self.tree.set(item, "Select", "")
        self.selected_tags_for_trend.clear()
        self.stat_cards['selected'].config(text="0")
        self.log("INFO", "✗ All selections cleared")

    def filter_tags(self):
        if self.headless:
            return
        search_text = self.tag_search_var.get().lower()
        if not search_text:
            for item in self.tree.get_children():
                self.tree.item(item, tags=())
            return
        for item in self.tree.get_children():
            tag_name = self.tree.item(item, "values")[1].lower()
            if search_text in tag_name:
                self.tree.item(item, tags=())
                self.tree.see(item)
            else:
                self.tree.item(item, tags=("hidden",))
        self.tree.tag_configure("hidden", foreground=COLORS['bg_dark'])

    def update_trend_display(self):
        """Update trends canvas"""
        if self.headless:
            return
        
        try:
            self.trend_canvas.delete("all")
            self.trend_hover_data = {}
            
            if len(self.selected_tags_for_trend) > 0:
                canvas_width = self.trend_canvas.winfo_width()
                canvas_height = self.trend_canvas.winfo_height()
                
                if canvas_width < 100:
                    self.root.after(300, self.update_trend_display)
                    return
                
                # Draw title
                self.trend_canvas.create_text(
                    20, 20,
                    text=f"📊 {len(self.selected_tags_for_trend)} Tags Selected",
                    fill=COLORS['accent_blue'],
                    font=self.font_title,
                    anchor="nw"
                )
                
                # Draw sparklines
                y_pos = 60
                sparkline_height = 80
                line_height = sparkline_height + 70
                
                # PLC Response Time first
                if '_PLC_ResponseTime' in self.trend_data and len(self.trend_data['_PLC_ResponseTime']) > 0:
                    self._draw_sparkline(
                        '_PLC_ResponseTime',
                        list(self.trend_data['_PLC_ResponseTime'])[-50:],
                        y_pos, canvas_width, sparkline_height,
                        COLORS['accent_orange'], "⚡ PLC Response Time"
                    )
                    y_pos += line_height
                
                # Selected tags
                colors = [COLORS['accent_green'], COLORS['accent_blue'], COLORS['accent_yellow'],
                         COLORS['accent_purple'], COLORS['accent_orange'], COLORS['error']]
                
                for idx, tag in enumerate(self.selected_tags_for_trend):
                    if tag in self.trend_data and len(self.trend_data[tag]) > 0:
                        color = colors[idx % len(colors)]
                        recent_values = list(self.trend_data[tag])[-50:]
                        self._draw_sparkline(
                            tag, recent_values, y_pos, canvas_width,
                            sparkline_height, color, tag
                        )
                        y_pos += line_height
            else:
                # No selection message
                canvas_width = self.trend_canvas.winfo_width()
                canvas_height = self.trend_canvas.winfo_height()
                self.trend_canvas.create_text(
                    canvas_width / 2, canvas_height / 2,
                    text="📊 Select tags from table below to visualize trends",
                    fill=COLORS['text_secondary'],
                    font=("Segoe UI", 12),
                    justify=tk.CENTER
                )
            
            self.root.after(300, self.update_trend_display)
        except Exception as e:
            print(f"[ERROR] Trend update: {e}")
            self.root.after(1000, self.update_trend_display)

    def _draw_sparkline(self, tag, values, y_pos, canvas_width, height, color, label):
        """Draw single sparkline"""
        # Label
        self.trend_canvas.create_text(
            20, y_pos,
            text=label,
            fill=color,
            font=("Segoe UI", 11, "bold"),
            anchor="nw"
        )
        
        y_pos += 25
        x_start = 20
        x_width = canvas_width - 250
        
        numeric_values = []
        for v in values:
            val = v[1]
            if isinstance(val, (int, float)):
                numeric_values.append(float(val))
            elif isinstance(val, bool):
                numeric_values.append(1.0 if val else 0.0)
        
        if len(numeric_values) >= 2:
            min_val = min(numeric_values)
            max_val = max(numeric_values)
            is_constant = (max_val == min_val)
            val_range = max_val - min_val if not is_constant else 1
            
            # Background
            self.trend_canvas.create_rectangle(
                x_start, y_pos,
                x_start + x_width, y_pos + height,
                outline=COLORS['border'],
                fill=COLORS['bg_light'],
                width=1
            )
            
            # Grid lines
            for i in range(5):
                grid_y = y_pos + (i * height / 4)
                self.trend_canvas.create_line(
                    x_start, grid_y,
                    x_start + x_width, grid_y,
                    fill=COLORS['border'],
                    width=1,
                    dash=(2, 4)
                )
            
            # Draw line
            if not is_constant:
                points = []
                for i, val in enumerate(numeric_values):
                    x = x_start + (i * x_width / max(len(numeric_values) - 1, 1))
                    normalized = (val - min_val) / val_range
                    y = y_pos + height - (normalized * height)
                    points.extend([x, y])
                
                if len(points) >= 4:
                    self.trend_canvas.create_line(
                        points, fill=color, width=3, smooth=True
                    )
            
            # Current value
            current_val = numeric_values[-1]
            self.trend_canvas.create_text(
                x_start + x_width + 15, y_pos + height/2,
                text=f"{current_val:.2f}",
                fill=color,
                font=("Consolas", 14, "bold"),
                anchor="w"
            )

    def update(self, tag, value, value_type):
        """Update tag in tree"""
        if self.headless:
            return
        
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            if isinstance(value, bool):
                display_value = "TRUE" if value else "FALSE"
            elif isinstance(value, float):
                display_value = f"{value:.3f}".rstrip('0').rstrip('.')
            else:
                display_value = str(value)
            
            if tag not in self.tree_items:
                item_id = self.tree.insert("", "end", values=("", tag, display_value, value_type, timestamp))
                self.tree_items[tag] = item_id
                self.stat_cards['tags'].config(text=str(len(self.tree_items)))
            else:
                item_id = self.tree_items[tag]
                self.tree.set(item_id, "Value", display_value)
                self.tree.set(item_id, "Time", timestamp)
            
            if isinstance(value, (int, float, bool)):
                numeric_value = float(value) if not isinstance(value, bool) else (1.0 if value else 0.0)
                self.trend_data[tag].append((datetime.now(), numeric_value))
        except Exception as e:
            self.log("ERROR", f"UI update error: {e}")

    def set_plc_status(self, connected):
        if self.headless:
            return
        try:
            if connected:
                self.plc_status_dot.itemconfig(self.plc_status_circle, fill=COLORS['success'])
                self.plc_status_label.config(text="PLC", fg=COLORS['success'])
            else:
                self.plc_status_dot.itemconfig(self.plc_status_circle, fill=COLORS['error'])
                self.plc_status_label.config(text="PLC", fg=COLORS['error'])
        except:
            pass

    def set_db_status(self, connected):
        if self.headless:
            return
        try:
            if connected:
                self.db_status_dot.itemconfig(self.db_status_circle, fill=COLORS['success'])
                self.db_status_label.config(text="DATABASE", fg=COLORS['success'])
            else:
                self.db_status_dot.itemconfig(self.db_status_circle, fill=COLORS['error'])
                self.db_status_label.config(text="DATABASE", fg=COLORS['error'])
        except:
            pass

    def update_plc_metrics_display(self):
        if self.headless or not hasattr(self, 'stat_cards'):
            return
        try:
            response_ms = self.plc_metrics.get('response_time_ms', 0)
            self.stat_cards['response_time'].config(text=f"{response_ms:.1f}ms")
        except:
            pass

    def log(self, level, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        self.log_queue.append((level, log_entry))
        if self.headless or level == "ERROR":
            print(log_entry)

    def increment_stat(self, stat_name):
        if stat_name in self.stats:
            self.stats[stat_name] += 1
        try:
            if stat_name in self.stat_cards:
                self.stat_cards[stat_name].config(text=str(self.stats[stat_name]))
        except:
            pass

    def update_uptime(self):
        if self.headless:
            return
        try:
            uptime = datetime.now() - self.stats['start_time']
            hours, remainder = divmod(int(uptime.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            self.stat_cards['uptime'].config(text=f"{hours:02d}:{minutes:02d}:{seconds:02d}")
            self.root.after(1000, self.update_uptime)
        except:
            pass

    def start(self):
        if self.headless:
            print("[HEADLESS MODE] Running...")
            try:
                while True:
                    time.sleep(60)
            except KeyboardInterrupt:
                print("\n[SHUTDOWN] Exiting...")
                sys.exit(0)
        else:
            self.root.mainloop()


ui = ProfessionalUI()


def db_writer_loop():
    """Database writer with smart filtering + 2-minute forced writes"""
    last_write_time = datetime.now(timezone.utc)
    write_interval = 1.0
    last_written_values = {}
    last_write_time_per_tag = {}
    forced_write_interval = FORCED_WRITE_INTERVAL
    
    while True:
        try:
            time.sleep(write_interval)
            current_time = datetime.now(timezone.utc)
            batch = tag_cache.get_batch(since_timestamp=last_write_time)
            
            if not batch or not ui.db_enabled:
                continue
            
            latest_dict = {}
            ts_rows = []
            filtered_count = 0
            forced_write_count = 0
            
            for tag_id, ts, value, quality in batch:
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
                
                # Smart filtering
                value_changed = True
                force_write = False
                
                if tag_id in last_written_values:
                    last_val = last_written_values[tag_id]
                    if isinstance(value, bool):
                        value_changed = (value != last_val)
                    elif isinstance(value, (int, float)):
                        value_changed = (value != last_val)
                    elif isinstance(value, str):
                        value_changed = (value != last_val)
                
                if tag_id in last_write_time_per_tag:
                    time_since_last_write = (current_time - last_write_time_per_tag[tag_id]).total_seconds()
                    if time_since_last_write >= forced_write_interval:
                        force_write = True
                        forced_write_count += 1
                
                if not value_changed and not force_write:
                    filtered_count += 1
                    continue
                
                last_written_values[tag_id] = value
                last_write_time_per_tag[tag_id] = current_time
                
                if tag_id not in latest_dict or ts > latest_dict[tag_id][1]:
                    latest_dict[tag_id] = (tag_id, ts, num, text, boolean, quality)
                
                ts_rows.append((ts, tag_id, num, text, boolean, quality, 'P'))
            
            latest_rows = list(latest_dict.values())
            
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
                    last_write_time = current_time
                    
                    if filtered_count > 0:
                        ui.stats['filtered'] += filtered_count
                        if not ui.headless:
                            ui.stat_cards['filtered'].config(text=str(ui.stats['filtered']))
                    
                    total_samples = len(batch)
                    if forced_write_count > 0:
                        ui.log("INFO", f"💾 DB: {len(ts_rows)} total ({len(ts_rows)-forced_write_count} changed, {forced_write_count} forced), {filtered_count} skipped")
                    else:
                        ui.log("INFO", f"💾 DB: {len(ts_rows)} changed, {filtered_count} skipped")
                    
                    cleanup_time = current_time - timedelta(seconds=10)
                    tag_cache.clear_old(cleanup_time)
                else:
                    ui.set_db_status(False)
                    ui.log("ERROR", f"❌ DB write failed")
        
        except Exception as e:
            ui.log("ERROR", f"❌ DB writer error: {e}")
            import traceback
            print(f"[DB EXCEPTION] {traceback.format_exc()}")
            time.sleep(1)


def plc_loop():
    """PLC scanning loop"""
    retry_count = 0
    max_retries = 5
    
    while retry_count < max_retries:
        try:
            ui.log("INFO", f"🔌 Connecting to PLC at {PLC_IP}...")
            
            with LogixDriver(PLC_PATH) as plc:
                ui.set_plc_status(True)
                ui.log("INFO", f"✓ PLC connected: {PLC_IP}")
                
                tags = plc.get_tag_list()
                tag_names = []

                for tag in tags:
                    name = getattr(tag, "tag_name", None) or tag.get("tag_name")
                    if not name:
                        continue
                    if getattr(tag, "array_dims", None) or getattr(tag, "structured", None):
                        continue
                    tag_names.append(name)

                ui.log("INFO", f"📊 Monitoring {len(tag_names)} tags")
                
                retry_count = 0
                scan_count = 0
                last_log_time = 0

                while True:
                    scan_count += 1
                    scan_start = time.time()
                    
                    read_start = time.time()
                    results = plc.read(*tag_names)
                    response_ms = (time.time() - read_start) * 1000
                    
                    ui.plc_metrics['response_time_ms'] = response_ms
                    ui.trend_data['_PLC_ResponseTime'].append((datetime.now(), response_ms))
                    
                    ts_utc = datetime.now(timezone.utc)
                    value_count = 0

                    for tag, res in zip(tag_names, results):
                        if res.error or res.value is None:
                            continue

                        val = res.value
                        quality = 'G'
                        
                        if isinstance(val, bool):
                            raw_value = val
                            value_type = "BOOL"
                        elif isinstance(val, (int, float)):
                            raw_value = float(val)
                            value_type = "REAL" if isinstance(val, float) else "INT"
                        elif isinstance(val, str):
                            raw_value = val
                            value_type = "STRING"
                        else:
                            continue
                        
                        tag_cache.put(tag, ts_utc, raw_value, quality)
                        
                        if scan_count % 10 == 0 or ui.scan_interval >= 0.1:
                            ui.update(tag, raw_value, value_type)
                        
                        value_count += 1

                    if value_count > 0:
                        ui.increment_stat('plc_reads')
                        ui.update_plc_metrics_display()
                        
                        current_time = time.time()
                        if current_time - last_log_time >= 5.0:
                            cache_stats = tag_cache.get_stats()
                            ui.log("INFO", f"⚡ Scan: {scan_count} | Tags: {value_count} | Response: {response_ms:.1f}ms")
                            last_log_time = current_time
                    
                    scan_duration = time.time() - scan_start
                    sleep_time = max(0.001, ui.scan_interval - scan_duration)
                    time.sleep(sleep_time)

        except Exception as e:
            retry_count += 1
            ui.log("ERROR", f"❌ PLC error (Retry {retry_count}/{max_retries}): {e}")
            ui.set_plc_status(False)
            
            if retry_count < max_retries:
                time.sleep(5)
            else:
                break
    
    ui.log("ERROR", "❌ Max retries reached - stopped")
    ui.set_plc_status(False)


if __name__ == "__main__":
    print("=" * 80)
    print("  🏭 Professional PLC Scanner - Enterprise Edition")
    print("  Real-time Industrial Data Acquisition & Monitoring")
    print("  Features: Smart Filtering • Live Trends • Database Logging")
    print("=" * 80)
    
    if not HEADLESS_MODE:
        ui.log("INFO", "=" * 60)
        ui.log("INFO", "🚀 System Starting - Professional Edition")
        ui.log("INFO", f"🔌 PLC Target: {PLC_IP}")
        ui.log("INFO", f"💾 Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}")
        ui.log("INFO", f"⏱ Scan Interval: {DEFAULT_SCAN_INTERVAL}s")
        ui.log("INFO", f"🔄 Forced Write: Every {int(FORCED_WRITE_INTERVAL/60)} minutes")
        ui.log("INFO", "=" * 60)
    
    plc_thread = threading.Thread(target=plc_loop, daemon=True, name="PLCScanner")
    plc_thread.start()
    
    db_thread = threading.Thread(target=db_writer_loop, daemon=True, name="DBWriter")
    db_thread.start()
    
    time.sleep(0.5)
    ui.log("INFO", "✓ All systems operational")
    
    ui.start()
