"""
Tag Trend Viewer - Standalone UI for querying and visualizing historical tag data
Shows ALL data points in a trend chart for selected date range
"""
import sys
import psycopg2
from datetime import datetime, timedelta
import json
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QComboBox, QDateTimeEdit, 
                             QLabel, QMessageBox, QGroupBox, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QCheckBox, QSpinBox)
from PyQt5.QtCore import Qt, QDateTime
import pyqtgraph as pg
from pyqtgraph import DateAxisItem
import numpy as np

# Load database configuration
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
        db_config = config['database']
except Exception as e:
    print(f"Error loading config: {e}")
    db_config = {
        'host': 'localhost',
        'port': 5432,
        'database': 'opcda_historian',
        'user': 'postgres',
        'password': 'admin'
    }


class TagTrendViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.connection = None
        self.available_tags = []
        self.current_data = []
        
        self.init_ui()
        self.connect_to_database()
        self.load_available_tags()
        
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle('Tag Trend Viewer - Historical Data Query')
        self.setGeometry(100, 100, 1400, 900)
        
        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        
        # Control panel
        control_group = QGroupBox("Query Controls")
        control_layout = QVBoxLayout()
        
        # Row 1: Tag selection
        tag_row = QHBoxLayout()
        tag_row.addWidget(QLabel("Select Tag:"))
        self.tag_combo = QComboBox()
        self.tag_combo.setMinimumWidth(300)
        tag_row.addWidget(self.tag_combo)
        tag_row.addStretch()
        control_layout.addLayout(tag_row)
        
        # Row 2: Date range
        date_row = QHBoxLayout()
        date_row.addWidget(QLabel("Start Time:"))
        self.start_datetime = QDateTimeEdit()
        self.start_datetime.setCalendarPopup(True)
        self.start_datetime.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.start_datetime.setDateTime(QDateTime.currentDateTime().addDays(-1))
        date_row.addWidget(self.start_datetime)
        
        date_row.addWidget(QLabel("End Time:"))
        self.end_datetime = QDateTimeEdit()
        self.end_datetime.setCalendarPopup(True)
        self.end_datetime.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.end_datetime.setDateTime(QDateTime.currentDateTime())
        date_row.addWidget(self.end_datetime)
        date_row.addStretch()
        control_layout.addLayout(date_row)
        
        # Row 3: Quick time buttons
        quick_row = QHBoxLayout()
        quick_row.addWidget(QLabel("Quick Range:"))
        
        btn_1h = QPushButton("Last 1 Hour")
        btn_1h.clicked.connect(lambda: self.set_quick_range(hours=1))
        quick_row.addWidget(btn_1h)
        
        btn_6h = QPushButton("Last 6 Hours")
        btn_6h.clicked.connect(lambda: self.set_quick_range(hours=6))
        quick_row.addWidget(btn_6h)
        
        btn_24h = QPushButton("Last 24 Hours")
        btn_24h.clicked.connect(lambda: self.set_quick_range(hours=24))
        quick_row.addWidget(btn_24h)
        
        btn_7d = QPushButton("Last 7 Days")
        btn_7d.clicked.connect(lambda: self.set_quick_range(days=7))
        quick_row.addWidget(btn_7d)
        
        quick_row.addStretch()
        control_layout.addLayout(quick_row)
        
        # Row 4: Display options
        options_row = QHBoxLayout()
        self.show_points_cb = QCheckBox("Show Data Points")
        self.show_points_cb.setChecked(True)
        options_row.addWidget(self.show_points_cb)
        
        options_row.addWidget(QLabel("Max Points to Display:"))
        self.max_points_spin = QSpinBox()
        self.max_points_spin.setRange(100, 100000)
        self.max_points_spin.setValue(10000)
        self.max_points_spin.setSingleStep(1000)
        options_row.addWidget(self.max_points_spin)
        
        options_row.addStretch()
        control_layout.addLayout(options_row)
        
        # Row 4b: Query optimization options
        query_mode_row = QHBoxLayout()
        query_mode_row.addWidget(QLabel("Query Mode:"))
        self.query_mode_combo = QComboBox()
        self.query_mode_combo.addItem("🚀 Optimized (TimescaleDB time_bucket)", "optimized")
        self.query_mode_combo.addItem("📊 Standard (Full scan)", "standard")
        self.query_mode_combo.addItem("⚖️ Compare Both (Side-by-side)", "compare")
        self.query_mode_combo.setCurrentIndex(0)
        query_mode_row.addWidget(self.query_mode_combo)
        
        self.compression_label = QLabel("Compression: Checking...")
        self.compression_label.setStyleSheet("padding: 5px; background-color: #e3f2fd; border-radius: 3px;")
        query_mode_row.addWidget(self.compression_label)
        
        query_mode_row.addStretch()
        control_layout.addLayout(query_mode_row)
        
        # Row 5: Query button
        button_row = QHBoxLayout()
        self.query_btn = QPushButton("Query Historical Data")
        self.query_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;")
        self.query_btn.clicked.connect(self.query_data)
        button_row.addWidget(self.query_btn)
        
        self.export_btn = QPushButton("Export to CSV")
        self.export_btn.clicked.connect(self.export_to_csv)
        self.export_btn.setEnabled(False)
        button_row.addWidget(self.export_btn)
        
        button_row.addStretch()
        control_layout.addLayout(button_row)
        
        control_group.setLayout(control_layout)
        main_layout.addWidget(control_group)
        
        # Status label
        self.status_label = QLabel("Status: Ready")
        self.status_label.setStyleSheet("padding: 5px; background-color: #e0e0e0;")
        main_layout.addWidget(self.status_label)
        
        # Chart widget with date axis
        self.chart_widget = pg.PlotWidget(axisItems={'bottom': DateAxisItem()})
        self.chart_widget.setBackground('w')
        self.chart_widget.showGrid(x=True, y=True, alpha=0.3)
        self.chart_widget.setLabel('left', 'Value')
        self.chart_widget.setLabel('bottom', 'Time')
        self.chart_widget.addLegend()
        main_layout.addWidget(self.chart_widget, stretch=3)
        
        # Data table
        table_group = QGroupBox("Data Points")
        table_layout = QVBoxLayout()
        self.data_table = QTableWidget()
        self.data_table.setColumnCount(5)
        self.data_table.setHorizontalHeaderLabels(['Timestamp', 'Value', 'Quality', 'Tag ID', 'Source'])
        self.data_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.data_table.setMaximumHeight(200)
        table_layout.addWidget(self.data_table)
        table_group.setLayout(table_layout)
        main_layout.addWidget(table_group, stretch=1)
        
    def check_compression_status(self):
        """Check if TimescaleDB compression is enabled for the table"""
        if not self.connection:
            return
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT 
                    h.table_name,
                    (SELECT count(*) FROM timescaledb_information.chunks 
                     WHERE hypertable_name = 'historian_timeseries' AND is_compressed = true) as compressed_chunks,
                    (SELECT count(*) FROM timescaledb_information.chunks 
                     WHERE hypertable_name = 'historian_timeseries') as total_chunks
                FROM _timescaledb_catalog.hypertable h
                WHERE h.table_name = 'historian_timeseries'
            """)
            row = cursor.fetchone()
            if row:
                compressed = row[1] if row[1] else 0
                total = row[2] if row[2] else 0
                if total > 0:
                    pct = (compressed / total) * 100
                    self.compression_label.setText(f"Compression: {compressed}/{total} chunks ({pct:.1f}%) ✓")
                    self.compression_label.setStyleSheet("padding: 5px; background-color: #c8e6c9; border-radius: 3px;")
                else:
                    self.compression_label.setText(f"Compression: Not a hypertable")
            cursor.close()
        except Exception as e:
            self.compression_label.setText(f"Compression: N/A")
    
    def connect_to_database(self):
        """Connect to PostgreSQL database with optimizations"""
        try:
            self.connection = psycopg2.connect(
                host=db_config['host'],
                port=db_config['port'],
                database=db_config['database'],
                user=db_config['user'],
                password=db_config['password'],
                # Connection optimizations
                options='-c work_mem=256MB -c max_parallel_workers_per_gather=4'
            )
            self.status_label.setText(f"Status: Connected to database - {db_config['database']}")
            self.status_label.setStyleSheet("padding: 5px; background-color: #c8e6c9;")
            self.check_compression_status()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to connect to database:\n{e}")
            self.status_label.setText(f"Status: Database connection failed - {e}")
            self.status_label.setStyleSheet("padding: 5px; background-color: #ffcdd2;")
            
    def load_available_tags(self):
        """Load all available tags from historian_meta.tag_master"""
        if not self.connection:
            return
            
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT tag_id, tag_name, data_type, eng_unit, description
                FROM historian_meta.tag_master
                WHERE enabled = true
                ORDER BY tag_id
            """)
            
            rows = cursor.fetchall()
            self.available_tags = []
            
            for row in rows:
                tag_id, tag_name, data_type, eng_unit, description = row
                display_text = f"{tag_id}"
                if tag_name:
                    display_text += f" ({tag_name})"
                if eng_unit:
                    display_text += f" [{eng_unit}]"
                    
                self.tag_combo.addItem(display_text, userData=tag_id)
                self.available_tags.append({
                    'tag_id': tag_id,
                    'tag_name': tag_name,
                    'data_type': data_type,
                    'eng_unit': eng_unit,
                    'description': description
                })
            
            cursor.close()
            self.status_label.setText(f"Status: Loaded {len(self.available_tags)} tags from database")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load tags:\n{e}")
            
    def set_quick_range(self, hours=None, days=None):
        """Set quick time range"""
        end_time = QDateTime.currentDateTime()
        
        if hours:
            start_time = end_time.addSecs(-hours * 3600)
        elif days:
            start_time = end_time.addDays(-days)
        else:
            start_time = end_time.addSecs(-3600)
            
        self.start_datetime.setDateTime(start_time)
        self.end_datetime.setDateTime(end_time)
        
    def query_data(self):
        """Query historical data for selected tag and date range"""
        if not self.connection:
            QMessageBox.warning(self, "Error", "No database connection")
            return
            
        if self.tag_combo.currentIndex() < 0:
            QMessageBox.warning(self, "Error", "Please select a tag")
            return
            
        tag_id = self.tag_combo.currentData()
        start_time = self.start_datetime.dateTime().toPyDateTime()
        end_time = self.end_datetime.dateTime().toPyDateTime()
        max_points = self.max_points_spin.value()
        query_mode = self.query_mode_combo.currentData()
        
        if start_time >= end_time:
            QMessageBox.warning(self, "Error", "Start time must be before end time")
            return
        
        if query_mode == "compare":
            self.query_compare_mode(tag_id, start_time, end_time, max_points)
        else:
            self.query_single_mode(tag_id, start_time, end_time, max_points, query_mode)
    
    def query_single_mode(self, tag_id, start_time, end_time, max_points, query_mode):
        """Execute single query (optimized or standard)"""
        self.status_label.setText(f"Status: Querying data for {tag_id} ({query_mode} mode)...")
        self.status_label.setStyleSheet("padding: 5px; background-color: #fff9c4;")
        QApplication.processEvents()
        
        query_start_time = time.time()
        
        try:
            cursor = self.connection.cursor()
            
            if query_mode == "optimized":
                rows, display_message = self.execute_optimized_query(cursor, tag_id, start_time, end_time, max_points)
            else:
                rows, display_message = self.execute_standard_query(cursor, tag_id, start_time, end_time, max_points)
            
            query_time = time.time() - query_start_time
            cursor.close()
            
            if not rows:
                QMessageBox.information(self, "No Data", "Query returned no results")
                return
            
            self.current_data = rows
            self.display_data(rows, tag_id, display_message + f" [{query_mode.upper()}]", query_time)
            self.export_btn.setEnabled(True)
            
        except Exception as e:
            QMessageBox.critical(self, "Query Error", f"Failed to query data:\n{e}")
            self.status_label.setText(f"Status: Query failed - {e}")
            self.status_label.setStyleSheet("padding: 5px; background-color: #ffcdd2;")
    
    def execute_optimized_query(self, cursor, tag_id, start_time, end_time, max_points):
        """Execute TimescaleDB-native optimized query with time_bucket"""
        # Calculate bucket size based on time range and max points
        time_range_seconds = (end_time - start_time).total_seconds()
        bucket_size = max(1, int(time_range_seconds / max_points))
        bucket_interval = f'{bucket_size} seconds'
        
        # Pure TimescaleDB query - no COUNT, no MODE, no subqueries
        cursor.execute("""
            SELECT
                time_bucket(%s, opc_timestamp) AS ts,
                AVG(value_num) AS value,
                MAX(quality) AS quality,
                %s AS tag_id,
                time_bucket(%s, opc_timestamp) AS opc_timestamp
            FROM historian_raw.historian_timeseries
            WHERE tag_id = %s
            AND opc_timestamp >= %s
            AND opc_timestamp < %s
            GROUP BY ts
            ORDER BY ts
        """, (bucket_interval, tag_id, bucket_interval, tag_id, start_time, end_time))
        
        rows = cursor.fetchall()
        return rows, f"TimescaleDB time_bucket: {len(rows):,} points (bucket: {bucket_size}s)"
    
    def execute_standard_query(self, cursor, tag_id, start_time, end_time, max_points):
        """Execute standard query with simple LIMIT"""
        cursor.execute("""
            SELECT opc_timestamp, value_num, quality, tag_id, opc_timestamp
            FROM historian_raw.historian_timeseries
            WHERE tag_id = %s 
            AND opc_timestamp >= %s AND opc_timestamp < %s
            ORDER BY opc_timestamp
            LIMIT %s
        """, (tag_id, start_time, end_time, max_points))
        
        rows = cursor.fetchall()
        return rows, f"Standard query: {len(rows):,} points (LIMIT {max_points:,})"
    
    def query_compare_mode(self, tag_id, start_time, end_time, max_points):
        """Compare optimized vs standard query performance"""
        self.status_label.setText(f"Status: Running comparison for {tag_id}...")
        self.status_label.setStyleSheet("padding: 5px; background-color: #fff9c4;")
        QApplication.processEvents()
        
        try:
            cursor = self.connection.cursor()
            
            # Run optimized query
            opt_start = time.time()
            opt_rows, opt_msg = self.execute_optimized_query(cursor, tag_id, start_time, end_time, max_points)
            opt_time = time.time() - opt_start
            
            if not opt_rows:
                QMessageBox.information(self, "No Data", f"No data found for {tag_id}")
                return
            
            # Run standard query
            std_start = time.time()
            std_rows, std_msg = self.execute_standard_query(cursor, tag_id, start_time, end_time, max_points)
            std_time = time.time() - std_start
            
            cursor.close()
            
            # Show comparison
            speedup = (std_time / opt_time) if opt_time > 0 else 1
            comparison_msg = (
                f"⚡ Performance Comparison\n\n"
                f"🚀 Optimized (time_bucket): {opt_time:.3f}s - {len(opt_rows):,} points\n"
                f"📊 Standard (LIMIT): {std_time:.3f}s - {len(std_rows):,} points\n\n"
                f"Speedup: {speedup:.2f}x {'faster' if speedup > 1 else 'slower'}\n"
                f"Time saved: {abs(std_time - opt_time):.3f}s"
            )
            
            QMessageBox.information(self, "Query Comparison", comparison_msg)
            
            # Display optimized results
            self.current_data = opt_rows
            self.display_data(opt_rows, tag_id, f"{opt_msg} [OPTIMIZED]", opt_time)
            self.export_btn.setEnabled(True)
            
        except Exception as e:
            QMessageBox.critical(self, "Comparison Error", f"Failed to compare queries:\n{e}")
            self.status_label.setText(f"Status: Comparison failed - {e}")
            self.status_label.setStyleSheet("padding: 5px; background-color: #ffcdd2;")
            
    def display_data(self, rows, tag_id, message, query_time):
        """Display data in chart and table"""
        # Start display timing
        display_start_time = time.time()
        
        # Extract data
        timestamps = []
        values = []
        qualities = []
        
        for row in rows:
            timestamp, value_num, quality, _, _ = row
            try:
                # Use timestamp for X-axis
                timestamps.append(timestamp.timestamp())
                values.append(float(value_num) if value_num is not None else None)
                qualities.append(quality)
            except Exception as e:
                continue
        
        if not timestamps:
            QMessageBox.warning(self, "Error", "No valid data to display")
            return
            
        # Clear previous plot
        self.chart_widget.clear()
        
        # Plot data
        if self.show_points_cb.isChecked():
            # Line with points
            self.chart_widget.plot(
                timestamps, 
                values, 
                pen=pg.mkPen(color='b', width=2),
                symbol='o',
                symbolSize=5,
                symbolBrush='b',
                name=tag_id
            )
        else:
            # Line only
            self.chart_widget.plot(
                timestamps, 
                values, 
                pen=pg.mkPen(color='b', width=2),
                name=tag_id
            )
        
        # Update title
        self.chart_widget.setTitle(f"Trend: {tag_id} - {message}")
        
        # Update table (show last 100 rows)
        self.data_table.setRowCount(0)
        display_rows = rows[-100:] if len(rows) > 100 else rows
        
        for i, row in enumerate(display_rows):
            timestamp, value_num, quality, tag_id_row, _ = row
            self.data_table.insertRow(i)
            self.data_table.setItem(i, 0, QTableWidgetItem(str(timestamp)))
            self.data_table.setItem(i, 1, QTableWidgetItem(f"{value_num:.4f}" if value_num is not None else "NULL"))
            self.data_table.setItem(i, 2, QTableWidgetItem(str(quality)))
            self.data_table.setItem(i, 3, QTableWidgetItem(tag_id))
            self.data_table.setItem(i, 4, QTableWidgetItem(str(timestamp)))
        
        # Calculate display time
        display_time = time.time() - display_start_time
        total_time = query_time + display_time
        
        # Update status
        avg_value = np.nanmean([v for v in values if v is not None])
        min_value = np.nanmin([v for v in values if v is not None])
        max_value = np.nanmax([v for v in values if v is not None])
        
        self.status_label.setText(
            f"Status: {message} | Avg: {avg_value:.4f} | Min: {min_value:.4f} | Max: {max_value:.4f} | "
            f"⏱️ Query: {query_time:.3f}s | Display: {display_time:.3f}s | Total: {total_time:.3f}s"
        )
        self.status_label.setStyleSheet("padding: 5px; background-color: #c8e6c9;")
        
    def export_to_csv(self):
        """Export current data to CSV file"""
        if not self.current_data:
            QMessageBox.warning(self, "Error", "No data to export")
            return
            
        from PyQt5.QtWidgets import QFileDialog
        
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Data",
            f"tag_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV Files (*.csv)"
        )
        
        if filename:
            try:
                import csv
                with open(filename, 'w', newline='') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(['Timestamp', 'Value', 'Quality', 'Tag ID', 'Source'])
                    writer.writerows(self.current_data)
                    
                QMessageBox.information(self, "Success", f"Data exported to:\n{filename}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export data:\n{e}")
                
    def closeEvent(self, event):
        """Clean up on close"""
        if self.connection:
            self.connection.close()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    viewer = TagTrendViewer()
    viewer.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
