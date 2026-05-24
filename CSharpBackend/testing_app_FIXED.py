#!/usr/bin/env python3
# ControlLogix → Live UI → PostgreSQL Historian (Schema-Correct)
# Author: Cereveate Tech | Shahnawaz Mustafa

import os
import sys

# ================= DISPLAY ENVIRONMENT SETUP =================
# Fix for Thonny IDE and headless environments
if 'DISPLAY' not in os.environ:
    # Try to set default display for GUI
    os.environ['DISPLAY'] = ':0'
    print("[SETUP] DISPLAY not set, attempting to use :0")

# Prevent Thonny from interfering with tkinter
if 'THONNY_USER_DIR' in os.environ:
    print("[WARNING] Thonny detected - GUI may not work properly")
    print("[WARNING] Please run directly: python3 testing_app_FIXED.py")
    
# Test display availability
try:
    import tkinter as tk
    test_root = tk.Tk()
    test_root.withdraw()
    test_root.destroy()
    print("[OK] Display available - GUI mode enabled")
    HEADLESS_MODE = False
except Exception as e:
    print(f"[WARNING] Display test failed: {e}")
    print("[INFO] Running in HEADLESS mode (console logging only)")
    HEADLESS_MODE = True
    # Still import tkinter for compatibility but won't create windows
    import tkinter as tk
# ============================================================

from pycomm3 import LogixDriver
import time, threading
from tkinter import ttk, scrolledtext
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timezone
from collections import deque
import csv
import gzip
from pathlib import Path

# ================= PLC CONFIG =================
PLC_IP = "192.168.0.20"
PLC_PATH = f"{PLC_IP}/1,0"
SCAN_INTERVAL = 1.0
# =============================================

# ================= DB CONFIG ==================
DB_CONFIG = {
    'host': '192.168.0.120',
    'port': 5432,
    'database': 'Cereveate',
    'user': 'cereveate',
    'password': 'cereveate@222',
    'sslmode': 'disable'
}
# =============================================

# ================= CSV LOGGING CONFIG =================
CSV_LOG_DIR = "/home/cereveate/login"  # Raspberry Pi logging directory
IST_OFFSET = 19800  # Indian Standard Time offset (UTC+5:30 in seconds)
csv_buffer = []  # Buffer for CSV data
current_csv_file = None
current_date = None
csv_lock = threading.Lock()
# =======================================================


# ---------- CSV LOGGING (GZIP COMPRESSED) ----------
def get_ist_time():
    """Get Indian Standard Time (UTC+5:30) without pytz dependency"""
    from datetime import timedelta
    utc_now = datetime.now(timezone.utc)
    ist_now = utc_now + timedelta(seconds=IST_OFFSET)
    return ist_now

def get_csv_filename():
    """Generate CSV filename with format: ddMMyyHHmmss.csv.gz"""
    now = get_ist_time()
    return now.strftime("%d%m%y%H%M%S") + ".csv.gz"

