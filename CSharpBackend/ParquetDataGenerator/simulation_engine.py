"""
Simulation Engine - Generates realistic turbine plant data with downtimes
Thread-safe background service
"""
import threading
import time
import random
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from datetime import datetime
import os
import json
from pathlib import Path


class SimulationEngine:
    def __init__(self, config):
        self.config = config
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        
        # Simulation state
        self.is_downtime = False
        self.downtime_end_time = None
        self.current_file_path = None
        self.current_file_size = 0
        self.max_file_size = config['Simulation']['FileRotationSizeMB'] * 1024 * 1024
        
        # Statistics
        self.total_records = 0
        self.total_files = 0
        self.downtime_events = 0
        self.last_update_time = None
        
        # Tag parameters
        self.tags = config['Tags']
        self.tag_params = config['TagParameters']
        
        # Ensure output directory exists
        self.output_dir = Path(config['Paths']['SimulationOutputDirectory'])
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def start(self):
        """Start simulation in background thread"""
        if self.running:
            return False
        
        self.running = True
        self.thread = threading.Thread(target=self._simulation_loop, daemon=True)
        self.thread.start()
        return True
    
    def stop(self):
        """Stop simulation"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        return True
    
    def _simulation_loop(self):
        """Main simulation loop"""
        print(f"[SimulationEngine] Started - Writing to {self.output_dir}")
        
        while self.running:
            try:
                # Check downtime status
                self._update_downtime_status()
                
                # Generate data for all tags
                timestamp = datetime.now()
                records = []
                
                for tag in self.tags:
                    value = self._generate_tag_value(tag)
                    records.append({
                        'Timestamp': timestamp,
                        'TagId': tag,
                        'Value': value
                    })
                
                # Write to parquet
                self._write_records(records)
                
                # Update statistics
                with self.lock:
                    self.total_records += len(records)
                    self.last_update_time = timestamp
                
                # Sleep for configured interval
                time.sleep(self.config['Simulation']['IntervalSeconds'])
                
            except Exception as e:
                print(f"[SimulationEngine] Error: {e}")
                time.sleep(1)
    
    def _update_downtime_status(self):
        """Update downtime status"""
        if not self.config['Simulation']['DowntimeEnabled']:
            return
        
        current_time = time.time()
        
        # Check if downtime ended
        if self.is_downtime and self.downtime_end_time:
            if current_time >= self.downtime_end_time:
                print("[SimulationEngine] ⚡ Plant RESTARTED - Normal operation resumed")
                self.is_downtime = False
                self.downtime_end_time = None
        
        # Check if new downtime should start
        elif not self.is_downtime:
            if random.random() < self.config['Simulation']['DowntimeProbability']:
                duration_range = self.config['Simulation']['DowntimeDurationSeconds']
                duration = random.randint(duration_range[0], duration_range[1])
                self.downtime_end_time = current_time + duration
                self.is_downtime = True
                
                with self.lock:
                    self.downtime_events += 1
                
                print(f"[SimulationEngine] 🔴 DOWNTIME STARTED - Duration: {duration}s")
    
    def _generate_tag_value(self, tag):
        """Generate realistic tag value with downtime simulation"""
        params = self.tag_params.get(tag, {'mean': 50, 'std_dev': 5, 'min': 0, 'max': 100})
        
        # During downtime, critical parameters go to 0 or null
        if self.is_downtime:
            # Load and speed go to 0
            if tag in ['GENERATOR_LOAD_MW', 'TURBINE_SPEED']:
                return 0.0
            
            # Random tags return null (simulate sensor loss)
            if random.random() < 0.3:
                return None
            
            # Other tags drop significantly
            if 'VIB' in tag:
                return round(random.uniform(0, params['min']), 2)
            if 'TEMP' in tag:
                return round(random.uniform(params['min'], params['mean'] * 0.6), 2)
            if 'PRESSURE' in tag:
                return round(random.uniform(params['min'], params['mean'] * 0.5), 2)
        
        # Normal operation - generate realistic values
        value = np.random.normal(params['mean'], params['std_dev'])
        
        # Add occasional spikes (outliers)
        if random.random() < 0.001:  # 0.1% chance
            value = value * random.uniform(1.5, 2.5)
        
        # Clamp to min/max
        value = max(params['min'], min(params['max'], value))
        
        return round(value, 2)
    
    def _write_records(self, records):
        """Write records to parquet file (thread-safe) - matches existing format"""
        # Convert to DataFrame with exact schema as existing file
        df = pd.DataFrame(records)
        
        # Add RowId column (will be recalculated when merging)
        df['RowId'] = range(1, len(df) + 1)
        
        # Add Quality column - "GOOD" for normal values, "BAD" for null/downtime
        df['Quality'] = df['Value'].apply(lambda x: 'BAD' if pd.isna(x) or x == 0 else 'GOOD')
        
        # Convert Value to string to match existing format
        df['Value'] = df['Value'].apply(lambda x: str(x) if not pd.isna(x) else '')
        
        # Reorder columns to match: RowId, TagId, Timestamp, Value, Quality
        df = df[['RowId', 'TagId', 'Timestamp', 'Value', 'Quality']]
        
        # Convert to pyarrow table with exact schema
        table = pa.Table.from_pandas(df, schema=pa.schema([
            ('RowId', pa.int64()),
            ('TagId', pa.string()),
            ('Timestamp', pa.timestamp('us')),
            ('Value', pa.string()),
            ('Quality', pa.string())
        ]))
        
        with self.lock:
            # Check if need new file
            if self.current_file_path is None or self.current_file_size >= self.max_file_size:
                self._create_new_file()
            
            # Append to current file
            try:
                # Read existing data
                if os.path.exists(self.current_file_path):
                    existing_table = pq.read_table(self.current_file_path)
                    combined_table = pa.concat_tables([existing_table, table])
                else:
                    combined_table = table
                
                # Write back
                pq.write_table(combined_table, self.current_file_path, compression='snappy')
                
                # Update file size
                self.current_file_size = os.path.getsize(self.current_file_path)
                
            except Exception as e:
                print(f"[SimulationEngine] Write error: {e}")
    
    def _create_new_file(self):
        """Create new parquet file"""
        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        filename = f"simulation_{timestamp_str}.parquet"
        self.current_file_path = self.output_dir / filename
        self.current_file_size = 0
        self.total_files += 1
        print(f"[SimulationEngine] 📁 New file: {filename}")
    
    def get_status(self):
        """Get current status (thread-safe)"""
        with self.lock:
            return {
                'running': self.running,
                'is_downtime': self.is_downtime,
                'total_records': self.total_records,
                'total_files': self.total_files,
                'downtime_events': self.downtime_events,
                'last_update': self.last_update_time.isoformat() if self.last_update_time else None,
                'current_file': os.path.basename(self.current_file_path) if self.current_file_path else None,
                'current_file_size_mb': round(self.current_file_size / 1024 / 1024, 2)
            }
