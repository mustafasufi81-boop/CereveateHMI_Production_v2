#!/usr/bin/env python3
"""
Standalone PLC Tag Scanner with Multi-Rate Scanning
Works on Linux/Windows - Completely independent from main OPC system
All configuration embedded - NO external files needed
Author: Cereveate Tech | Shahnawaz Mustafa
"""

import os
import sys
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
import gzip
import csv

# ================= DISPLAY ENVIRONMENT SETUP =================
# Fix for Thonny IDE and headless environments
if 'DISPLAY' not in os.environ:
    os.environ['DISPLAY'] = ':0'
    print("[SETUP] DISPLAY not set, attempting to use :0")

if 'THONNY_USER_DIR' in os.environ:
    print("[WARNING] Thonny detected - GUI may not work properly")
    print("[WARNING] Please run directly: python3 plc_tag_scanner_standalone.py")

# Test display availability
try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext
    test_root = tk.Tk()
    test_root.withdraw()
    test_root.destroy()
    print("[OK] Display available - GUI mode enabled")
    GUI_AVAILABLE = True
    HEADLESS_MODE = False
except Exception as e:
    print(f"[WARNING] Display test failed: {e}")
    print("[INFO] Running in HEADLESS mode (console logging only)")
    GUI_AVAILABLE = False
    HEADLESS_MODE = True
    import tkinter as tk
    from tkinter import ttk, scrolledtext
# ============================================================

# PLC library (lazy import for faster startup)
PLC_AVAILABLE = False
LogixDriver = None

def _lazy_import_plc():
    """Import PLC library only when needed"""
    global PLC_AVAILABLE, LogixDriver
    if not PLC_AVAILABLE:
        try:
            from pycomm3 import LogixDriver as LD
            LogixDriver = LD
            PLC_AVAILABLE = True
            return True
        except ImportError as e:
            print(f"[ERROR] pycomm3 not installed: {e}")
            print("[INFO] Run: pip install pycomm3")
            return False
    return True

# Database library (optional - lazy import)
DB_AVAILABLE = False
psycopg2 = None


# ============================================================================
# EMBEDDED CONFIGURATION - EDIT THIS SECTION TO CUSTOMIZE
# ============================================================================
# SCAN RATE OPTIONS: You can use any value from 1ms to 1000ms
# Common options: 1, 5, 10, 20, 50, 100, 200, 500, 1000 (in milliseconds)
# Lower values = faster scanning = higher CPU usage
# ============================================================================
EMBEDDED_CONFIG = {
    "plc_connection": {
        "ip": "192.168.0.20",
        "slot": 0,
        "path": "1,0",
        "timeout": 5,
        "retry_attempts": 3
    },
    "csv_logging": {
        "enabled": True,
        "directory": "./plc_scan_logs",
        "compression": "gzip",
        "timezone": "UTC"
    },
    "scan_groups": [
        {
            "name": "Welding_Ultra_Fast_10ms",
            "scan_rate_ms": 10,
            "enabled": True,
            "tags": [
                "Welding_Current_A",
                "Welding_Voltage_V",
                "Arc"
            ]
        },
        {
            "name": "Welding_Fast_50ms",
            "scan_rate_ms": 50,
            "enabled": True,
            "tags": [
                "Power",
                "Welder_id",
                "WPS_ID"
            ]
        },
        {
            "name": "Welding_Info_100ms",
            "scan_rate_ms": 100,
            "enabled": True,
            "tags": [
                "Joint_Id",
                "Pipe_Id"
            ]
        },
        {
            "name": "Pump_Monitoring_500ms",
            "scan_rate_ms": 500,
            "enabled": True,
            "tags": [
                "Pump_RPM",
                "Pump_Flow_Rate",
                "Pump_Discharge_Pressure",
                "Pump_Suction_Pressure",
                "Pump_Motor_Current",
                "Pump_Bearing_Temp"
            ]
        },
        {
            "name": "Status_Slow_1000ms",
            "scan_rate_ms": 1000,
            "enabled": True,
            "tags": [
                "sim_step",
                "Pump_Running_Status",
                "Pump_Healthy",
                "Load_MW",
                "Inlet_Temp",
                "Boiler_Inlet_Temp"
            ]
        }
    ],
    "performance": {
        "batch_size": 100,
        "csv_write_interval_ms": 5000
    }
}
# ============================================================================


