"""
Dynamic Simulation Engine - Auto-discovers tags from existing files
Thread-safe parquet file generation with downtime simulation
"""

import os
import time
import threading
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import numpy as np
from datetime import datetime
from pathlib import Path


class DynamicSimulationEngine:
    def __init__(self, config):
        self.config = config
        self.interval = config['Simulation']['IntervalSeconds']
        self.downtime_prob = config['Simulation']['DowntimeProbability']
        
        # Handle downtime duration as either single value or range
        downtime_dur = config['Simulation']['DowntimeDurationSeconds']
        if isinstance(downtime_dur, list):
            self.downtime_duration_min = downtime_dur[0]
            self.downtime_duration_max = downtime_dur[1]
        else:
            self.downtime_duration_min = downtime_dur
            self.downtime_duration_max = downtime_dur
            
        self.output_dir = config['Paths']['SimulationOutputDirectory']
        self.max_file_size = config['Simulation']['FileRotationSizeMB'] * 1024 * 1024
        self.main_data_dir = config['Paths']['MainDataDirectory']
        
        # Auto-discover tags from existing main data file
        self.tags = []
        self.tag_ranges = {}
        self._auto_discover_tags()
        
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        self.current_file = None
        self.writer = None
        self.current_file_size = 0
        self.write_count = 0  # Counter to trigger file rotation
        
        # Statistics
        self.stats = {
            'records_generated': 0,
            'files_created': 0,
            'downtime_events': 0,
            'last_update': None,
            'is_downtime': False,
            'current_file': None,
            'total_tags': len(self.tags)
        }
        
        # Ensure output directory exists
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
    
    def _auto_discover_tags(self):
        """Auto-discover tags from existing parquet files in main data directory"""
        print(f"[DynamicSimulation] 🔍 Auto-discovering tags from {self.main_data_dir}")
        
        try:
            # Look for existing parquet files
            main_files = list(Path(self.main_data_dir).glob('*.parquet'))
            
            if main_files:
                # Read first file to get tag list
                df = pd.read_parquet(str(main_files[0]))
                discovered_tags = sorted(df['TagId'].unique().tolist())
                
                print(f"[DynamicSimulation] ✓ Discovered {len(discovered_tags)} tags from {main_files[0].name}")
                
                # Use discovered tags
                self.tags = discovered_tags
                
                # Generate realistic ranges for each tag based on tag name
                for tag in self.tags:
                    self.tag_ranges[tag] = self._generate_range_for_tag(tag)
                
                print(f"[DynamicSimulation] ✓ Generated ranges for all {len(self.tags)} tags")
                
            else:
                # Fallback to config if no files exist
                print(f"[DynamicSimulation] ⚠ No existing files found, using config tags")
                self.tags = self.config.get('Tags', [])
                self.tag_ranges = self.config.get('TagRanges', {})
                
        except Exception as e:
            print(f"[DynamicSimulation] ⚠ Error discovering tags: {e}, using config")
            self.tags = self.config.get('Tags', [])
            self.tag_ranges = self.config.get('TagRanges', {})
    
    def _generate_range_for_tag(self, tag):
        """Generate realistic range based on tag name patterns"""
        tag_upper = tag.upper()
        
        # Bearing vibrations
        if 'BEARING' in tag_upper and 'VIB' in tag_upper:
            if 'IP_REAR' in tag_upper or 'IP-REAR' in tag_upper:
                return {"mean": 21, "std": 0.5, "min": 20, "max": 25}
            else:
                return {"mean": 20, "std": 2, "min": 15, "max": 30}
        
        # Shaft vibrations
        elif 'SHAFT' in tag_upper and 'VIB' in tag_upper:
            if 'HP_FRONT' in tag_upper or 'HP-FRONT' in tag_upper:
                if 'X' in tag_upper:
                    return {"mean": 180, "std": 40, "min": 100, "max": 370}
                else:
                    return {"mean": 150, "std": 35, "min": 90, "max": 350}
            elif 'HP_REAR' in tag_upper or 'HP-REAR' in tag_upper:
                if 'X' in tag_upper:
                    return {"mean": 210, "std": 30, "min": 150, "max": 300}
                else:
                    return {"mean": 190, "std": 25, "min": 140, "max": 250}
            elif 'IP_REAR' in tag_upper or 'IP-REAR' in tag_upper:
                if 'X' in tag_upper:
                    return {"mean": 135, "std": 15, "min": 100, "max": 200}
                else:
                    return {"mean": 100, "std": 18, "min": 70, "max": 160}
            else:
                return {"mean": 150, "std": 25, "min": 80, "max": 250}
        
        # Temperature tags
        elif 'TEMP' in tag_upper or 'TEMPERATURE' in tag_upper:
            if 'STEAM' in tag_upper or 'MS' in tag_upper:
                return {"mean": 540, "std": 5, "min": 520, "max": 560}
            elif 'OIL' in tag_upper:
                return {"mean": 45, "std": 3, "min": 38, "max": 55}
            else:
                return {"mean": 100, "std": 10, "min": 50, "max": 150}
        
        # Pressure tags
        elif 'PRESS' in tag_upper or 'PRESSURE' in tag_upper:
            if 'STEAM' in tag_upper or 'HP' in tag_upper or 'INLET' in tag_upper:
                return {"mean": 165, "std": 5, "min": 150, "max": 180}
            elif 'IP' in tag_upper:
                return {"mean": 40, "std": 3, "min": 30, "max": 50}
            elif 'OIL' in tag_upper:
                return {"mean": 2.5, "std": 0.2, "min": 2.0, "max": 3.0}
            else:
                return {"mean": 100, "std": 10, "min": 50, "max": 150}
        
        # Vacuum
        elif 'VACUUM' in tag_upper or 'CONDENSER' in tag_upper:
            return {"mean": 94, "std": 1, "min": 90, "max": 97}
        
        # Flow tags
        elif 'FLOW' in tag_upper:
            return {"mean": 1000, "std": 50, "min": 800, "max": 1200}
        
        # Load/Power
        elif 'LOAD' in tag_upper or 'MW' in tag_upper or 'POWER' in tag_upper:
            return {"mean": 210, "std": 15, "min": 180, "max": 270}
        
        # Frequency
        elif 'FREQ' in tag_upper or 'HZ' in tag_upper:
            return {"mean": 50.0, "std": 0.05, "min": 49.8, "max": 50.2}
        
        # NOx, O2, PPM (emissions)
        elif 'NOX' in tag_upper or 'PPM' in tag_upper:
            return {"mean": 50, "std": 10, "min": 20, "max": 100}
        
        elif 'O2' in tag_upper or 'OXYGEN' in tag_upper or 'LEVEL' in tag_upper:
            return {"mean": 3.5, "std": 0.5, "min": 2.0, "max": 5.0}
        
        # Micro meter (UM) vibration tags
        elif 'MICRO_METER' in tag_upper or '-UM' in tag_upper:
            return {"mean": 20, "std": 2, "min": 15, "max": 30}
        
        # Default fallback
        else:
            return {"mean": 50, "std": 5, "min": 0, "max": 100}
    
    def start(self):
        """Start simulation in background thread"""
        if self.running:
            return {'success': False, 'message': 'Simulation already running'}
        
        self.running = True
        with self.lock:
            self.stats['running'] = True
        self.thread = threading.Thread(target=self._simulation_loop, daemon=True)
        self.thread.start()
        return {'success': True, 'message': f'Simulation started with {len(self.tags)} tags'}
    
    def stop(self):
        """Stop simulation gracefully"""
        if not self.running:
            return {'success': False, 'message': 'Simulation not running'}
        
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        
        # Close current writer
        with self.lock:
            if self.writer:
                self.writer.close()
                self.writer = None
            self.stats['running'] = False
        
        return {'success': True, 'message': 'Simulation stopped'}
    
    def _simulation_loop(self):
        """Main simulation loop - runs in background thread"""
        print(f"[DynamicSimulation] Started simulation loop (interval={self.interval}s, tags={len(self.tags)})")
        
        while self.running:
            try:
                # Check if downtime should occur
                is_downtime = np.random.random() < self.downtime_prob
                
                if is_downtime:
                    self._simulate_downtime()
                else:
                    self._generate_normal_data()
                
                time.sleep(self.interval)
                
            except Exception as e:
                print(f"[DynamicSimulation] Error in simulation loop: {e}")
                time.sleep(1)
    
    def _simulate_downtime(self):
        """Simulate plant downtime (null/zero values)"""
        # Randomize downtime duration within range
        downtime_duration = np.random.randint(self.downtime_duration_min, self.downtime_duration_max + 1)
        
        with self.lock:
            self.stats['is_downtime'] = True
            self.stats['downtime_events'] += 1
        
        print(f"[DynamicSimulation] 🔴 DOWNTIME EVENT - Duration: {downtime_duration}s")
        
        downtime_start = time.time()
        while time.time() - downtime_start < downtime_duration and self.running:
            timestamp = datetime.now()
            
            # Generate downtime data (mostly nulls and zeros)
            data_rows = []
            for tag in self.tags:
                # Mix of null and zero values during downtime
                if 'LOAD' in tag.upper() or 'FREQ' in tag.upper():
                    value = 0  # Critical parameters go to zero
                else:
                    value = None if np.random.random() < 0.7 else 0  # 70% null, 30% zero
                
                data_rows.append({
                    'Timestamp': timestamp,
                    'TagId': tag,
                    'Value': value
                })
            
            self._write_to_parquet(data_rows)
            time.sleep(self.interval)
        
        with self.lock:
            self.stats['is_downtime'] = False
        
        print(f"[DynamicSimulation] ✅ DOWNTIME ENDED - Resuming normal operation")
    
    def _generate_normal_data(self):
        """Generate normal operating data"""
        timestamp = datetime.now()
        data_rows = []
        
        for tag in self.tags:
            tag_config = self.tag_ranges.get(tag, {'mean': 50, 'std': 5, 'min': 0, 'max': 100})
            
            # Generate value with normal distribution
            value = np.random.normal(tag_config['mean'], tag_config['std'])
            
            # Clip to min/max
            value = np.clip(value, tag_config['min'], tag_config['max'])
            
            # Round based on tag type
            if 'FREQ' in tag.upper():
                value = round(value, 2)
            elif 'PRESSURE' in tag.upper() and 'LUBE' in tag.upper():
                value = round(value, 2)
            else:
                value = round(value, 2)
            
            data_rows.append({
                'Timestamp': timestamp,
                'TagId': tag,
                'Value': value
            })
        
        self._write_to_parquet(data_rows)
        
        with self.lock:
            self.stats['records_generated'] += len(data_rows)
            self.stats['last_update'] = timestamp.isoformat()
    
    def _write_to_parquet(self, data_rows):
        """Thread-safe parquet file writing with daily rotation"""
        with self.lock:
            # Get current date for daily file rotation
            current_date = datetime.now().strftime('%Y%m%d')
            
            # Check if need new file (rotate daily OR on first write OR server restart)
            need_new_file = (
                self.writer is None or 
                self.current_file is None or
                current_date not in str(self.current_file)  # New day = new file
            )
            
            if need_new_file:
                self._rotate_file()
            
            # Convert to DataFrame
            df = pd.DataFrame(data_rows)
            
            # Convert timestamp to microsecond precision (not nanosecond)
            df['Timestamp'] = pd.to_datetime(df['Timestamp']).astype('datetime64[us]')
            
            # Convert to pyarrow Table with microsecond precision to match existing data
            table = pa.Table.from_pandas(df, schema=pa.schema([
                ('Timestamp', pa.timestamp('us')),  # Use microsecond precision
                ('TagId', pa.string()),
                ('Value', pa.float64())
            ]))
            
            # Append to in-memory buffer instead of writing to file
            if not hasattr(self, 'data_buffer'):
                self.data_buffer = []
            self.data_buffer.append(table)
            self.write_count += 1  # Increment write counter
            
            # Update file size estimate
            self.current_file_size += len(data_rows) * 50  # Rough estimate
    
    def _rotate_file(self):
        """Create or APPEND to daily parquet file (thread-safe, must be called within lock)"""
        # Generate daily filename (ONE file per day)
        date_str = datetime.now().strftime('%Y%m%d')
        filename = f"simulation_{date_str}.parquet"
        
        # Write buffered data to daily file (append if exists, create if new)
        if hasattr(self, 'data_buffer') and self.data_buffer:
            temp_filepath = os.path.join(self.output_dir, f"{filename}.tmp")
            final_filepath = os.path.join(self.output_dir, filename)
            
            # Combine all buffered tables
            new_table = pa.concat_tables(self.data_buffer)
            
            # If daily file already exists, merge with it
            if os.path.exists(final_filepath):
                try:
                    # Read existing file
                    existing_table = pq.read_table(final_filepath)
                    # Combine with new data
                    combined_table = pa.concat_tables([existing_table, new_table])
                    
                    # Write combined data to temp file
                    pq.write_table(combined_table, temp_filepath, compression='snappy')
                    
                    # Delete old file and rename temp (atomic update)
                    os.remove(final_filepath)
                    os.rename(temp_filepath, final_filepath)
                    
                    print(f"[DynamicSimulation] 📁 Daily file appended: {filename} ({len(new_table)} new records, {len(combined_table)} total)")
                except Exception as e:
                    print(f"[DynamicSimulation] Error appending to daily file: {e}")
                    # If merge fails, just write new data
                    pq.write_table(new_table, temp_filepath, compression='snappy')
                    os.remove(final_filepath)
                    os.rename(temp_filepath, final_filepath)
            else:
                # New daily file - just write it
                pq.write_table(new_table, temp_filepath, compression='snappy')
                os.rename(temp_filepath, final_filepath)
                print(f"[DynamicSimulation] 📁 New daily file created: {filename} ({len(new_table)} records)")
            
            self.stats['files_created'] += 1
            self.stats['current_file'] = filename
        
        # Reset buffer for next batch
        self.data_buffer = []
        self.current_file = filename
        self.current_file_size = 0
        self.write_count = 0  # Reset write counter
        self.writer = True  # Dummy value to indicate writer is active
    
    def get_stats(self):
        """Get current simulation statistics"""
        with self.lock:
            stats = self.stats.copy()
            stats['running'] = self.running
            return stats
