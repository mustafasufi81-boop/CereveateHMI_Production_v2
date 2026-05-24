#!/usr/bin/env python3
"""
Simple PLC Tag Scanner - Based on Working Code
Author: Cereveate Tech | Shahnawaz Mustafa
"""

import os
import sys
import time
import threading
from datetime import datetime, timezone
from pathlib import Path

# ================= DISPLAY ENVIRONMENT SETUP =================
if 'DISPLAY' not in os.environ:
    os.environ['DISPLAY'] = ':0'
    print("[SETUP] DISPLAY not set, attempting to use :0")

if 'THONNY_USER_DIR' in os.environ:
    print("[WARNING] Thonny detected - run directly: python3 plc_scanner_simple.py")
    
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
    import tkinter as tk
# ============================================================

from pycomm3 import LogixDriver
from tkinter import ttk, scrolledtext
from collections import deque
import psycopg2
from psycopg2.extras import execute_values
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

# ================= CONFIG =================
PLC_IP = "192.168.0.20"
PLC_PATH = f"{PLC_IP}/1,0"
SCAN_INTERVAL = 1.0  # seconds (configurable via UI)

# Database Config
DB_CONFIG = {
    'host': '192.168.0.120',
    'port': 5432,
    'database': 'Cereveate',
    'user': 'cereveate',
    'password': 'cereveate@222',
    'sslmode': 'disable'
}
DB_ENABLED = True  # Enable/disable database logging
# ==========================================

class SimpleUI:
    def __init__(self):
        self.headless = HEADLESS_MODE
        self.stats = {
            'plc_reads': 0,
            'errors': 0,
            'start_time': datetime.now()
        }
        self.log_queue = deque(maxlen=500)
        
        if self.headless:
            print("[HEADLESS] Running without GUI - console logging only")
            self.root = None
            return
            
        try:
            self.root = tk.Tk()
            self.root.title("PLC Tag Scanner")
            self.root.geometry("1400x800")
            self.root.configure(bg="#0D1117")
            self._build_gui()
        except Exception as e:
            print(f"[ERROR] Failed to create GUI: {e}")
            print("[FALLBACK] Switching to headless mode")
            self.headless = True
            self.root = None
    
    def _build_gui(self):
        # Header
        header_frame = tk.Frame(self.root, bg="#161B22", height=80)
        header_frame.pack(fill=tk.X, padx=0, pady=0)
        header_frame.pack_propagate(False)

        tk.Label(
            header_frame,
            text="PLC Tag Scanner",
            font=("Segoe UI", 22, "bold"),
            fg="#58A6FF",
            bg="#161B22"
        ).pack(side=tk.LEFT, padx=20, pady=15)

        # Connection Status
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

        # Stats Bar
        stats_frame = tk.Frame(self.root, bg="#0D1117", height=60)
        stats_frame.pack(fill=tk.X, padx=10, pady=(5, 0))
        stats_frame.pack_propagate(False)

        self.stat_labels = {}
        stat_items = [
            ("Tags", "tags", "0"),
            ("PLC Reads", "plc_reads", "0"),
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

        # Main Content Area
        main_container = tk.Frame(self.root, bg="#0D1117")
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # LEFT: Tag Values
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

        tree_scrollbar = ttk.Scrollbar(tree_frame)
        tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

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

        # RIGHT: Log Viewer
        right_frame = tk.Frame(main_container, bg="#0D1117")
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))

        tk.Label(
            right_frame,
            text="System Log",
            font=("Segoe UI", 12, "bold"),
            fg="#C9D1D9",
            bg="#0D1117",
            anchor="w"
        ).pack(fill=tk.X, pady=(0, 5))

        log_container = tk.Frame(right_frame, bg="#161B22", relief=tk.RIDGE, bd=1)
        log_container.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(
            log_container,
            bg="#0D1117",
            fg="#C9D1D9",
            font=("Consolas", 9),
            wrap=tk.WORD,
            relief=tk.FLAT,
            state=tk.DISABLED
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        self.log_text.tag_config("INFO", foreground="#58A6FF")
        self.log_text.tag_config("SUCCESS", foreground="#3FB950")
        self.log_text.tag_config("WARNING", foreground="#D29922")
        self.log_text.tag_config("ERROR", foreground="#F85149")
        self.log_text.tag_config("TIMESTAMP", foreground="#8B949E")

        self.update_uptime()
        self.log("INFO", "System initialized successfully")

    def update(self, tag, value, value_type):
        if self.headless:
            if len(self.stats.get('_tag_cache', {})) < 50:
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
        except:
            pass

    def set_plc_status(self, connected):
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

    def log(self, level, message):
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

    def increment_stat(self, stat_name):
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
                              f"Errors: {self.stats['errors']}")
            except KeyboardInterrupt:
                print("\n[SHUTDOWN] Shutting down gracefully...")
                sys.exit(0)
        else:
            self.root.mainloop()


ui = SimpleUI()


def plc_loop():
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
                
                retry_count = 0
                scan_count = 0

                while True:
                    scan_count += 1
                    results = plc.read(*tag_names)

                    value_count = 0
                    for tag, res in zip(tag_names, results):
                        if res.error:
                            continue

                        val = res.value
                        
                        if val is None:
                            continue

                        value_type = ""
                        
                        # Check boolean FIRST (before numeric check)
                        if isinstance(val, bool):
                            display = "TRUE" if val else "FALSE"
                            value_type = "BOOL"
                        elif isinstance(val, (int, float)):
                            num = float(val)
                            
                            # Filter garbage/noise
                            if abs(num) < 1e-10:
                                num = 0.0
                            
                            # Format display
                            if num == 0:
                                display = "0"
                            elif abs(num) < 0.001:
                                display = f"{num:.6f}".rstrip('0').rstrip('.')
                            elif abs(num) < 1:
                                display = f"{num:.4f}".rstrip('0').rstrip('.')
                            elif abs(num) > 1e9:
                                display = f"{num:.2e}"
                            else:
                                display = f"{num:.2f}".rstrip('0').rstrip('.')
                            value_type = "REAL" if isinstance(val, float) else "INT"
                        elif isinstance(val, str):
                            display = val
                            value_type = "STRING"
                        else:
                            continue

                        ui.update(tag, display, value_type)
                        value_count += 1

                    if value_count > 0:
                        ui.increment_stat('plc_reads')
                        
                        if scan_count % 10 == 0:
                            ui.log("INFO", f"PLC Scan #{scan_count}: Read {value_count} tag values")

                    time.sleep(SCAN_INTERVAL)

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
    print("  PLC Tag Scanner - Simple & Reliable")
    print("  PLC: Allen-Bradley ControlLogix")
    print("=" * 70)
    
    if not HEADLESS_MODE:
        ui.log("INFO", "=" * 60)
        ui.log("INFO", "System Starting - PLC Tag Scanner")
        ui.log("INFO", f"PLC Target: {PLC_IP}")
        ui.log("INFO", f"Scan Interval: {SCAN_INTERVAL}s")
        ui.log("INFO", "=" * 60)
    
    # Start PLC thread BEFORE starting UI
    plc_thread = threading.Thread(target=plc_loop, daemon=True)
    plc_thread.start()
    
    # Give thread time to start
    time.sleep(0.5)
    
    # Start UI (blocks here)
    ui.start()
