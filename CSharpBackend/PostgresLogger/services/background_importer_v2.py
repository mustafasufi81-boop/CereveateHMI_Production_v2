"""
Background Service for Parquet Data Import
Monitors parquet directory and imports new data to PostgreSQL
Maintains tag_catalog and file_imports tracking tables
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
import pyarrow.parquet as pq
import hashlib
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.config_manager import get_config_manager

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
    """Manages parquet file imports to PostgreSQL with tag catalog"""
    
    def __init__(self):
        self.config_manager = get_config_manager()
        self._last_ts_per_tag = {}  # Track last timestamp for sampling frequency
        self._last_catalog_refresh = 0  # Unix timestamp of last catalog update
        self.create_tag_catalog_table()
        
    def get_db_connection(self):
        """Get database connection from config"""
        db_config = self.config_manager.config['database']
        return psycopg2.connect(
            host=db_config['host'],
            port=db_config['port'],
            database=db_config['database'],
            user=db_config['user'],
            password=db_config['password']
        )
    
    def create_tag_catalog_table(self):
        """Create tag_catalog table if not exists"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Create tag_catalog table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tag_catalog (
                    tag_id TEXT PRIMARY KEY,
                    first_seen TIMESTAMPTZ NOT NULL,
                    last_seen TIMESTAMPTZ NOT NULL,
                    last_file TEXT
                )
            """)
            
            # Create index for sorting by last_seen
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_tag_catalog_last_seen 
                ON tag_catalog(last_seen DESC)
            """)
            
            conn.commit()
            cursor.close()
            conn.close()
            logger.info("Tag catalog table verified/created")
            
        except Exception as e:
            logger.error(f"Error creating tag_catalog table: {e}")
            raise
    
    def calculate_file_hash(self, file_path):
        """Calculate hash of file for change detection"""
        try:
            hash_md5 = hashlib.md5()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            logger.error(f"Error calculating hash for {file_path}: {e}")
            return None
    
    def get_imported_tags(self, file_path, file_hash):
        """Get list of tags already imported from this file with this hash"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT tag_id 
                FROM tag_imports 
                WHERE file_path = %s AND file_hash = %s
            """, (file_path, file_hash))
            
            results = cursor.fetchall()
            cursor.close()
            conn.close()
            
            return set(row[0] for row in results)
            
        except Exception as e:
            logger.error(f"Error getting imported tags: {e}")
            return set()
    
    def get_tags_to_import(self, file_path, file_hash, tags_in_file, mapped_tags):
        """Determine which tags need to be imported from this file"""
        # Tags that are both in file AND mapped
        available_mapped_tags = tags_in_file.intersection(mapped_tags)
        
        # Tags already imported from this file+hash
        already_imported = self.get_imported_tags(file_path, file_hash)
        
        # Import only tags that haven't been imported yet
        tags_to_import = available_mapped_tags - already_imported
        
        return tags_to_import, already_imported
    
    def _normalize_column_name(self, col_name):
        """Normalize column name for matching"""
        return col_name.strip().lower()
    
    def _find_column(self, df, possible_names):
        """Find column by multiple possible names (case-insensitive)"""
        columns_lower = {self._normalize_column_name(c): c for c in df.columns}
        for name in possible_names:
            normalized = self._normalize_column_name(name)
            if normalized in columns_lower:
                return columns_lower[normalized]
        return None
    
    def extract_tag_ids(self, df, is_long_format):
        """Extract distinct TagIds from dataframe"""
        try:
            if is_long_format:
                # Long format: TagId column (case-insensitive)
                tag_col = self._find_column(df, ['TagId', 'tagid', 'tag_id', 'TAG_ID'])
                if tag_col:
                    return set(df[tag_col].dropna().unique())
                else:
                    logger.warning("Long format detected but no TagId column found")
                    return set()
            else:
                # Wide format: column names are tags (exclude Timestamp)
                ts_col = self._find_column(df, ['Timestamp', 'timestamp', 'time', 'datetime', 'ts'])
                tag_cols = [col for col in df.columns if col != ts_col]
                return set(tag_cols)
                
        except Exception as e:
            logger.error(f"Error extracting tag IDs: {e}")
            return set()
    
    def upsert_tag_catalog(self, tag_ids, file_path, df, is_long_format):
        """Update tag_catalog with discovered tags"""
        if not tag_ids:
            return
        
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Get timestamp from data for first_seen/last_seen
            ts_col = self._find_column(df, ['Timestamp', 'timestamp', 'time', 'datetime', 'ts'])
            if ts_col:
                timestamps = pd.to_datetime(df[ts_col], errors='coerce').dropna()
                if len(timestamps) > 0:
                    min_ts = timestamps.min()
                    max_ts = timestamps.max()
                else:
                    min_ts = max_ts = datetime.now()
            else:
                min_ts = max_ts = datetime.now()
            
            # Calculate file hash and size
            file_hash = self.calculate_file_hash(file_path)
            file_size = os.path.getsize(file_path)
            
            # Upsert each tag into tag_catalog
            for tag_id in tag_ids:
                cursor.execute("""
                    INSERT INTO tag_catalog (tag_id, first_seen, last_seen, last_file)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (tag_id) DO UPDATE SET
                        first_seen = LEAST(tag_catalog.first_seen, EXCLUDED.first_seen),
                        last_seen = GREATEST(tag_catalog.last_seen, EXCLUDED.last_seen),
                        last_file = EXCLUDED.last_file
                """, (tag_id, min_ts, max_ts, file_path))
                
                # Count records for this tag in this file
                if is_long_format:
                    record_count = len(df[df['TagId'] == tag_id]) if 'TagId' in df.columns else 0
                else:
                    record_count = len(df) if tag_id in df.columns else 0
                
                # Also update tag_file_catalog to track ALL files containing this tag
                cursor.execute("""
                    INSERT INTO tag_file_catalog (tag_id, file_path, file_hash, first_seen, last_seen, record_count, file_size_bytes, last_updated)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (tag_id, file_path, file_hash) DO UPDATE SET
                        first_seen = LEAST(tag_file_catalog.first_seen, EXCLUDED.first_seen),
                        last_seen = GREATEST(tag_file_catalog.last_seen, EXCLUDED.last_seen),
                        record_count = EXCLUDED.record_count,
                        last_updated = NOW()
                """, (tag_id, file_path, file_hash, min_ts, max_ts, record_count, file_size))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info(f"Updated tag catalog with {len(tag_ids)} tags from {file_path}")
            
        except Exception as e:
            logger.error(f"Error updating tag catalog: {e}")
    
    def get_tag_mappings(self):
        """Get tag mappings from config"""
        return self.config_manager.config.get('tag_mappings', [])
    
    def _coerce_numeric_value(self, value):
        """Coerce value to float, handling booleans and strings"""
        if pd.isna(value):
            return None
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if isinstance(value, str):
            value_lower = value.lower().strip()
            if value_lower in ('true', 'on', 'yes', '1'):
                return 1.0
            elif value_lower in ('false', 'off', 'no', '0'):
                return 0.0
            try:
                return float(value)
            except (ValueError, TypeError):
                return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    def process_long_format(self, df, tag_map, useful_tags, file_path):
        """Process long-format parquet and return records to insert"""
        records = []
        
        try:
            # Find columns
            tag_col = self._find_column(df, ['TagId', 'tagid', 'tag_id'])
            ts_col = self._find_column(df, ['Timestamp', 'timestamp', 'time', 'datetime'])
            val_col = self._find_column(df, ['Value', 'value', 'val'])
            
            if not tag_col or not ts_col or not val_col:
                logger.error(f"Required columns not found in {file_path}")
                return records
            
            # Filter to only mapped tags
            df_filtered = df[df[tag_col].isin(useful_tags)].copy()
            
            if len(df_filtered) == 0:
                return records
            
            # Convert timestamp (from parquet file - actual sensor reading time)
            df_filtered['_ts'] = pd.to_datetime(df_filtered[ts_col], errors='coerce')
            df_filtered['_tag'] = df_filtered[tag_col]
            df_filtered['_val'] = df_filtered[val_col]
            
            # Apply sampling frequency per tag
            for tag_id in useful_tags:
                tag_config = tag_map.get(tag_id)
                if not tag_config:
                    continue
                
                # Get mapping details (from config)
                plant = tag_config.get('plant', 'Unknown')
                asset = tag_config.get('asset', 'Unknown')
                subsystem = tag_config.get('subsystem', 'General')
                unit = tag_config.get('unit', '')
                sampling_freq = tag_config.get('sampling_frequency_seconds', 0)
                
                # Filter tag data
                tag_data = df_filtered[df_filtered['_tag'] == tag_id].copy()
                tag_data = tag_data.dropna(subset=['_ts', '_val'])
                tag_data = tag_data.sort_values('_ts')
                
                # Apply sampling frequency
                if sampling_freq > 0:
                    last_ts = self._last_ts_per_tag.get(tag_id)
                    
                    for _, row in tag_data.iterrows():
                        ts = row['_ts']
                        val = self._coerce_numeric_value(row['_val'])
                        if val is None:
                            continue
                        if last_ts is None or (ts - last_ts).total_seconds() >= sampling_freq:
                            records.append({
                                'timestamp': ts,
                                'tag_code': tag_id,
                                'tag_name': tag_config.get('tag_name', tag_id),
                                'plant': plant,
                                'asset': asset,
                                'subsystem': subsystem,
                                'unit': unit,
                                'value': val,
                                'quality_code': 192,
                                'status_flag': 'OK',
                                'data_source': 'OPC_DA'
                            })
                            self._last_ts_per_tag[tag_id] = ts
                else:
                    # Import all data points
                    for _, row in tag_data.iterrows():
                        val = self._coerce_numeric_value(row['_val'])
                        if val is None:
                            continue
                        records.append({
                            'timestamp': row['_ts'],
                            'tag_code': tag_id,
                            'tag_name': tag_config.get('tag_name', tag_id),
                            'plant': plant,
                            'asset': asset,
                            'subsystem': subsystem,
                            'unit': unit,
                            'value': val,
                            'quality_code': 192,
                            'status_flag': 'OK',
                            'data_source': 'OPC_DA'
                        })
                        self._last_ts_per_tag[tag_id] = row['_ts']
            
            return records
            
        except Exception as e:
            logger.error(f"Error processing long format: {e}")
            return []
    
    def process_wide_format(self, df, tag_map, useful_tags, file_path):
        """Process wide-format parquet and return records to insert"""
        records = []
        
        try:
            # Find timestamp column
            ts_col = self._find_column(df, ['Timestamp', 'timestamp', 'time', 'datetime', 'ts'])
            if not ts_col:
                logger.warning(f"No Timestamp column in {file_path}")
                return records
            
            df['_ts'] = pd.to_datetime(df[ts_col], errors='coerce')
            df = df.dropna(subset=['_ts'])
            df = df.sort_values('_ts')
            
            # Process each mapped tag column
            for tag_id in useful_tags:
                if tag_id not in df.columns:
                    continue
                
                tag_config = tag_map.get(tag_id)
                if not tag_config:
                    continue
                
                # Get mapping details (from config)
                plant = tag_config.get('plant', 'Unknown')
                asset = tag_config.get('asset', 'Unknown')
                subsystem = tag_config.get('subsystem', 'General')
                unit = tag_config.get('unit', '')
                sampling_freq = tag_config.get('sampling_frequency_seconds', 0)
                
                # Get non-null values
                tag_data = df[['_ts', tag_id]].dropna()
                
                # Apply sampling frequency
                if sampling_freq > 0:
                    last_ts = self._last_ts_per_tag.get(tag_id)
                    
                    for _, row in tag_data.iterrows():
                        ts = row['_ts']
                        val = self._coerce_numeric_value(row[tag_id])
                        if val is None:
                            continue
                        if last_ts is None or (ts - last_ts).total_seconds() >= sampling_freq:
                            records.append({
                                'timestamp': ts,
                                'tag_code': tag_id,
                                'tag_name': tag_config.get('tag_name', tag_id),
                                'plant': plant,
                                'asset': asset,
                                'subsystem': subsystem,
                                'unit': unit,
                                'value': val,
                                'quality_code': 192,
                                'status_flag': 'OK',
                                'data_source': 'OPC_DA'
                            })
                            self._last_ts_per_tag[tag_id] = ts
                else:
                    # Import all
                    for _, row in tag_data.iterrows():
                        val = self._coerce_numeric_value(row[tag_id])
                        if val is None:
                            continue
                        records.append({
                            'timestamp': row['_ts'],
                            'tag_code': tag_id,
                            'tag_name': tag_config.get('tag_name', tag_id),
                            'plant': plant,
                            'asset': asset,
                            'subsystem': subsystem,
                            'unit': unit,
                            'value': val,
                            'quality_code': 192,
                            'status_flag': 'OK',
                            'data_source': 'OPC_DA'
                        })
                        self._last_ts_per_tag[tag_id] = row['_ts']
            
            return records
            
        except Exception as e:
            logger.error(f"Error processing wide format: {e}")
            return []
    
    def log_tag_import(self, file_path, file_hash, tag_id, records_imported):
        """Log successful import of a specific tag from a file"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO tag_imports (file_path, file_hash, tag_id, records_imported)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (file_path, file_hash, tag_id) DO UPDATE SET
                    records_imported = EXCLUDED.records_imported,
                    import_timestamp = NOW()
            """, (file_path, file_hash, tag_id, records_imported))
            
            conn.commit()
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error logging tag import: {e}")
    
    def log_import_skipped(self, file_path, file_hash, file_size):
        """Log skipped import (no mapped tags)"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO file_imports (file_path, file_hash, file_size, records_imported, status)
                VALUES (%s, %s, %s, 0, 'SKIPPED')
                ON CONFLICT (file_path, file_hash) DO UPDATE SET
                    status = 'SKIPPED',
                    import_timestamp = NOW()
            """, (file_path, file_hash, file_size))
            
            conn.commit()
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error logging skipped import: {e}")
    
    def log_import_failure(self, file_path, file_hash, file_size, error_msg):
        """Log failed import"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO file_imports (file_path, file_hash, file_size, status, error_message)
                VALUES (%s, %s, %s, 'FAILED', %s)
                ON CONFLICT (file_path, file_hash) DO UPDATE SET
                    status = 'FAILED',
                    error_message = EXCLUDED.error_message,
                    import_timestamp = NOW()
            """, (file_path, file_hash, file_size, error_msg))
            
            conn.commit()
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error logging import failure: {e}")
    
    def import_parquet_file(self, file_path):
        """Import parquet file to PostgreSQL with full tracking"""
        try:
            logger.info(f"Processing file: {file_path}")
            
            # Calculate hash
            file_hash = self.calculate_file_hash(file_path)
            if not file_hash:
                logger.error(f"Could not calculate hash for {file_path}")
                return False
            
            file_size = os.path.getsize(file_path)
            
            # Read parquet first to check available tags
            # Read parquet
            try:
                df = pd.read_parquet(file_path)
            except Exception as e:
                error_msg = f"Could not read parquet: {e}"
                logger.error(error_msg)
                self.log_import_failure(file_path, file_hash, file_size, error_msg)
                return False
            
            if df.empty:
                logger.warning(f"Empty parquet file: {file_path}")
                self.log_import_skipped(file_path, file_hash, file_size)
                return True
            
            # Detect format (long vs wide)
            columns_lower = [c.lower() for c in df.columns]
            is_long_format = 'tagid' in columns_lower and 'timestamp' in columns_lower and 'value' in columns_lower
            
            logger.info(f"Format detected: {'LONG' if is_long_format else 'WIDE'}")
            
            # Extract all tag IDs
            tag_ids = self.extract_tag_ids(df, is_long_format)
            logger.info(f"Found {len(tag_ids)} unique tags")
            
            # Update tag catalog (always, even if no mapping)
            self.upsert_tag_catalog(tag_ids, file_path, df, is_long_format)
            
            # Get tag mappings (only enabled ones) with normalized matching
            tag_mappings = self.get_tag_mappings()
            tag_map = {}
            tag_map_normalized = {}
            for m in tag_mappings:
                if m.get('parquet_column') and m.get('enabled', True):
                    parquet_col = m['parquet_column']
                    tag_map[parquet_col] = m
                    tag_map_normalized[self._normalize_column_name(parquet_col)] = m
            
            # Match tags from file to mappings (case-insensitive)
            matched_tag_map = {}
            for tag_id in tag_ids:
                normalized_tag = self._normalize_column_name(tag_id)
                if normalized_tag in tag_map_normalized:
                    matched_tag_map[tag_id] = tag_map_normalized[normalized_tag]
            
            tag_map = matched_tag_map
            
            # Determine which tags need to be imported (tag-based logic)
            tags_to_import, already_imported = self.get_tags_to_import(
                file_path, file_hash, tag_ids, set(tag_map.keys())
            )
            
            if already_imported:
                logger.info(f"Already imported from this file: {already_imported}")
            
            if not tags_to_import:
                logger.info(f"No new tags to import from {file_path}")
                return True
            
            logger.info(f"Importing {len(tags_to_import)} tags: {tags_to_import}")
            
            # Process based on format
            if is_long_format:
                records = self.process_long_format(df, tag_map, tags_to_import, file_path)
            else:
                records = self.process_wide_format(df, tag_map, tags_to_import, file_path)
            
            if not records:
                logger.warning(f"No records extracted from {file_path}")
                return True
                
            # Insert to database
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            insert_query = """
                INSERT INTO sensor_data (timestamp, tag_code, tag_name, plant, asset, subsystem, unit, value, quality_code, status_flag, data_source)
                VALUES (%(timestamp)s, %(tag_code)s, %(tag_name)s, %(plant)s, %(asset)s, %(subsystem)s, %(unit)s, %(value)s, %(quality_code)s, %(status_flag)s, %(data_source)s)
                ON CONFLICT (timestamp, tag_code) DO NOTHING
            """
            
            execute_batch(cursor, insert_query, records, page_size=1000)
            conn.commit()
            
            inserted_count = cursor.rowcount
            cursor.close()
            conn.close()
            
            logger.info(f"Imported {inserted_count} records from {file_path}")
            
            # Log each tag import separately
            for tag_id in tags_to_import:
                tag_records = len([r for r in records if r['tag_code'] == tag_id])
                self.log_tag_import(file_path, file_hash, tag_id, tag_records)
                logger.info(f"  - {tag_id}: {tag_records} records")
            
            return True
            
        except Exception as e:
            logger.error(f"Error importing {file_path}: {e}", exc_info=True)
            if 'file_hash' in locals() and 'file_size' in locals():
                self.log_import_failure(file_path, file_hash, file_size, str(e))
            return False
    
    def refresh_tag_catalog(self):
        """Scan ALL parquet files and update tag catalog"""
        try:
            data_dir = self.config_manager.config['parquet_source']['data_directory']
            
            # Find ALL parquet files
            parquet_files = list(Path(data_dir).glob('*.parquet'))
            if not parquet_files:
                logger.debug("No parquet files found for catalog refresh")
                return
            
            logger.info(f"Refreshing tag catalog from {len(parquet_files)} files")
            
            # Process each file
            for file_path in parquet_files:
                try:
                    # Read parquet
                    df = pd.read_parquet(file_path)
                    if df.empty:
                        continue
                    
                    # Detect format and extract tags
                    columns_lower = [c.lower() for c in df.columns]
                    is_long_format = 'tagid' in columns_lower and 'timestamp' in columns_lower and 'value' in columns_lower
                    
                    tag_ids = self.extract_tag_ids(df, is_long_format)
                    
                    # Update catalog
                    self.upsert_tag_catalog(tag_ids, str(file_path), df, is_long_format)
                    
                except Exception as e:
                    logger.error(f"Error processing {file_path} for catalog: {e}")
            
            logger.info("Tag catalog refresh complete")
            
        except Exception as e:
            logger.error(f"Error refreshing tag catalog: {e}")
    
    def process_directory(self):
        """Process all parquet files in directory"""
        data_dir = self.config_manager.config['parquet_source']['data_directory']
        
        if not os.path.exists(data_dir):
            logger.warning(f"Data directory does not exist: {data_dir}")
            return
        
        parquet_files = list(Path(data_dir).glob('*.parquet'))
        logger.info(f"Found {len(parquet_files)} parquet files")
        
        for file_path in sorted(parquet_files):
            self.import_parquet_file(str(file_path))
            time.sleep(0.1)  # Small delay between files
    
    def verify_mapped_tags_have_data(self):
        """Check which mapped tags have zero records in sensor_data"""
        try:
            tag_mappings = self.get_tag_mappings()
            mapped_tag_codes = [m['parquet_column'] for m in tag_mappings if m.get('parquet_column') and m.get('enabled', True)]
            
            if not mapped_tag_codes:
                logger.info("No mapped tags to verify")
                return set()
            
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            missing_tags = set()
            for tag_code in mapped_tag_codes:
                cursor.execute("""
                    SELECT COUNT(*) FROM sensor_data WHERE tag_code = %s
                """, (tag_code,))
                count = cursor.fetchone()[0]
                if count == 0:
                    logger.warning(f"Mapped tag '{tag_code}' has ZERO records in sensor_data")
                    missing_tags.add(tag_code)
                else:
                    logger.info(f"Mapped tag '{tag_code}' has {count} records")
            
            cursor.close()
            conn.close()
            
            return missing_tags
            
        except Exception as e:
            logger.error(f"Error verifying mapped tags: {e}")
            return set()
    
    def force_reimport_for_tags(self, tag_codes):
        """Force re-import of specific tags from ALL files by clearing their import history"""
        try:
            if not tag_codes:
                return
            
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            for tag_code in tag_codes:
                cursor.execute("""
                    DELETE FROM tag_imports WHERE tag_id = %s
                """, (tag_code,))
                logger.info(f"Cleared import history for tag: {tag_code}")
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info(f"Force re-import enabled for {len(tag_codes)} tags")
            
        except Exception as e:
            logger.error(f"Error clearing import history: {e}")
    
    def reprocess_skipped_files(self):
        """Re-process files that were skipped due to no mapped tags"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT file_path FROM file_imports 
                WHERE status = 'SKIPPED' 
                ORDER BY import_timestamp DESC
            """)
            
            skipped_files = [row[0] for row in cursor.fetchall()]
            cursor.close()
            conn.close()
            
            if not skipped_files:
                logger.info("No skipped files to reprocess")
                return
            
            logger.info(f"Re-processing {len(skipped_files)} skipped file(s)")
            for file_path in skipped_files:
                if os.path.exists(file_path):
                    logger.info(f"Re-importing: {file_path}")
                    self.import_parquet_file(file_path)
                    time.sleep(0.1)
                    
        except Exception as e:
            logger.error(f"Error reprocessing skipped files: {e}")


