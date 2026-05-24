"""
Background Service for Parquet Data Import
Monitors parquet directory and imports new data to PostgreSQL
"""

import os
import sys
import time
import logging
from datetime import datetime
from pathlib import Path
import psycopg2
from psycopg2.extras import execute_batch
import pandas as pd
import hashlib
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.config_manager import get_config_manager
from services.parquet_reader import SafeParquetReader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('parquet_importer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ParquetImporter:
    """Manages parquet file imports to PostgreSQL"""
    
    def __init__(self):
        self.config_manager = get_config_manager()
        self.parquet_reader = SafeParquetReader()
        self.processed_files = set()
        self.load_processed_files()
        
    def load_processed_files(self):
        """Load list of already processed files"""
        cache_file = Path('processed_files.txt')
        if cache_file.exists():
            with open(cache_file, 'r') as f:
                self.processed_files = set(f.read().splitlines())
            logger.info(f"Loaded {len(self.processed_files)} processed files from cache")
    
    def save_processed_file(self, file_path):
        """Save processed file to cache"""
        self.processed_files.add(file_path)
        with open('processed_files.txt', 'a') as f:
            f.write(f"{file_path}\n")
    
    def get_db_connection(self):
        """Get database connection"""
        db_config = self.config_manager.get_db_config()
        return psycopg2.connect(
            host=db_config.get('host', 'localhost'),
            port=db_config.get('port', 5432),
            database=db_config.get('database', 'Cereveate'),
            user=db_config.get('user', 'cereveate'),
            password=db_config.get('password', 'cereveate@222')
        )
    
    def calculate_file_hash(self, file_path):
        """Calculate SHA256 hash of file"""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def is_file_imported(self, file_path, file_hash):
        """Check if file was already imported"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) FROM file_imports 
            WHERE file_path = %s AND file_hash = %s
        """, (file_path, file_hash))
        
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        
        return count > 0
    
    def import_parquet_file(self, file_path):
        """Import a single parquet file to database"""
        try:
            logger.info(f"Processing file: {file_path}")
            
            # Check if file is ready (not being written)
            if not self.parquet_reader.is_file_ready(file_path):
                logger.warning(f"File not ready (still being written): {file_path}")
                return False
            
            # Calculate file hash
            file_hash = self.calculate_file_hash(file_path)
            
            # Check if already imported
            if self.is_file_imported(file_path, file_hash):
                logger.info(f"File already imported: {file_path}")
                return True
            
            # Read parquet file
            logger.info(f"Reading parquet file: {file_path}")
            df, checksum = self.parquet_reader.read_with_checksum(file_path)
            
            if df is None:
                logger.error(f"Failed to read parquet file: {file_path}")
                return False
            
            logger.info(f"Read {len(df)} records from {file_path}")
            
            # Get tag mappings
            tag_mappings = self.config_manager.get_enabled_tag_mappings()
            tag_map = {m['parquet_column']: m for m in tag_mappings}
            
            # ONLY process columns that user has mapped - no auto-discovery
            if not tag_map:
                logger.warning(f"No tag mappings configured. Please map tags in web UI first.")
                return False
            
            # Prepare data for insertion WITH SAMPLING FREQUENCY
            records = []
            
            # Get timestamp column
            timestamp_col = None
            for col in df.columns:
                if col.lower() in ['timestamp', 'time']:
                    timestamp_col = col
                    break
            
            if timestamp_col is None:
                logger.error(f"No timestamp column found in {file_path}")
                return False
            
            # Sort by timestamp
            df = df.sort_values(by=timestamp_col)
            
            # Process each mapped tag with its sampling frequency
            for col, mapping in tag_map.items():
                if col not in df.columns:
                    logger.warning(f"Column {col} not found in parquet file")
                    continue
                
                sampling_freq = mapping.get('sampling_frequency_seconds', 5)
                
                # Resample data based on frequency
                tag_data = df[[timestamp_col, col]].copy()
                tag_data = tag_data.dropna(subset=[col])
                
                if len(tag_data) == 0:
                    continue
                
                # Apply sampling frequency filter
                last_timestamp = None
                for _, row in tag_data.iterrows():
                    timestamp = row[timestamp_col]
                    value = row[col]
                    
                    # Skip if less than sampling frequency from last record
                    if last_timestamp is not None:
                        time_diff = (timestamp - last_timestamp).total_seconds()
                        if time_diff < sampling_freq:
                            continue
                    
                    last_timestamp = timestamp
                    
                    record = (
                        timestamp,                          # timestamp
                        datetime.now(),                     # ingest_timestamp
                        mapping.get('plant', 'Unknown'),    # plant
                        mapping.get('asset', 'Unknown'),    # asset
                        mapping.get('subsystem', 'Unknown'), # subsystem
                        mapping.get('tag_name', col),       # tag_name
                        col,                                # tag_code (original column name)
                        float(value),                       # value
                        value,                              # raw_value
                        mapping.get('unit', ''),            # unit
                        'GOOD',                             # quality_code
                        'ACTIVE',                           # status_flag
                        'PARQUET_IMPORT',                   # data_source
                        f"{mapping.get('plant', 'Unknown')}_{col}", # sensor_id
                        None,                               # shift
                        os.path.basename(file_path)         # batch_id
                    )
                    records.append(record)
            
            if not records:
                logger.warning(f"No records to import from {file_path}")
                return False
            
            logger.info(f"Prepared {len(records)} records for insertion")
            
            # Insert into database
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            try:
                # Batch insert
                batch_size = self.config_manager.config.get('import_settings', {}).get('batch_size', 10000)
                
                insert_query = """
                    INSERT INTO sensor_data (
                        timestamp, ingest_timestamp, plant, asset, subsystem,
                        tag_name, tag_code, value, raw_value, unit,
                        quality_code, status_flag, data_source, sensor_id, shift, batch_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                execute_batch(cursor, insert_query, records, page_size=batch_size)
                conn.commit()
                
                logger.info(f"Inserted {len(records)} records successfully")
                
                # Record import in file_imports table
                cursor.execute("""
                    INSERT INTO file_imports (
                        file_path, file_hash, file_size, import_timestamp,
                        records_imported, status
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    file_path,
                    file_hash,
                    os.path.getsize(file_path),
                    datetime.now(),
                    len(records),
                    'SUCCESS'
                ))
                conn.commit()
                
                # Save to processed files cache
                self.save_processed_file(file_path)
                
                logger.info(f"Successfully imported {file_path}")
                return True
                
            except Exception as e:
                conn.rollback()
                logger.error(f"Database error while importing {file_path}: {e}")
                
                # Record failed import
                cursor.execute("""
                    INSERT INTO file_imports (
                        file_path, file_hash, file_size, import_timestamp,
                        records_imported, status, error_message
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    file_path,
                    file_hash,
                    os.path.getsize(file_path),
                    datetime.now(),
                    0,
                    'FAILED',
                    str(e)
                ))
                conn.commit()
                
                return False
                
            finally:
                cursor.close()
                conn.close()
                
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
            return False
    
    def scan_and_import_directory(self):
        """Scan directory and import all parquet files"""
        parquet_config = self.config_manager.get_parquet_source_config()
        data_dir = parquet_config.get('data_directory')
        
        if not os.path.exists(data_dir):
            logger.error(f"Data directory not found: {data_dir}")
            return
        
        logger.info(f"Scanning directory: {data_dir}")
        
        # Find all parquet files
        parquet_files = []
        for file_name in os.listdir(data_dir):
            if file_name.endswith('.parquet'):
                file_path = os.path.join(data_dir, file_name)
                parquet_files.append(file_path)
        
        logger.info(f"Found {len(parquet_files)} parquet files")
        
        # Import each file
        success_count = 0
        for file_path in sorted(parquet_files):
            if self.import_parquet_file(file_path):
                success_count += 1
        
        logger.info(f"Import complete: {success_count}/{len(parquet_files)} files imported successfully")


class ParquetFileHandler(FileSystemEventHandler):
    """Handles file system events for parquet directory"""
    
    def __init__(self, importer):
        self.importer = importer
        self.pending_files = {}
    
    def on_created(self, event):
        if event.is_directory:
            return
        
        if event.src_path.endswith('.parquet'):
            logger.info(f"New parquet file detected: {event.src_path}")
            # Wait a bit for file to be fully written
            self.pending_files[event.src_path] = time.time()
    
    def on_modified(self, event):
        if event.is_directory:
            return
        
        if event.src_path.endswith('.parquet'):
            # Update timestamp
            self.pending_files[event.src_path] = time.time()
    
    def process_pending_files(self):
        """Process files that haven't been modified for a while"""
        current_time = time.time()
        stability_wait = self.importer.config_manager.get_parquet_source_config().get('stability_wait_seconds', 5)
        
        to_process = []
        for file_path, last_modified in list(self.pending_files.items()):
            if current_time - last_modified > stability_wait:
                to_process.append(file_path)
                del self.pending_files[file_path]
        
        for file_path in to_process:
            self.importer.import_parquet_file(file_path)


def create_file_imports_table():
    """Create file_imports table if it doesn't exist"""
    config_manager = get_config_manager()
    db_config = config_manager.get_db_config()
    
    conn = psycopg2.connect(
        host=db_config.get('host', 'localhost'),
        port=db_config.get('port', 5432),
        database=db_config.get('database', 'Cereveate'),
        user=db_config.get('user', 'cereveate'),
        password=db_config.get('password', 'cereveate@222')
    )
    
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS file_imports (
            id SERIAL PRIMARY KEY,
            file_path TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            file_size BIGINT,
            import_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            records_imported INTEGER DEFAULT 0,
            status TEXT DEFAULT 'PENDING',
            error_message TEXT,
            UNIQUE(file_path, file_hash)
        )
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_file_imports_timestamp 
        ON file_imports(import_timestamp DESC)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_file_imports_status 
        ON file_imports(status)
    """)
    
    conn.commit()
    cursor.close()
    conn.close()
    
    logger.info("file_imports table created/verified")


def create_tag_catalog_table():
    """Create tag_catalog table if it doesn't exist"""
    config_manager = get_config_manager()
    db_config = config_manager.get_db_config()
    
    conn = psycopg2.connect(
        host=db_config.get('host', 'localhost'),
        port=db_config.get('port', 5432),
        database=db_config.get('database', 'Cereveate'),
        user=db_config.get('user', 'cereveate'),
        password=db_config.get('password', 'cereveate@222')
    )
    
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tag_catalog (
            tag_id TEXT PRIMARY KEY,
            first_seen TIMESTAMPTZ NOT NULL,
            last_seen TIMESTAMPTZ NOT NULL,
            last_file TEXT
        )
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tag_catalog_last_seen 
        ON tag_catalog(last_seen DESC)
    """)
    
    conn.commit()
    cursor.close()
    conn.close()
    
    logger.info("tag_catalog table created/verified")


def main():
    """Main entry point for background importer"""
    logger.info("=" * 60)
    logger.info("Cereveate Parquet Importer - Background Service")
    logger.info("=" * 60)
    
    # Create file_imports table
    create_file_imports_table()
    
    # Initialize importer
    importer = ParquetImporter()
    
    # Initial scan and import
    logger.info("Performing initial directory scan...")
    importer.scan_and_import_directory()
    
    # Set up file watcher
    parquet_config = importer.config_manager.get_parquet_source_config()
    watch_directory = parquet_config.get('data_directory')
    check_interval = parquet_config.get('check_interval_seconds', 10)
    
    logger.info(f"Starting file watcher on: {watch_directory}")
    logger.info(f"Check interval: {check_interval} seconds")
    
    event_handler = ParquetFileHandler(importer)
    observer = Observer()
    observer.schedule(event_handler, watch_directory, recursive=False)
    observer.start()
    
    try:
        while True:
            # Process pending files periodically
            event_handler.process_pending_files()
            time.sleep(check_interval)
            
    except KeyboardInterrupt:
        logger.info("Shutdown requested...")
        observer.stop()
    
    observer.join()
    logger.info("Importer stopped")


if __name__ == "__main__":
    main()
