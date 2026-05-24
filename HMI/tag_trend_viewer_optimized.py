"""
Tag Trend Viewer - ULTRA OPTIMIZED VERSION
Uses TimescaleDB best practices for maximum performance
"""
import sys
import psycopg2
from datetime import datetime, timedelta
import json
import time
import numpy as np
import csv

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QComboBox, QDateTimeEdit, 
                             QLabel, QMessageBox, QGroupBox, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QCheckBox, QSpinBox,
                             QFileDialog, QProgressBar)
from PyQt5.QtCore import Qt, QDateTime
from PyQt5.QtGui import QFont
import pyqtgraph as pg
from pyqtgraph import DateAxisItem, setConfigOptions

# Configure pyqtgraph
setConfigOptions(useOpenGL=False)
setConfigOptions(antialias=True)

# Load database configuration
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
        db_config = config['database']
except:
    db_config = {
        'host': 'localhost',
        'port': 5432,
        'database': 'Cereveate',
        'user': 'cereveate',
        'password': 'cereveate@222'
    }


class TagTrendViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.connection = None
        self.cursor = None
        self.available_tags = []
        self.current_data = []
        self.current_timestamps = []
        self.current_values = []
        
        self.init_ui()
        self.connect_to_database()
        self.load_available_tags()
        
    def init_ui(self):
        """Initialize UI"""
        self.setWindowTitle('⚡ Tag Trend Viewer - ULTRA OPTIMIZED')
        self.setGeometry(100, 100, 1400, 800)
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        
        # Control panel
        control_group = QGroupBox("Query Controls")
        control_layout = QVBoxLayout()
        
        # Tag selection
        tag_row = QHBoxLayout()
        tag_row.addWidget(QLabel("Select Tag:"))
        self.tag_combo = QComboBox()
        self.tag_combo.setMinimumWidth(300)
        self.tag_combo.setEditable(True)
        tag_row.addWidget(self.tag_combo)
        tag_row.addStretch()
        control_layout.addLayout(tag_row)
        
        # Date range
        date_row = QHBoxLayout()
        date_row.addWidget(QLabel("Start:"))
        self.start_datetime = QDateTimeEdit()
        self.start_datetime.setCalendarPopup(True)
        self.start_datetime.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.start_datetime.setDateTime(QDateTime.currentDateTime().addDays(-1))
        date_row.addWidget(self.start_datetime)
        
        date_row.addWidget(QLabel("End:"))
        self.end_datetime = QDateTimeEdit()
        self.end_datetime.setCalendarPopup(True)
        self.end_datetime.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.end_datetime.setDateTime(QDateTime.currentDateTime())
        date_row.addWidget(self.end_datetime)
        date_row.addStretch()
        control_layout.addLayout(date_row)
        
        # Quick time
        quick_row = QHBoxLayout()
        for label, hours in [("1h", 1), ("6h", 6), ("24h", 24), ("7d", 168)]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked, h=hours: self.set_quick_range(h))
            quick_row.addWidget(btn)
        quick_row.addStretch()
        control_layout.addLayout(quick_row)
        
        # Query mode - THREE OPTIMIZED OPTIONS
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Query Mode:"))
        self.query_mode_combo = QComboBox()
        self.query_mode_combo.addItem("⚡ Sampled (Fast - Exact Values)", "skip")
        self.query_mode_combo.addItem("📊 Time-Based Sample (Exact Values)", "bucket")
        self.query_mode_combo.addItem("🔬 All Data (Slow - Full Resolution)", "full")
        self.query_mode_combo.setToolTip(
            "Sampled: Takes every Nth point - EXACT values, no averaging\n"
            "Time-Based: One actual value per time interval - EXACT values\n"
            "All Data: Returns every single raw data point (slow for large ranges)"
        )
        mode_row.addWidget(self.query_mode_combo)
        
        mode_row.addWidget(QLabel("Max Points:"))
        self.max_points_spin = QSpinBox()
        self.max_points_spin.setRange(100, 1000000)
        self.max_points_spin.setValue(10000)
        self.max_points_spin.setSingleStep(1000)
        mode_row.addWidget(self.max_points_spin)
        
        self.explain_cb = QCheckBox("Show Query Plan")
        self.explain_cb.setToolTip("Print EXPLAIN ANALYZE to console")
        mode_row.addWidget(self.explain_cb)
        
        mode_row.addStretch()
        control_layout.addLayout(mode_row)
        
        # Display options
        opts_row = QHBoxLayout()
        self.show_points_cb = QCheckBox("Show Points")
        self.show_points_cb.setChecked(True)
        opts_row.addWidget(self.show_points_cb)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(200)
        opts_row.addWidget(self.progress_bar)
        opts_row.addStretch()
        control_layout.addLayout(opts_row)
        
        # Query button
        btn_row = QHBoxLayout()
        self.query_btn = QPushButton("🔍 Query Data")
        self.query_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; padding: 8px; }")
        self.query_btn.clicked.connect(self.query_data)
        btn_row.addWidget(self.query_btn)
        
        self.export_btn = QPushButton("💾 Export CSV")
        self.export_btn.clicked.connect(self.export_to_csv)
        self.export_btn.setEnabled(False)
        btn_row.addWidget(self.export_btn)
        btn_row.addStretch()
        control_layout.addLayout(btn_row)
        
        control_group.setLayout(control_layout)
        main_layout.addWidget(control_group)
        
        # Status
        self.status_label = QLabel("Status: Ready")
        self.status_label.setStyleSheet("padding: 6px; background-color: #f0f0f0; border: 1px solid #ddd;")
        main_layout.addWidget(self.status_label)
        
        # Chart
        self.chart_widget = pg.PlotWidget(axisItems={'bottom': DateAxisItem()})
        self.chart_widget.setBackground('w')
        self.chart_widget.showGrid(x=True, y=True, alpha=0.3)
        self.chart_widget.setLabel('left', 'Value')
        self.chart_widget.setLabel('bottom', 'Time')
        main_layout.addWidget(self.chart_widget, stretch=3)
        
        # Stats
        self.stats_label = QLabel("Statistics: No data")
        self.stats_label.setStyleSheet("padding: 5px; background-color: #e8f4fd; font-family: monospace;")
        main_layout.addWidget(self.stats_label)
        
        # Table
        table_group = QGroupBox("Data Points (Last 100)")
        table_layout = QVBoxLayout()
        self.data_table = QTableWidget()
        self.data_table.setColumnCount(4)
        self.data_table.setHorizontalHeaderLabels(['Timestamp', 'Value', 'Quality', 'Tag'])
        self.data_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.data_table.setMaximumHeight(200)
        self.data_table.setAlternatingRowColors(True)
        table_layout.addWidget(self.data_table)
        table_group.setLayout(table_layout)
        main_layout.addWidget(table_group, stretch=1)
        
    def connect_to_database(self):
        """Connect with TimescaleDB optimizations"""
        try:
            # Connection with performance parameters
            self.connection = psycopg2.connect(
                host=db_config['host'],
                port=db_config['port'],
                database=db_config['database'],
                user=db_config['user'],
                password=db_config['password'],
                options='-c statement_timeout=60000 -c work_mem=512MB -c effective_cache_size=4GB'
            )
            self.cursor = self.connection.cursor()
            
            # Parallel execution settings
            self.cursor.execute("SET max_parallel_workers_per_gather = 4")
            self.cursor.execute("SET parallel_tuple_cost = 0.01")
            self.cursor.execute("SET enable_partitionwise_aggregate = on")
            
            self.connection.commit()
            
            self.status_label.setText("✅ Connected (TimescaleDB optimized)")
            self.status_label.setStyleSheet("background-color: #d4edda;")
            
        except Exception as e:
            self.status_label.setText(f"❌ Connection failed: {str(e)[:80]}")
            self.status_label.setStyleSheet("background-color: #f8d7da;")
            QMessageBox.critical(self, "Error", f"Database connection failed:\n{e}")
    
    def load_available_tags(self):
        """Load tags"""
        if not self.connection:
            return
            
        try:
            self.cursor.execute("""
                SELECT DISTINCT tag_id 
                FROM historian_raw.historian_timeseries 
                ORDER BY tag_id
                LIMIT 100
            """)
            
            tags = self.cursor.fetchall()
            self.tag_combo.clear()
            
            for tag in tags:
                self.tag_combo.addItem(str(tag[0]), tag[0])
            
            self.status_label.setText(f"✅ Loaded {len(tags)} tags")
            
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Cannot load tags:\n{e}")
    
    def set_quick_range(self, hours):
        """Set time range"""
        end = QDateTime.currentDateTime()
        start = end.addSecs(-hours * 3600)
        self.start_datetime.setDateTime(start)
        self.end_datetime.setDateTime(end)
    
    def query_data(self):
        """OPTIMIZED QUERY - Three performance modes"""
        if not self.connection:
            QMessageBox.warning(self, "Error", "Not connected")
            return
            
        if self.tag_combo.currentIndex() < 0:
            QMessageBox.warning(self, "Error", "Select a tag")
            return
            
        tag_id = self.tag_combo.currentData()
        start_time = self.start_datetime.dateTime().toPyDateTime()
        end_time = self.end_datetime.dateTime().toPyDateTime()
        max_points = self.max_points_spin.value()
        
        if start_time >= end_time:
            QMessageBox.warning(self, "Error", "Invalid time range")
            return
            
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("⏳ Querying...")
        QApplication.processEvents()
        
        query_start = time.time()
        
        try:
            self.current_data = []
            self.current_timestamps = []
            self.current_values = []
            
            # Get fast estimate (skip if function doesn't exist)
            try:
                # Simple row count estimation without the function
                self.cursor.execute("""
                    SELECT reltuples::bigint AS estimate
                    FROM pg_class
                    WHERE relname = 'historian_timeseries'
                """)
                estimated_rows = self.cursor.fetchone()[0] or max_points
                # Rough estimation: assume even distribution
                time_range_total = (end_time - start_time).total_seconds()
                estimated_rows = min(estimated_rows // 10, max_points * 10)
            except:
                estimated_rows = max_points
            
            self.progress_bar.setValue(10)
            
            # SELECT OPTIMAL QUERY MODE
            query_mode = self.query_mode_combo.currentData()
            
            if query_mode == "skip":
                # ⚡ FAST: Sample raw data points (no averaging!)
                # Takes every Nth row to reduce data volume while keeping EXACT values
                time_range = (end_time - start_time).total_seconds()
                
                # Calculate sample rate: if too much data, take every Nth point
                sample_every = max(1, int(estimated_rows / max_points))
                
                if sample_every <= 1:
                    # Small dataset - return all raw data
                    query = """
                        SELECT opc_timestamp, value_num, quality, tag_id
                        FROM historian_raw.historian_timeseries
                        WHERE tag_id = %s
                        AND opc_timestamp >= %s
                        AND opc_timestamp <= %s
                        ORDER BY opc_timestamp
                        LIMIT %s
                    """
                    params = (tag_id, start_time, end_time, max_points)
                else:
                    # Large dataset - sample using row_number but keep EXACT values
                    query = f"""
                        WITH numbered AS (
                            SELECT opc_timestamp, value_num, quality, tag_id,
                                   ROW_NUMBER() OVER (ORDER BY opc_timestamp) as rn
                            FROM historian_raw.historian_timeseries
                            WHERE tag_id = %s
                            AND opc_timestamp >= %s
                            AND opc_timestamp <= %s
                        )
                        SELECT opc_timestamp, value_num, quality, tag_id
                        FROM numbered
                        WHERE rn % {sample_every} = 1
                        ORDER BY opc_timestamp
                        LIMIT %s
                    """
                    params = (tag_id, start_time, end_time, max_points)
                
            elif query_mode == "bucket":
                # 📊 EXACT DATA with time-based sampling (no AVG!)
                # Returns actual raw values, just fewer of them
                time_range = (end_time - start_time).total_seconds()
                sample_interval = max(1, int(time_range / max_points))
                
                query = f"""
                    WITH time_samples AS (
                        SELECT DISTINCT ON (time_bucket(%s, opc_timestamp))
                               opc_timestamp, value_num, quality, tag_id
                        FROM historian_raw.historian_timeseries
                        WHERE tag_id = %s
                        AND opc_timestamp >= %s
                        AND opc_timestamp <= %s
                        ORDER BY time_bucket(%s, opc_timestamp), opc_timestamp
                    )
                    SELECT opc_timestamp, value_num, quality, tag_id
                    FROM time_samples
                    ORDER BY opc_timestamp
                    LIMIT %s
                """
                params = (f'{sample_interval} seconds', tag_id, start_time, end_time, 
                         f'{sample_interval} seconds', max_points)
                
            else:  # full
                # 🔬 FULL: All data points (slowest)
                query = """
                    SELECT opc_timestamp, value_num, quality, tag_id
                    FROM historian_raw.historian_timeseries
                    WHERE tag_id = %s
                    AND opc_timestamp >= %s
                    AND opc_timestamp <= %s
                    ORDER BY opc_timestamp
                    LIMIT %s
                """
                params = (tag_id, start_time, end_time, max_points)
            
            self.progress_bar.setValue(30)
            
            # Optional EXPLAIN ANALYZE
            if self.explain_cb.isChecked():
                explain_query = "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) " + query
                self.cursor.execute(explain_query, params)
                explain_result = self.cursor.fetchall()
                print("\n" + "="*60)
                print(f"QUERY PLAN - Mode: {query_mode.upper()}")
                print("="*60)
                for row in explain_result:
                    print(row[0])
                print("="*60 + "\n")
            
            # Debug: Print query details
            print(f"\n{'='*60}")
            print(f"Query Mode: {query_mode}")
            print(f"Tag: {tag_id}")
            print(f"Start: {start_time}")
            print(f"End: {end_time}")
            print(f"Estimated Rows: {estimated_rows}")
            print(f"Max Points: {max_points}")
            print(f"{'='*60}\n")
            
            # Execute actual query
            self.cursor.execute(query, params)
            rows = self.cursor.fetchall()
            
            query_time = time.time() - query_start
            
            print(f"Query returned {len(rows)} rows in {query_time:.3f}s\n")
            
            self.progress_bar.setValue(70)
            
            if not rows or len(rows) == 0:
                QMessageBox.information(self, "No Data", "No data found for the selected time range and tag")
                self.progress_bar.setVisible(False)
                self.status_label.setText(f"❌ No data found for {tag_id}")
                self.status_label.setStyleSheet("background-color: #fff3cd;")
                return
            
            # Store data
            self.current_data = rows
            
            # Prepare for plotting
            for row in rows:
                timestamp = row[0]
                value = row[1] if row[1] is not None else float('nan')
                self.current_timestamps.append(timestamp.timestamp())
                self.current_values.append(float(value))
            
            self.progress_bar.setValue(90)
            QApplication.processEvents()
            
            # Display
            self.display_data(rows, tag_id, query_time, query_mode)
            
            self.export_btn.setEnabled(True)
            self.progress_bar.setValue(100)
            
        except Exception as e:
            QMessageBox.critical(self, "Query Error", f"Failed:\n{str(e)[:200]}")
            self.status_label.setText(f"❌ Error: {str(e)[:100]}")
            self.status_label.setStyleSheet("background-color: #f8d7da;")
        
        finally:
            self.progress_bar.setVisible(False)
    
    def display_data(self, rows, tag_id, query_time, query_mode):
        """Display results"""
        try:
            self.chart_widget.clear()
            
            timestamps_np = np.array(self.current_timestamps, dtype=np.float64)
            values_np = np.array(self.current_values, dtype=np.float64)
            valid_values = values_np[~np.isnan(values_np)]
            
            # Plot
            if len(timestamps_np) > 0:
                show_symbols = self.show_points_cb.isChecked() and len(timestamps_np) < 2000
                self.chart_widget.plot(
                    timestamps_np, 
                    values_np, 
                    pen=pg.mkPen(color='blue', width=2),
                    symbol='o' if show_symbols else None,
                    symbolSize=4,
                    symbolBrush='blue',
                    name=str(tag_id)
                )
            
            mode_emoji = {"skip": "⚡", "bucket": "📊", "full": "🔬"}.get(query_mode, "")
            self.chart_widget.setTitle(f"{mode_emoji} {tag_id} | {len(rows):,} points | {query_time:.3f}s")
            
            # Update table
            self.data_table.setRowCount(0)
            display_rows = rows[-100:]
            
            for i, row in enumerate(display_rows):
                self.data_table.insertRow(i)
                timestamp_str = row[0].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                value_str = f"{float(row[1]):.6f}" if row[1] is not None else "NULL"
                
                self.data_table.setItem(i, 0, QTableWidgetItem(timestamp_str))
                self.data_table.setItem(i, 1, QTableWidgetItem(value_str))
                self.data_table.setItem(i, 2, QTableWidgetItem(str(row[2])))
                self.data_table.setItem(i, 3, QTableWidgetItem(str(row[3])))
            
            # Statistics
            if len(valid_values) > 0:
                stats_text = (
                    f"📊 {tag_id} | Mode: {query_mode.upper()} | Query: {query_time:.3f}s\n"
                    f"Points: {len(rows):,} | "
                    f"Avg: {np.mean(valid_values):.6f} | "
                    f"Min: {np.min(valid_values):.6f} | "
                    f"Max: {np.max(valid_values):.6f} | "
                    f"StdDev: {np.std(valid_values):.6f}"
                )
            else:
                stats_text = "No valid data"
            
            self.stats_label.setText(stats_text)
            
            # Status
            mode_name = self.query_mode_combo.currentText()
            self.status_label.setText(f"✅ {mode_emoji} {len(rows):,} points in {query_time:.3f}s | {mode_name}")
            self.status_label.setStyleSheet("background-color: #d4edda;")
            
        except Exception as e:
            QMessageBox.warning(self, "Display Error", f"Error:\n{e}")
    
    def export_to_csv(self):
        """Export to CSV"""
        if not self.current_data:
            QMessageBox.warning(self, "No Data", "No data to export")
            return
            
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export", 
            f"tag_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV Files (*.csv)"
        )
        
        if filename:
            try:
                with open(filename, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Timestamp', 'Value', 'Quality', 'Tag'])
                    writer.writerows(self.current_data)
                
                QMessageBox.information(self, "Success", f"Exported {len(self.current_data):,} rows")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Export failed:\n{e}")
    
    def closeEvent(self, event):
        """Cleanup"""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    font = QFont("Segoe UI", 9)
    app.setFont(font)
    
    viewer = TagTrendViewer()
    viewer.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