class ParquetFileHandler(FileSystemEventHandler):
    """Handles file system events for new parquet files"""
    
    def __init__(self, importer, stability_wait=5):
        self.importer = importer
        self.stability_wait = stability_wait
        self._processing = set()  # Track files being processed
        
    def _process_file(self, file_path):
        """Process a parquet file with proper locking"""
        if file_path in self._processing:
            logger.debug(f"Already processing: {file_path}")
            return
        
        try:
            self._processing.add(file_path)
            logger.info(f"File event detected: {file_path}")
            
            # Wait for file to stabilize and verify size doesn't change
            time.sleep(self.stability_wait)
            
            if not os.path.exists(file_path):
                logger.warning(f"File disappeared: {file_path}")
                return
            
            # Double-check file is stable by comparing size
            initial_size = os.path.getsize(file_path)
            time.sleep(1)
            final_size = os.path.getsize(file_path)
            
            if initial_size != final_size:
                logger.warning(f"File still being written: {file_path}")
                time.sleep(3)
            
            self.importer.import_parquet_file(file_path)
            
        finally:
            self._processing.discard(file_path)
    
    def on_created(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith('.parquet'):
            self._process_file(event.src_path)
    
    def on_modified(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith('.parquet'):
            self._process_file(event.src_path)


def main():
    """Main entry point"""
    logger.info("Starting Parquet Importer Service")
    
    importer = ParquetImporter()
    
    # Initial directory scan
    logger.info("Processing existing files...")
    importer.process_directory()
    
    # Set up file watcher
    config_manager = get_config_manager()
    data_dir = config_manager.config['parquet_source']['data_directory']
    check_interval = config_manager.config['parquet_source'].get('check_interval_seconds', 10)
    stability_wait = config_manager.config['parquet_source'].get('stability_wait_seconds', 5)
    
    event_handler = ParquetFileHandler(importer, stability_wait)
    observer = Observer()
    observer.schedule(event_handler, data_dir, recursive=False)
    observer.start()
    
    logger.info(f"Watching directory: {data_dir}")
    logger.info("Press Ctrl+C to stop")
    
    try:
        last_catalog_refresh = 0
        last_config_check = 0
        last_verification = 0
        last_full_scan = 0
        catalog_refresh_interval = 300  # 5 minutes
        config_check_interval = 30  # 30 seconds
        verification_interval = 60  # 1 minute - check for missing data
        full_scan_interval = 600  # 10 minutes - full directory re-scan
        last_tag_count = len(importer.get_tag_mappings())
        
        while True:
            time.sleep(check_interval)
            
            current_time = time.time()
            
            # Refresh tag catalog periodically
            if current_time - last_catalog_refresh >= catalog_refresh_interval:
                logger.info("Performing periodic tag catalog refresh...")
                importer.refresh_tag_catalog()
                last_catalog_refresh = current_time
            
            # Check for new tag mappings
            if current_time - last_config_check >= config_check_interval:
                current_tag_count = len(importer.get_tag_mappings())
                if current_tag_count != last_tag_count:
                    logger.info(f"Tag mappings changed (now {current_tag_count}, was {last_tag_count}). Re-processing all files...")
                    # Re-process all files to check for new mapped tags
                    importer.process_directory()
                    last_tag_count = current_tag_count
                last_config_check = current_time
            
            # Verify all mapped tags have data in sensor_data
            if current_time - last_verification >= verification_interval:
                logger.info("Verifying all mapped tags have data...")
                missing_tags = importer.verify_mapped_tags_have_data()
                if missing_tags:
                    logger.warning(f"Found {len(missing_tags)} mapped tags with NO data. Force re-importing...")
                    importer.force_reimport_for_tags(missing_tags)
                    importer.process_directory()
                last_verification = current_time
            
            # Full directory re-scan to catch any missed files
            if current_time - last_full_scan >= full_scan_interval:
                logger.info("Performing full directory re-scan...")
                importer.process_directory()
                last_full_scan = current_time
                
    except KeyboardInterrupt:
        logger.info("Stopping importer...")
        observer.stop()
    
    observer.join()
    logger.info("Importer stopped")


if __name__ == "__main__":
    main()