def write_csv_buffer():
    """Write buffered data to compressed CSV file"""
    global csv_buffer, current_csv_file, current_date
    
    if not csv_buffer:
        return
    
    with csv_lock:
        try:
            # Create directory if it doesn't exist
            Path(CSV_LOG_DIR).mkdir(parents=True, exist_ok=True)
            
            # Check if date changed - create new file
            now_date = get_ist_time().date()
            if current_date != now_date:
                current_date = now_date
                current_csv_file = os.path.join(CSV_LOG_DIR, get_csv_filename())
                print(f"[CSV] New file: {os.path.basename(current_csv_file)}")
                
                # Write header to new file
                with gzip.open(current_csv_file, 'wt', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Timestamp', 'TagId', 'Value', 'Quality', 'Type'])
            
            # Append data to compressed CSV
            with gzip.open(current_csv_file, 'at', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                for row in csv_buffer:
                    timestamp_ist, tag_id, value, quality, value_type = row
                    # Format timestamp as ISO string
                    ts_str = timestamp_ist.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]  # Milliseconds
                    writer.writerow([ts_str, tag_id, value, quality, value_type])
            
            print(f"[CSV] Wrote {len(csv_buffer)} records (compressed)")
            csv_buffer.clear()
            
        except Exception as e:
            print(f"[ERROR] CSV write failed: {e}")

# ---------- DATABASE ----------
def connect_db():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False
        return conn
    except Exception as e:
        print("[ERROR] DB connection failed:", e)
        return None


def insert_latest_values(rows):
    """
    rows = [(tag_id, ts, num, text, boolean, quality), ...]
    Schema: tag_id, last_time, last_value_num, last_value_text, last_value_bool, last_quality
    """
    if not rows:
        return

    conn = connect_db()
    if not conn:
        ui.set_db_status(False)
        ui.log("ERROR", "Database connection failed")
        return

    try:
        ui.set_db_status(True)
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
        # Add updated_at timestamp
        rows_with_updated = [(r[0], r[1], r[2], r[3], r[4], r[5], datetime.now(timezone.utc)) for r in rows]
        execute_values(cur, query, rows_with_updated)
        conn.commit()
        cur.close()
        conn.close()
        ui.increment_stat('db_writes')
        ui.log("SUCCESS", f"Database: Wrote {len(rows)} tag values")
    except Exception as e:
        ui.log("ERROR", f"Latest-value insert error: {e}")
        if conn:
            conn.rollback()
            conn.close()


def insert_timeseries(rows):
    """
    rows = [(ts, tag_id, num, text, boolean, quality, source), ...]
    Schema: time, tag_id, value_num, value_text, value_bool, quality, sample_source
    """
    if not rows:
        return

    conn = connect_db()
    if not conn:
        ui.set_db_status(False)
        ui.log("ERROR", "Database connection failed")
        return

    try:
        ui.set_db_status(True)
        cur = conn.cursor()
        query = """
            INSERT INTO historian_raw.historian_timeseries
            (time, tag_id, value_num, value_text, value_bool, quality, sample_source)
            VALUES %s
        """
        execute_values(cur, query, rows)
        conn.commit()
        cur.close()
        conn.close()
        ui.increment_stat('db_writes')
    except Exception as e:
        ui.log("ERROR", f"Timeseries insert error: {e}")
        if conn:
            conn.rollback()
            conn.close()


# ---------- UI ----------
class ProUI:
    def __init__(self):
        self.headless = HEADLESS_MODE
        
        # Initialize stats regardless of mode
        self.stats = {
            'plc_reads': 0,
            'db_writes': 0,
            'errors': 0,
            'start_time': datetime.now()
        }
        self.log_queue = deque(maxlen=500)
        
        # Only create GUI if display is available
        if self.headless:
            print("[HEADLESS] Running without GUI - console logging only")
            self.root = None
            return
            
        try:
            self.root = tk.Tk()
            self.root.title("ControlLogix Live Monitor - Cereveate")
            self.root.geometry("1400x800")
            self.root.configure(bg="#0D1117")
            self._build_gui()
        except Exception as e:
            print(f"[ERROR] Failed to create GUI: {e}")
            print("[FALLBACK] Switching to headless mode")
            self.headless = True
            self.root = None
    
    def _build_gui(self):
        """Build GUI components - only called if display available"""

        # ========== TOP HEADER ==========
        header_frame = tk.Frame(self.root, bg="#161B22", height=80)
        header_frame.pack(fill=tk.X, padx=0, pady=0)
        header_frame.pack_propagate(False)

        tk.Label(
            header_frame,
            text="ControlLogix Live Monitor",
            font=("Segoe UI", 22, "bold"),
            fg="#58A6FF",
            bg="#161B22"
        ).pack(side=tk.LEFT, padx=20, pady=15)

        # Connection Status Indicator
        self.connection_frame = tk.Frame(header_frame, bg="#161B22")
        self.connection_frame.pack(side=tk.RIGHT, padx=20)

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

        # ========== STATS BAR ==========
        stats_frame = tk.Frame(self.root, bg="#0D1117", height=60)
        stats_frame.pack(fill=tk.X, padx=10, pady=(5, 0))
        stats_frame.pack_propagate(False)

        self.stat_labels = {}
        stat_items = [
            ("Tags", "tags", "0"),
            ("PLC Reads", "plc_reads", "0"),
            ("DB Writes", "db_writes", "0"),
            ("Errors", "errors", "0"),
            ("Uptime", "uptime", "00:00:00")
        ]

        for label_text, key, default_value in stat_items:
            stat_box = tk.Frame(stats_frame, bg="#161B22", relief=tk.RIDGE, bd=1)
            stat_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

            tk.Label(
                stat_box,
                text=label_text,
                font=("Segoe UI", 9),
                fg="#8B949E",
                bg="#161B22"
            ).pack(pady=(5, 0))

            self.stat_labels[key] = tk.Label(
                stat_box,
                text=default_value,
                font=("Segoe UI", 16, "bold"),
                fg="#58A6FF" if key != "errors" else "#F85149",
                bg="#161B22"
            )
            self.stat_labels[key].pack(pady=(0, 5))

        # ========== MAIN CONTENT AREA ==========
        main_container = tk.Frame(self.root, bg="#0D1117")
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # LEFT: Tag Values (60%)
        left_frame = tk.Frame(main_container, bg="#0D1117")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        tk.Label(
            left_frame,
            text="Live Tag Values",
            font=("Segoe UI", 12, "bold"),
            fg="#C9D1D9",
            bg="#0D1117",
            anchor="w"
        ).pack(fill=tk.X, pady=(0, 5))

        tree_frame = tk.Frame(left_frame, bg="#161B22", relief=tk.RIDGE, bd=1)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        # Scrollbar for tree
        tree_scrollbar = ttk.Scrollbar(tree_frame)
        tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Configure treeview style
        style = ttk.Style()
        style.theme_use("clam")
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

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("Tag", "Value", "Type", "Time"),
            show="headings",
            yscrollcommand=tree_scrollbar.set,
            selectmode="browse"
        )
        self.tree.heading("Tag", text="Tag Name")
        self.tree.heading("Value", text="Value")
        self.tree.heading("Type", text="Type")
        self.tree.heading("Time", text="Last Update")
        
        self.tree.column("Tag", width=400, anchor="w")
        self.tree.column("Value", width=150, anchor="center")
        self.tree.column("Type", width=80, anchor="center")
        self.tree.column("Time", width=150, anchor="center")
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scrollbar.config(command=self.tree.yview)

        self.tree_items = {}

        # RIGHT: Log Viewer (40%)
        right_frame = tk.Frame(main_container, bg="#0D1117")
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))

        # Log header with clear button
        log_header = tk.Frame(right_frame, bg="#0D1117")
        log_header.pack(fill=tk.X, pady=(0, 5))

        tk.Label(
            log_header,
            text="System Log",
            font=("Segoe UI", 12, "bold"),
            fg="#C9D1D9",
            bg="#0D1117",
            anchor="w"
        ).pack(side=tk.LEFT)

        clear_btn = tk.Button(
            log_header,
            text="Clear Log",
            command=self.clear_log,
            bg="#21262D",
            fg="#C9D1D9",
            activebackground="#30363D",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 9),
            cursor="hand2",
            padx=10,
            pady=2
        )
        clear_btn.pack(side=tk.RIGHT)

        log_container = tk.Frame(right_frame, bg="#161B22", relief=tk.RIDGE, bd=1)
        log_container.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(
            log_container,
            bg="#0D1117",
            fg="#C9D1D9",
            font=("Consolas", 9),
            wrap=tk.WORD,
            relief=tk.FLAT,
            state=tk.DISABLED,
            cursor="arrow"
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # Configure log text tags for colors
        self.log_text.tag_config("INFO", foreground="#58A6FF")
        self.log_text.tag_config("SUCCESS", foreground="#3FB950")
        self.log_text.tag_config("WARNING", foreground="#D29922")
        self.log_text.tag_config("ERROR", foreground="#F85149")
        self.log_text.tag_config("TIMESTAMP", foreground="#8B949E")

        # ========== BOTTOM STATUS BAR ==========
        bottom_frame = tk.Frame(self.root, bg="#161B22", height=35)
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM)
        bottom_frame.pack_propagate(False)

        self.status_label = tk.Label(
            bottom_frame,
            text="Initializing system...",
            font=("Segoe UI", 10),
            fg="#8B949E",
            bg="#161B22",
            anchor="w"
        )
        self.status_label.pack(side=tk.LEFT, padx=15, fill=tk.X, expand=True)

        # Start uptime counter
        self.update_uptime()
        self.log("INFO", "System initialized successfully")

    def update(self, tag, value, value_type):
        """Update tag value in treeview"""
        if self.headless:
            # Console output for headless mode
            if len(self.stats.get('_tag_cache', {})) < 50:  # Limit console spam
                print(f"[TAG] {tag} = {value} ({value_type})")
            if '_tag_cache' not in self.stats:
                self.stats['_tag_cache'] = {}
            self.stats['_tag_cache'][tag] = True
            return
            
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            if tag not in self.tree_items:
                self.tree.insert("", "end", iid=tag, values=(tag, value, value_type, timestamp))
                self.tree_items[tag] = True
                self.stat_labels['tags'].config(text=str(len(self.tree_items)))
            else:
                self.tree.set(tag, "Value", value)
                self.tree.set(tag, "Time", timestamp)
        except Exception as e:
            self.log("ERROR", f"UI update error for tag {tag}: {e}")

    def update_status(self, msg, level="INFO"):
        """Update bottom status bar"""
        if self.headless:
            print(f"[STATUS:{level}] {msg}")
            return
            
        try:
            colors = {
                "INFO": "#58A6FF",
                "SUCCESS": "#3FB950",
                "WARNING": "#D29922",
                "ERROR": "#F85149"
            }
            icons = {
                "INFO": "[INFO]",
                "SUCCESS": "[OK]",
                "WARNING": "[WARN]",
                "ERROR": "[ERR]"
            }
            icon = icons.get(level, "[INFO]")
            color = colors.get(level, "#8B949E")
            self.status_label.config(text=f"{icon} {msg}", fg=color)
        except:
            pass

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
                self.log("SUCCESS", f"PLC connected: {PLC_IP}")
            else:
                self.plc_status_dot.itemconfig(self.plc_status_circle, fill="#F85149")
                self.plc_status_label.config(text="PLC: Disconnected", fg="#F85149")
                self.log("ERROR", "PLC connection lost")
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
                self.db_status_dot.itemconfig(self.db_status_circle, fill="#F85149")
                self.db_status_label.config(text="DB: Disconnected", fg="#F85149")
        except:
            pass

    def log(self, level, message):
        """Add message to log viewer"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        
        # Always maintain log queue for statistics
        self.log_queue.append((level, log_entry))
        
        # Console output for headless mode
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

            # Update error count
            if level == "ERROR":
                self.stats['errors'] += 1
                self.stat_labels['errors'].config(text=str(self.stats['errors']))
        except:
            print(log_entry)  # Fallback to console

    def clear_log(self):
        """Clear log viewer"""
        if self.headless:
            print("[SYSTEM] Log cleared (headless mode)")
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
            if self.headless:
                # Print statistics summary periodically (every 100 operations)
                if self.stats[stat_name] % 100 == 0:
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
            # Keep main thread alive for daemon threads
            try:
                while True:
                    time.sleep(1)
                    # Print uptime periodically
                    uptime = datetime.now() - self.stats['start_time']
                    if int(uptime.total_seconds()) % 60 == 0:  # Every minute
                        print(f"[UPTIME] {int(uptime.total_seconds() / 60)} minutes | "
                              f"PLC Reads: {self.stats['plc_reads']} | "
                              f"DB Writes: {self.stats['db_writes']} | "
                              f"Errors: {self.stats['errors']}")
            except KeyboardInterrupt:
                print("\n[SHUTDOWN] Shutting down gracefully...")
                sys.exit(0)
        else:
            self.root.mainloop()


ui = ProUI()


# ---------- PLC LOOP ----------
def plc_loop():
    retry_count = 0
    max_retries = 5
    
    while retry_count < max_retries:
        try:
            ui.update_status(f"Connecting to PLC at {PLC_IP}...", "INFO")
            ui.log("INFO", f"Attempting PLC connection to {PLC_IP} (Attempt {retry_count + 1}/{max_retries})")
            
            with LogixDriver(PLC_PATH) as plc:
                ui.set_plc_status(True)
                ui.update_status(f"Connected! Reading tags from {PLC_IP}", "SUCCESS")
                
                tags = plc.get_tag_list()
                tag_names = []

                for tag in tags:
                    name = getattr(tag, "tag_name", None) or tag.get("tag_name")
                    if not name:
                        continue
                    if getattr(tag, "array_dims", None) or getattr(tag, "structured", None):
                        continue
                    tag_names.append(name)

                ui.update_status(f"Monitoring {len(tag_names)} tags", "SUCCESS")
                ui.log("SUCCESS", f"Started monitoring {len(tag_names)} tags from PLC")
                
                # Reset retry count on successful connection
                retry_count = 0
                scan_count = 0

                while True:
                    scan_count += 1
                    results = plc.read(*tag_names)
                    ts_utc = datetime.now(timezone.utc)
                    ts_ist = get_ist_time()  # Indian Standard Time for CSV

                    latest_rows = []
                    ts_rows = []
                    value_count = 0

                    for tag, res in zip(tag_names, results):
                        if res.error:
                            continue

                        val = res.value
                        
                        # Skip None/null values
                        if val is None:
                            continue

                        # Initialize all as None
                        num = text = boolean = None
                        quality = 'G'
                        source = 'P'   # PLC
                        value_type = ""

                        # Check for boolean FIRST (before numeric check)
                        # In Python, bool is subclass of int, so check bool first!
                        if isinstance(val, bool):
                            boolean = val
                            # Convert to 1/0 for numeric storage as well (compatibility)
                            num = 1.0 if val else 0.0
                            display = "TRUE" if val else "FALSE"
                            value_type = "BOOL"
                        elif isinstance(val, (int, float)):
                            num = float(val)
                            
                            # Filter out garbage/noise - values smaller than 1e-10 are treated as zero
                            # PLC sensors/actuators don't produce values like 4e-43
                            if abs(num) < 1e-10:
                                num = 0.0
                            
                            # Format display based on cleaned value
                            if num == 0:
                                display = "0"
                            elif abs(num) < 0.001:
                                # Very small but valid decimals (0.001 to 0.000000001)
                                display = f"{num:.6f}".rstrip('0').rstrip('.')
                            elif abs(num) < 1:
                                # Small decimals - show 4 decimal places
                                display = f"{num:.4f}".rstrip('0').rstrip('.')
                            elif abs(num) > 1e9:
                                # Very large numbers - use scientific notation
                                display = f"{num:.2e}"
                            else:
                                # Normal range - round to 2 decimals for cleaner display
                                display = f"{num:.2f}".rstrip('0').rstrip('.')
                            value_type = "REAL" if isinstance(val, float) else "INT"
                        elif isinstance(val, str):
                            text = val
                            display = val
                            value_type = "STRING"
                        else:
                            continue   # ignore non-scalar

                        ui.update(tag, display, value_type)
                        value_count += 1

                        # Add to database rows (UTC timestamp)
                        latest_rows.append(
                            (tag, ts_utc, num, text, boolean, quality)
                        )

                        ts_rows.append(
                            (ts_utc, tag, num, text, boolean, quality, source)
                        )
                        
                        # Add to CSV buffer (IST timestamp)
                        # Store the numeric value (convert boolean to 1/0)
                        csv_value = num if num is not None else (1.0 if boolean else 0.0 if boolean is not None else 0.0)
                        csv_buffer.append((ts_ist, tag, csv_value, quality, value_type))

                    # Insert to database
                    if latest_rows:
                        insert_latest_values(latest_rows)
                        insert_timeseries(ts_rows)
                        ui.increment_stat('plc_reads')
                        
                        # Write CSV every 10 scans or when buffer > 100 records
                        if scan_count % 10 == 0 or len(csv_buffer) > 100:
                            write_csv_buffer()
                        
                        # Log every 10 scans to show system is active
                        if scan_count % 10 == 0:
                            ui.log("INFO", f"PLC Scan #{scan_count}: Read {value_count} tag values")

                    time.sleep(SCAN_INTERVAL)

        except Exception as e:
            retry_count += 1
            error_msg = f"PLC connection error (Retry {retry_count}/{max_retries}): {str(e)}"
            ui.log("ERROR", error_msg)
            ui.update_status(error_msg, "ERROR")
            ui.set_plc_status(False)
            
            if retry_count < max_retries:
                time.sleep(5)
            else:
                break
    
    ui.update_status("Max retries reached. Please restart application.", "ERROR")
    ui.log("ERROR", "Max PLC connection retries reached - system stopped")
    ui.set_plc_status(False)


# ---------- MAIN ----------
if __name__ == "__main__":
    # Initialize CSV logging directory
    try:
        Path(CSV_LOG_DIR).mkdir(parents=True, exist_ok=True)
        current_date = get_ist_time().date()
        current_csv_file = os.path.join(CSV_LOG_DIR, get_csv_filename())
        print(f"[CSV] Logging to: {current_csv_file}")
    except Exception as e:
        print(f"[WARNING] CSV directory creation failed: {e}")
    
    print("=" * 70)
    print("  ControlLogix Live Monitor - Cereveate Tech")
    print("  Database: PostgreSQL Historian + CSV Logging (GZIP)")
    print("  PLC: Allen-Bradley ControlLogix")
    print("  Timezone: India Standard Time (IST)")
    print("=" * 70)
    ui.log("INFO", "=" * 60)
    ui.log("INFO", "System Starting - ControlLogix Live Monitor v2.0")
    ui.log("INFO", f"PLC Target: {PLC_IP}")
    ui.log("INFO", f"Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    ui.log("INFO", f"CSV Logging: {CSV_LOG_DIR} (GZIP compressed, IST timezone)")
    ui.log("INFO", f"Scan Interval: {SCAN_INTERVAL}s")
    ui.log("INFO", "=" * 60)
    
    threading.Thread(target=plc_loop, daemon=True).start()
    ui.start()