class ConfigManager:
    """Load and manage scan configuration - uses embedded config"""
    
    def __init__(self, config_file=None):
        self.config_file = config_file
        self.config = EMBEDDED_CONFIG
        print(f"[INFO] Using embedded configuration")
        print(f"[INFO] PLC: {self.config['plc_connection']['ip']}")
        print(f"[INFO] Scan groups: {len(self.config['scan_groups'])}")
    
    def get_default_config(self):
        """Return embedded configuration"""
        return EMBEDDED_CONFIG


class ScanGroup:
    """Represents a group of tags with same scan rate"""
    
    def __init__(self, name, scan_rate_ms, tags, enabled=True):
        self.name = name
        self.scan_rate_ms = scan_rate_ms
        self.scan_rate_sec = scan_rate_ms / 1000.0
        self.tags = tags
        self.enabled = enabled
        self.last_scan = 0
        self.scan_count = 0
        self.values = {}
        
    def should_scan(self, current_time):
        """Check if this group should be scanned now"""
        if not self.enabled:
            return False
        return (current_time - self.last_scan) >= self.scan_rate_sec
    
    def update_scan_time(self):
        """Update last scan timestamp"""
        self.last_scan = time.time()
        self.scan_count += 1


class PLCScanner:
    """Main PLC scanning engine"""
    
    def __init__(self, config, ui=None):
        self.config = config
        self.ui = ui
        self.running = True  # Auto-start enabled
        self.plc = None
        self.current_scan_rate = 1.0  # Default 1 second
        
        # Initialize scan groups
        self.scan_groups = []
        for i, group_config in enumerate(config.config['scan_groups']):
            group = ScanGroup(
                name=group_config['name'],
                scan_rate_ms=group_config['scan_rate_ms'],
                tags=group_config['tags'],
                enabled=group_config.get('enabled', True)
            )
            # Stagger initial scan times to prevent all groups scanning at once
            group.last_scan = time.time() - (i * 0.05)  # 50ms offset per group
            self.scan_groups.append(group)
        
        # CSV logging
        self.csv_enabled = config.config['csv_logging']['enabled']
        self.csv_dir = config.config['csv_logging']['directory']
        self.csv_buffer = []
        self.csv_lock = threading.Lock()
        
        # Statistics
        self.stats = {
            'total_scans': 0,
            'total_values': 0,
            'errors': 0,
            'start_time': datetime.now()
        }
        
    def log(self, level, message):
        """Log message to UI or console"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] [{level}] {message}"
        
        if self.ui and hasattr(self.ui, 'log'):
            self.ui.log(level, message)
        else:
            print(log_msg)
    
    def connect_plc(self):
        """Connect to PLC"""
        # Lazy import pycomm3
        if not _lazy_import_plc():
            self.log("ERROR", "pycomm3 library not available")
            self.log("ERROR", "Install with: pip install pycomm3")
            if self.ui:
                self.ui.set_plc_connected(False)
            return False
        
        plc_config = self.config.config['plc_connection']
        plc_path = f"{plc_config['ip']}/{plc_config['path']}"
        
        try:
            self.log("INFO", f"Connecting to PLC: {plc_config['ip']} (path: {plc_config['path']})")
            self.plc = LogixDriver(plc_path, init_tags=False)
            self.plc.open()
            self.log("SUCCESS", f"PLC connected: {plc_config['ip']}")
            if self.ui:
                self.ui.set_plc_connected(True)
            return True
        except Exception as e:
            error_msg = str(e)
            self.log("ERROR", f"PLC connection failed: {error_msg}")
            self.log("ERROR", f"Check: IP={plc_config['ip']}, Path={plc_config['path']}, Slot={plc_config['slot']}")
            if self.ui:
                self.ui.set_plc_connected(False)
            return False
    
    def disconnect_plc(self):
        """Disconnect from PLC"""
        if self.plc:
            try:
                self.plc.close()
                self.log("INFO", "PLC disconnected")
                if self.ui:
                    self.ui.set_plc_connected(False)
            except:
                pass
    
    def scan_group(self, group):
        """Scan all tags in a group"""
        if not group.tags or not self.plc:
            return
        
        try:
            timestamp = datetime.now(timezone.utc)
            values_read = 0
            
            # Read tags individually to avoid PLC batch size limits
            for tag in group.tags:
                try:
                    result = self.plc.read(tag)
                    
                    if hasattr(result, 'error') and result.error:
                        self.log("WARNING", f"Tag read error: {tag} - {result.error}")
                        continue
                    
                    value = result.value if hasattr(result, 'value') else result
                    if value is None:
                        continue
                    
                    # Store value
                    group.values[tag] = {
                        'value': value,
                        'timestamp': timestamp,
                        'type': type(value).__name__
                    }
                    
                    # Update UI
                    if self.ui:
                        self.ui.update_tag_value(tag, value, group.name)
                    
                    # Add to CSV buffer
                    if self.csv_enabled:
                        with self.csv_lock:
                            self.csv_buffer.append({
                                'timestamp': timestamp,
                                'tag': tag,
                                'value': value,
                                'group': group.name
                            })
                    
                    values_read += 1
                    
                except Exception as tag_error:
                    self.log("WARNING", f"Tag {tag} read failed: {tag_error}")
                    continue
            
            self.stats['total_values'] += values_read
            group.update_scan_time()
            
        except Exception as e:
            self.log("ERROR", f"Scan error in group {group.name}: {e}")
            self.stats['errors'] += 1
            # Add small delay on error to prevent hammering PLC
            time.sleep(0.1)
    
    def write_csv_buffer(self):
        """Write CSV buffer to compressed file"""
        if not self.csv_enabled or not self.csv_buffer:
            return
        
        with self.csv_lock:
            try:
                # Create directory
                Path(self.csv_dir).mkdir(parents=True, exist_ok=True)
                
                # Generate filename
                now = datetime.now()
                filename = now.strftime("%Y%m%d_%H%M%S.csv.gz")
                filepath = os.path.join(self.csv_dir, filename)
                
                # Write compressed CSV
                with gzip.open(filepath, 'wt', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Timestamp', 'Tag', 'Value', 'Group'])
                    
                    for entry in self.csv_buffer:
                        ts_str = entry['timestamp'].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                        writer.writerow([
                            ts_str,
                            entry['tag'],
                            entry['value'],
                            entry['group']
                        ])
                
                self.log("INFO", f"CSV: Wrote {len(self.csv_buffer)} records to {filename}")
                self.csv_buffer.clear()
                
            except Exception as e:
                self.log("ERROR", f"CSV write failed: {e}")
    
    def run(self):
        """Main scanning loop"""
        self.running = True
        self.log("INFO", "Scanner started")
        
        if not self.connect_plc():
            self.running = False
            return
        
        last_csv_write = time.time()
        csv_interval = self.config.config['performance']['csv_write_interval_ms'] / 1000.0
        
        while self.running:
            try:
                current_time = time.time()
                
                # Scan each group if due (with small delay between groups)
                groups_scanned = 0
                for group in self.scan_groups:
                    if group.should_scan(current_time):
                        self.scan_group(group)
                        self.stats['total_scans'] += 1
                        groups_scanned += 1
                        # Small delay between group scans to prevent overwhelming PLC
                        if groups_scanned < len(self.scan_groups):
                            time.sleep(0.01)  # 10ms delay between groups
                
                # Write CSV periodically
                if self.csv_enabled and (current_time - last_csv_write) >= csv_interval:
                    self.write_csv_buffer()
                    last_csv_write = current_time
                
                # Update stats in UI
                if self.ui and self.stats['total_scans'] % 10 == 0:
                    self.ui.update_stats(self.stats)
                
                # Use minimum scan rate from groups or UI override
                # Find the fastest enabled group scan rate
                min_group_rate = min(
                    (g.scan_rate_sec for g in self.scan_groups if g.enabled),
                    default=0.1
                )
                # Use the smaller of UI rate or fastest group rate
                sleep_time = min(self.current_scan_rate, min_group_rate)
                time.sleep(sleep_time)
                
            except Exception as e:
                self.log("ERROR", f"Scanner error: {e}")
                self.stats['errors'] += 1
                time.sleep(1)
        
        self.disconnect_plc()
        self.log("INFO", "Scanner stopped")
    
    def start(self):
        """Start scanner in background thread - called automatically"""
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
    
    def stop(self):
        """Stop scanner"""
        self.running = False
        if hasattr(self, 'thread'):
            self.thread.join(timeout=2)
    
    def update_scan_rate(self, rate_ms):
        """Update scan rate dynamically"""
        self.current_scan_rate = rate_ms / 1000.0
        self.log("INFO", f"Scan rate updated to {rate_ms}ms ({self.current_scan_rate}s)")


class ScannerUI:
    """GUI for PLC Scanner"""
    
    def __init__(self, config_file):
        if not GUI_AVAILABLE:
            print("[ERROR] GUI not available on this system")
            sys.exit(1)
        
        self.config = ConfigManager(config_file)
        self.scanner = None
        
        # Create main window
        self.root = tk.Tk()
        self.root.title("PLC Tag Scanner - Multi-Rate Scanning")
        self.root.geometry("1200x700")
        self.root.configure(bg="#1e1e1e")
        
        self.build_ui()
        
    def build_ui(self):
        """Build the user interface"""
        
        # Top toolbar
        toolbar = tk.Frame(self.root, bg="#2d2d2d", height=60)
        toolbar.pack(fill=tk.X, side=tk.TOP)
        toolbar.pack_propagate(False)
        
        tk.Label(toolbar, text="PLC Tag Scanner", font=("Arial", 16, "bold"),
                bg="#2d2d2d", fg="#00d4ff").pack(side=tk.LEFT, padx=20, pady=15)
        
        # PLC status indicator
        self.plc_status_canvas = tk.Canvas(toolbar, width=20, height=20, bg="#2d2d2d", highlightthickness=0)
        self.plc_status_canvas.pack(side=tk.RIGHT, padx=5)
        self.plc_status_circle = self.plc_status_canvas.create_oval(2, 2, 18, 18, fill="#808080", outline="")
        
        self.plc_status_label = tk.Label(toolbar, text="PLC: Disconnected", font=("Arial", 10),
                                        bg="#2d2d2d", fg="#808080")
        self.plc_status_label.pack(side=tk.RIGHT, padx=5)
        
        # Status indicator (auto-running)
        status_frame = tk.Frame(toolbar, bg="#2d2d2d")
        status_frame.pack(side=tk.RIGHT, padx=20)
        
        self.running_dot = tk.Canvas(status_frame, width=16, height=16, bg="#2d2d2d", highlightthickness=0)
        self.running_dot.pack(side=tk.LEFT, padx=5)
        self.running_circle = self.running_dot.create_oval(2, 2, 14, 14, fill="#00ff00", outline="")
        
        tk.Label(status_frame, text="● AUTO-SCANNING", font=("Arial", 10, "bold"),
                fg="#00ff00", bg="#2d2d2d").pack(side=tk.LEFT, padx=5)
        
        # Main content area
        content = tk.Frame(self.root, bg="#1e1e1e")
        content.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left panel: Tag values (60%)
        left_panel = tk.Frame(content, bg="#1e1e1e")
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        tk.Label(left_panel, text="Live Tag Values", font=("Arial", 12, "bold"),
                bg="#1e1e1e", fg="#ffffff", anchor="w").pack(fill=tk.X, pady=(0, 5))
        
        # Treeview for tag values
        tree_frame = tk.Frame(left_panel, bg="#2d2d2d")
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        tree_scroll = ttk.Scrollbar(tree_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree = ttk.Treeview(tree_frame, columns=("Tag", "Value", "Group", "Time"),
                                show="headings", yscrollcommand=tree_scroll.set)
        self.tree.heading("Tag", text="Tag Name")
        self.tree.heading("Value", text="Value")
        self.tree.heading("Group", text="Scan Group")
        self.tree.heading("Time", text="Last Update")
        
        self.tree.column("Tag", width=300)
        self.tree.column("Value", width=150)
        self.tree.column("Group", width=150)
        self.tree.column("Time", width=120)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.config(command=self.tree.yview)
        
        self.tree_items = {}
        
        # Right panel: Log and stats (40%)
        right_panel = tk.Frame(content, bg="#1e1e1e")
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        # Scan Rate Configuration Panel
        config_frame = tk.LabelFrame(right_panel, text="Quick Scan Rate Selector", 
                                    font=("Arial", 10, "bold"),
                                    bg="#2d2d2d", fg="#ffaa00", relief=tk.FLAT)
        config_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Dropdown for scan rate selection
        self.scan_rate_options = {
            "Ultra Fast (1ms)": 1,
            "Very Fast (5ms)": 5,
            "Fast (10ms)": 10,
            "Quick (20ms)": 20,
            "Normal (50ms)": 50,
            "Medium (100ms)": 100,
            "Moderate (200ms)": 200,
            "Slow (500ms)": 500,
            "Very Slow (1000ms)": 1000
        }
        
        dropdown_frame = tk.Frame(config_frame, bg="#2d2d2d")
        dropdown_frame.pack(fill=tk.X, padx=10, pady=8)
        
        tk.Label(dropdown_frame, text="Scan Rate (Live):", font=("Arial", 9, "bold"),
                bg="#2d2d2d", fg="#00d4ff").pack(side=tk.LEFT, padx=(0, 10))
        
        self.scan_rate_var = tk.StringVar(value="Very Slow (1000ms)")
        scan_dropdown = ttk.Combobox(dropdown_frame, textvariable=self.scan_rate_var,
                                    values=list(self.scan_rate_options.keys()),
                                    state="readonly", width=20)
        scan_dropdown.pack(side=tk.LEFT)
        scan_dropdown.bind("<<ComboboxSelected>>", self.on_scan_rate_changed)
        
        info_text = "⚡ Changes apply immediately - No restart needed!"
        tk.Label(config_frame, text=info_text, font=("Arial", 8, "bold"),
                bg="#2d2d2d", fg="#00ff00", wraplength=300, justify=tk.LEFT).pack(padx=10, pady=(0, 5))
        
        # Scan Groups Panel
        groups_frame = tk.LabelFrame(right_panel, text="Active Scan Groups", font=("Arial", 10, "bold"),
                                   bg="#2d2d2d", fg="#00d4ff", relief=tk.FLAT)
        groups_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.group_labels = {}
        for group in self.config.config['scan_groups']:
            row = tk.Frame(groups_frame, bg="#2d2d2d")
            row.pack(fill=tk.X, padx=10, pady=3)
            
            status_color = "#00ff00" if group['enabled'] else "#808080"
            status_text = "●" if group['enabled'] else "○"
            
            tk.Label(row, text=status_text, font=("Arial", 12), bg="#2d2d2d", 
                    fg=status_color, anchor="w", width=2).pack(side=tk.LEFT)
            
            tk.Label(row, text=f"{group['name']}", font=("Arial", 9), 
                    bg="#2d2d2d", fg="#cccccc", anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True)
            
            tk.Label(row, text=f"{group['scan_rate_ms']}ms", font=("Arial", 9, "bold"), 
                    bg="#2d2d2d", fg="#00d4ff", anchor="e").pack(side=tk.RIGHT)
            
            self.group_labels[group['name']] = row
        
        # Statistics
        stats_frame = tk.LabelFrame(right_panel, text="Statistics", font=("Arial", 10, "bold"),
                                   bg="#2d2d2d", fg="#00d4ff", relief=tk.FLAT)
        stats_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.stat_labels = {}
        stats = [("Total Scans", "total_scans"), ("Values Read", "total_values"), ("Errors", "errors")]
        
        for label, key in stats:
            row = tk.Frame(stats_frame, bg="#2d2d2d")
            row.pack(fill=tk.X, padx=10, pady=5)
            
            tk.Label(row, text=f"{label}:", font=("Arial", 9), bg="#2d2d2d", fg="#cccccc", anchor="w").pack(side=tk.LEFT)
            self.stat_labels[key] = tk.Label(row, text="0", font=("Arial", 9, "bold"), bg="#2d2d2d", fg="#00ff00", anchor="e")
            self.stat_labels[key].pack(side=tk.RIGHT)
        
        # Log viewer
        tk.Label(right_panel, text="System Log", font=("Arial", 10, "bold"),
                bg="#1e1e1e", fg="#ffffff", anchor="w").pack(fill=tk.X, pady=(0, 5))
        
        log_frame = tk.Frame(right_panel, bg="#2d2d2d")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, bg="#1a1a1a", fg="#cccccc",
                                                  font=("Consolas", 9), wrap=tk.WORD,
                                                  relief=tk.FLAT, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        # Configure log colors
        self.log_text.tag_config("INFO", foreground="#00d4ff")
        self.log_text.tag_config("SUCCESS", foreground="#00ff00")
        self.log_text.tag_config("WARNING", foreground="#ffaa00")
        self.log_text.tag_config("ERROR", foreground="#ff0000")
        
    def set_plc_connected(self, connected):
        """Update PLC connection status"""
        if connected:
            self.plc_status_canvas.itemconfig(self.plc_status_circle, fill="#00ff00")
            self.plc_status_label.config(text="PLC: Connected", fg="#00ff00")
        else:
            self.plc_status_canvas.itemconfig(self.plc_status_circle, fill="#ff0000")
            self.plc_status_label.config(text="PLC: Disconnected", fg="#ff0000")
    
    def update_tag_value(self, tag, value, group):
        """Update tag value in treeview"""
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            value_str = f"{value:.3f}" if isinstance(value, float) else str(value)
            
            if tag in self.tree_items:
                self.tree.set(self.tree_items[tag], "Value", value_str)
                self.tree.set(self.tree_items[tag], "Time", timestamp)
            else:
                item = self.tree.insert("", "end", values=(tag, value_str, group, timestamp))
                self.tree_items[tag] = item
        except:
            pass
    
    def update_stats(self, stats):
        """Update statistics display"""
        try:
            for key, label in self.stat_labels.items():
                if key in stats:
                    label.config(text=str(stats[key]))
        except:
            pass
    
    def log(self, level, message):
        """Add log message"""
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, f"[{timestamp}] ", "INFO")
            self.log_text.insert(tk.END, f"[{level}] ", level)
            self.log_text.insert(tk.END, f"{message}\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        except:
            print(f"[{level}] {message}")
    
    def log_scan_group_info(self):
        """Log scan group configuration on startup"""
        self.log("INFO", "=== Scan Groups Configuration ===")
        self.log("INFO", "Supported scan rates: 1ms to 1000ms")
        for group in self.config.config['scan_groups']:
            status = "ENABLED" if group['enabled'] else "DISABLED"
            self.log("INFO", f"  {group['name']}: {group['scan_rate_ms']}ms [{status}] - {len(group['tags'])} tags")
        self.log("INFO", "=================================")
    
    def on_scan_rate_changed(self, event=None):
        """Handle scan rate dropdown selection - apply immediately"""
        try:
            selected = self.scan_rate_var.get()
            rate_ms = self.scan_rate_options[selected]
            
            if self.scanner:
                self.scanner.update_scan_rate(rate_ms)
                self.log("SUCCESS", f"Scan rate changed to: {selected}")
            else:
                self.log("WARNING", "Scanner not initialized yet")
        except Exception as e:
            self.log("ERROR", f"Failed to update scan rate: {e}")
    
    def auto_start_scanner(self):
        """Auto-start scanner on initialization"""
        try:
            self.log("INFO", "Auto-starting scanner...")
            self.scanner = PLCScanner(self.config, ui=self)
            
            # Apply initial scan rate from dropdown
            selected = self.scan_rate_var.get()
            rate_ms = self.scan_rate_options[selected]
            self.scanner.current_scan_rate = rate_ms / 1000.0
            
            self.scanner.start()
            self.log("SUCCESS", f"Scanner started with {rate_ms}ms scan rate")
        except Exception as e:
            self.log("ERROR", f"Auto-start failed: {e}")
            import traceback
            traceback.print_exc()
    
    def run(self):
        """Start the UI and auto-start scanner"""
        self.log("INFO", "PLC Scanner initialized")
        self.log("INFO", "Using EMBEDDED configuration (no external files)")
        self.log("INFO", f"PLC: {self.config.config['plc_connection']['ip']}")
        self.log_scan_group_info()
        
        # Auto-start scanner after UI is ready
        self.root.after(1000, self.auto_start_scanner)
        
        self.root.mainloop()


def main():
    """Main entry point"""
    print("=" * 70)
    print("  PLC Tag Scanner - Multi-Rate Scanning v1.0")
    print("  Standalone Application - Does NOT affect main OPC system")
    print("  Configuration: EMBEDDED (no external files needed)")
    print("=" * 70)
    print()
    
    if GUI_AVAILABLE:
        print("[INFO] Starting GUI mode...")
        try:
            app = ScannerUI(config_file=None)
            app.run()
        except Exception as e:
            print(f"[ERROR] GUI failed to start: {e}")
            print(f"[ERROR] Details: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    else:
        # Console mode
        print("[INFO] Running in console mode (no GUI)")
        config = ConfigManager()
        scanner = PLCScanner(config)
        
        try:
            scanner.run()
        except KeyboardInterrupt:
            print("\n[INFO] Shutting down...")
            scanner.stop()
        except Exception as e:
            print(f"[ERROR] Scanner failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[FATAL ERROR] Application crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
