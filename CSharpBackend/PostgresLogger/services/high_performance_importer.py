"""
HIGH-PERFORMANCE PARQUET IMPORTER
Enterprise-ready importer for 10K+ tags with:
- Idempotent imports (file hash tracking)
- Selective tag import (mapped tags only)
- Efficient bulk inserts (COPY protocol)
- Sampling & deduplication
- Concurrent worker support (SELECT FOR UPDATE SKIP LOCKED)
- Comprehensive monitoring
"""

import os
import sys
import time
import logging
import hashlib
import math
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional
from numbers import Number
import threading

import pandas as pd
from pandas.api.types import is_datetime64_any_dtype
import pyarrow.parquet as pq
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values, RealDictCursor
from psycopg2.pool import SimpleConnectionPool
import socket

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.config_manager import get_config_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(name)s - %(message)s',
    handlers=[
        logging.FileHandler('high_performance_importer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class HighPerformanceImporter:
    """
    Enterprise-grade Parquet to PostgreSQL importer
    
    Design Principles:
    1. Idempotent: File hash prevents double-import
    2. Selective: Only import mapped tags
    3. Efficient: Bulk COPY, batching, connection pooling
    4. Safe: Transactions, error handling, monitoring
    5. Concurrent: SKIP LOCKED for multi-worker
    """

    _db_pool: Optional[SimpleConnectionPool] = None
    _pool_lock = threading.Lock()
    _indexes_ensured = False

    DEFAULT_BATCH_SIZE = 50000
    DEFAULT_POOL_MIN_CONN = 1
    DEFAULT_POOL_MAX_CONN = 8
    RETRYABLE_PG_CODES = {
        '40001',  # serialization_failure
        '40P01',  # deadlock_detected
        '53300',  # too_many_connections
        '57P01',  # admin_shutdown
        '57P03',  # cannot_connect_now
        '08000',  # connection_exception
        '08003',  # connection_does_not_exist
        '08006',  # connection_failure
        '08001',  # sqlclient_unable_to_establish_sqlconnection
        '08004',  # sqlserver_rejected_establishment_of_sqlconnection
        '08007'   # transaction_resolution_unknown
    }

    QUALITY_MAP = {
        'GOOD': 192,
        'GOODCLAMP': 192,
        'GOOD-NOTLIMITED': 192,
        'GOOD-LOCALOVERRIDE': 216,
        'OK': 192,
        'BAD': 0,
        'BAD-NOTCONNECTED': 0,
        'BAD-DEVICEFAILURE': 0,
        'BAD-SENSORFAILURE': 0,
        'BAD-LASTKNOWNVALUE': 8,
        'UNCERTAIN': 64,
        'UNCERTAIN-LASTUSABLEVALUE': 80,
        'UNCERTAIN-SENSORNOTACCURATE': 68,
        'SUBNORMAL': 88
    }
    
    def __init__(self, worker_id: Optional[str] = None):
        self.config_manager = get_config_manager()
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}"
        
        # In-memory sampling state (per-tag last timestamp)
        self._sampling_state: Dict[str, datetime] = {}
        self._wide_last_values: Dict[str, Optional[float]] = {}
        self._max_retry_attempts = 3
        self._retry_sleep_seconds = 2
        
        # Performance tracking
        self._stats = {
            'files_processed': 0,
            'files_success': 0,
            'files_failed': 0,
            'files_skipped': 0,
            'total_records': 0,
            'total_tags': 0
        }

        self._ensure_db_pool()
        self._ensure_indexes()
        
        logger.info(f"Importer initialized: worker_id={self.worker_id}")
    
    # =========================================================================
    # DATABASE CONNECTION
    # =========================================================================
    
    def _ensure_db_pool(self):
        """Initialize database connection pool once per process."""
        if HighPerformanceImporter._db_pool is not None:
            return

        with HighPerformanceImporter._pool_lock:
            if HighPerformanceImporter._db_pool is not None:
                return

            db_config = self.config_manager.get_db_config()
            min_conn = int(db_config.get('pool_min_connections', self.DEFAULT_POOL_MIN_CONN))
            max_conn = int(db_config.get('pool_max_connections', self.DEFAULT_POOL_MAX_CONN))
            if max_conn < min_conn:
                max_conn = min_conn

            HighPerformanceImporter._db_pool = SimpleConnectionPool(
                min_conn,
                max_conn,
                host=db_config.get('host', 'localhost'),
                port=db_config.get('port', 5432),
                database=db_config.get('database', 'Cereveate'),
                user=db_config.get('user', 'cereveate'),
                password=db_config.get('password', 'cereveate@222'),
                options='-c statement_timeout=300000'
            )

    def get_db_connection(self):
        """Borrow database connection from pool."""
        self._ensure_db_pool()
        if HighPerformanceImporter._db_pool is None:
            raise RuntimeError("Database connection pool was not initialized")
        return HighPerformanceImporter._db_pool.getconn()

    def release_db_connection(self, conn):
        """Return connection to the pool."""
        if conn is None:
            return
        if HighPerformanceImporter._db_pool is None:
            conn.close()
            return
        HighPerformanceImporter._db_pool.putconn(conn)

    @classmethod
    def close_db_pool(cls):
        """Close all pooled connections."""
        if cls._db_pool is not None:
            cls._db_pool.closeall()
            cls._db_pool = None

    @contextmanager
    def db_cursor(self, cursor_factory=None):
        """Context manager yielding a connection and cursor with automatic cleanup."""
        conn = None
        cursor = None
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor(cursor_factory=cursor_factory)
            yield conn, cursor
            conn.commit()
        except Exception:
            if conn is not None:
                conn.rollback()
            raise
        finally:
            if cursor is not None and not cursor.closed:
                cursor.close()
            if conn is not None:
                self.release_db_connection(conn)

    def _is_retryable(self, exc: psycopg2.Error) -> bool:
        """Determine if exception should be retried."""
        if isinstance(exc, psycopg2.OperationalError):
            return True

        pg_code = getattr(exc, 'pgcode', None)
        return pg_code in self.RETRYABLE_PG_CODES

    def _run_with_retry(self, func, *args, **kwargs):
        """Execute a callable with retry logic for transient database errors."""
        attempts = kwargs.pop('attempts', self._max_retry_attempts)
        sleep_seconds = kwargs.pop('sleep_seconds', self._retry_sleep_seconds)
        last_exception = None

        for attempt in range(1, attempts + 1):
            try:
                return func(*args, **kwargs)
            except psycopg2.Error as exc:
                last_exception = exc
                if attempt == attempts or not self._is_retryable(exc):
                    logger.error("Database operation failed: %s", exc)
                    raise

                logger.warning(
                    "Database operation failed with %s (attempt %s/%s). Retrying in %ss...",
                    getattr(exc, 'pgcode', 'unknown'),
                    attempt,
                    attempts,
                    sleep_seconds
                )
                time.sleep(sleep_seconds)

        if last_exception:
            raise last_exception

    def _ensure_indexes(self):
        """Create required indexes if they do not exist."""
        if HighPerformanceImporter._indexes_ensured:
            return

        def _create_indexes():
            with self.db_cursor() as (_, cursor):
                statements = [
                    "CREATE INDEX IF NOT EXISTS idx_tag_imports_file ON tag_imports (file_path, file_hash)",
                    "CREATE INDEX IF NOT EXISTS idx_sensor_data_tag_time ON sensor_data (tag_code, timestamp)",
                    "CREATE INDEX IF NOT EXISTS idx_tag_catalog_mapped ON tag_catalog (is_mapped)"
                ]
                for statement in statements:
                    cursor.execute(statement)

        try:
            self._run_with_retry(_create_indexes)
            HighPerformanceImporter._indexes_ensured = True
        except Exception as exc:
            logger.warning(f"Unable to ensure indexes: {exc}")
    
    # =========================================================================
    # FILE HASH & VALIDATION
    # =========================================================================
    
    def calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA256 hash of file for idempotency"""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def is_file_ready(self, file_path: str, stability_wait: int = 5) -> bool:
        """Check if file is ready (not being written)"""
        try:
            initial_size = os.path.getsize(file_path)
            time.sleep(stability_wait)
            final_size = os.path.getsize(file_path)
            return initial_size == final_size
        except Exception as e:
            logger.warning(f"Error checking file stability: {e}")
            return False
    
    # =========================================================================
    # IMPORT QUEUE MANAGEMENT (Concurrent Worker Support)
    # =========================================================================
    
    def enqueue_file(self, file_path: str) -> bool:
        """
        Add file to import queue (idempotent)
        Returns True if file was newly enqueued, False if already exists
        """
        try:
            file_hash = self.calculate_file_hash(file_path)
            file_size = os.path.getsize(file_path)

            def _operation():
                with self.db_cursor() as (_, cursor):
                    cursor.execute(
                        """
                        INSERT INTO file_imports (file_path, file_hash, file_size, status)
                        VALUES (%s, %s, %s, 'PENDING')
                        ON CONFLICT (file_path, file_hash) DO NOTHING
                        RETURNING id
                        """,
                        (file_path, file_hash, file_size)
                    )
                    return cursor.fetchone()

            result = self._run_with_retry(_operation)

            if result:
                logger.info(f"Enqueued: {file_path} (hash={file_hash[:8]}...)")
                return True
            else:
                logger.debug(f"Already enqueued: {file_path}")
                return False
                
        except Exception as e:
            logger.error(f"Error enqueuing file {file_path}: {e}")
            return False
    
    def get_next_pending_file(self) -> Optional[Dict]:
        """
        Get next PENDING file from queue using SKIP LOCKED
        Returns file metadata or None if queue is empty
        """
        try:
            def _operation():
                with self.db_cursor(cursor_factory=RealDictCursor) as (_, cursor):
                    cursor.execute(
                        """
                        UPDATE file_imports
                        SET 
                            status = 'PROCESSING',
                            worker_id = %s,
                            lock_acquired_at = NOW(),
                            started_at = NOW()
                        WHERE id = (
                            SELECT id FROM file_imports
                            WHERE status = 'PENDING'
                            ORDER BY id
                            LIMIT 1
                            FOR UPDATE SKIP LOCKED
                        )
                        RETURNING id, file_path, file_hash, file_size
                        """,
                        (self.worker_id,)
                    )
                    return cursor.fetchone()

            result = self._run_with_retry(_operation)

            if result:
                logger.info(f"Locked file for processing: {result['file_path']}")
                return dict(result)
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error getting next pending file: {e}")
            return None
    
    def mark_file_complete(self, file_id: int, status: str, 
                          records_imported: int, tags_imported: int,
                          tags_skipped: int, error_message: Optional[str] = None,
                          file_format: Optional[str] = None,
                          total_tags: int = 0, total_rows: int = 0):
        """Mark file import as complete in database"""
        try:
            def _operation():
                with self.db_cursor() as (_, cursor):
                    cursor.execute(
                        """
                        UPDATE file_imports
                        SET 
                            status = %s,
                            completed_at = NOW(),
                            processing_time_ms = EXTRACT(EPOCH FROM (NOW() - started_at)) * 1000,
                            records_imported = %s,
                            tags_imported = %s,
                            tags_skipped = %s,
                            error_message = %s,
                            file_format = %s,
                            total_tags_in_file = %s,
                            total_rows_in_file = %s
                        WHERE id = %s
                        """,
                        (status, records_imported, tags_imported, tags_skipped,
                         error_message, file_format, total_tags, total_rows, file_id)
                    )

            self._run_with_retry(_operation)

            logger.info(f"Marked file {file_id} as {status}")
            
        except Exception as e:
            logger.error(f"Error marking file complete: {e}")
    
    # =========================================================================
    # TAG CATALOG MANAGEMENT
    # =========================================================================
    
    def update_tag_catalog(
        self,
        tag_ids: Set[str],
        file_path: str,
        record_counts: Dict[str, int],
        min_timestamp: Optional[datetime],
        max_timestamp: Optional[datetime],
        mapped_tags: Set[str],
        file_hash: str,
        file_size_bytes: int
    ):
        """Batch update of tag catalog tables for discovered tags."""
        if not tag_ids:
            return

        min_ts = min_timestamp or datetime.utcnow()
        max_ts = max_timestamp or min_ts
        now_ts = datetime.utcnow()

        try:
            def _operation():
                with self.db_cursor() as (_, cursor):
                    tag_catalog_rows = [
                        (
                            tag_id,
                            min_ts,
                            max_ts,
                            file_path,
                            int(record_counts.get(tag_id, 0)),
                            tag_id in mapped_tags,
                            now_ts
                        )
                        for tag_id in tag_ids
                    ]

                    tag_file_rows = [
                        (
                            tag_id,
                            file_path,
                            file_hash,
                            min_ts,
                            max_ts,
                            int(record_counts.get(tag_id, 0)),
                            file_size_bytes,
                            now_ts
                        )
                        for tag_id in tag_ids
                    ]

                    execute_values(
                        cursor,
                        """
                        INSERT INTO tag_catalog 
                        (tag_id, first_seen, last_seen, last_file, record_count, is_mapped, last_updated)
                        VALUES %s
                        ON CONFLICT (tag_id) DO UPDATE SET
                            first_seen = LEAST(tag_catalog.first_seen, EXCLUDED.first_seen),
                            last_seen = GREATEST(tag_catalog.last_seen, EXCLUDED.last_seen),
                            last_file = EXCLUDED.last_file,
                            record_count = tag_catalog.record_count + EXCLUDED.record_count,
                            is_mapped = EXCLUDED.is_mapped,
                            last_updated = EXCLUDED.last_updated
                        """,
                        tag_catalog_rows,
                        template="(%s, %s, %s, %s, %s, %s, %s)"
                    )

                    execute_values(
                        cursor,
                        """
                        INSERT INTO tag_file_catalog 
                        (tag_id, file_path, file_hash, first_seen, last_seen, record_count, file_size_bytes, last_updated)
                        VALUES %s
                        ON CONFLICT (tag_id, file_path, file_hash) DO UPDATE SET
                            first_seen = LEAST(tag_file_catalog.first_seen, EXCLUDED.first_seen),
                            last_seen = GREATEST(tag_file_catalog.last_seen, EXCLUDED.last_seen),
                            record_count = EXCLUDED.record_count,
                            last_updated = EXCLUDED.last_updated
                        """,
                        tag_file_rows,
                        template="(%s, %s, %s, %s, %s, %s, %s, %s)"
                    )

            self._run_with_retry(_operation)

            logger.info(f"Updated tag_catalog: {len(tag_ids)} tags ({len(mapped_tags)} mapped)")

        except Exception as e:
            logger.error(f"Error updating tag catalog: {e}")
    
    # =========================================================================
    # FORMAT DETECTION & TAG EXTRACTION
    # =========================================================================

    def _normalize_quality_code(self, quality_raw) -> int:
        """Normalize quality payloads into OPC DA integer codes."""
        if pd.isna(quality_raw):
            return 192

        if isinstance(quality_raw, str):
            normalized = quality_raw.strip().upper()
            return self.QUALITY_MAP.get(normalized, 192)

        try:
            return int(quality_raw)
        except (TypeError, ValueError):
            return 192

    def _coerce_numeric_value(self, tag_id: str, timestamp: datetime, raw_value) -> Optional[float]:
        """Convert mixed OPC values into a float for storage."""
        if raw_value is None:
            return None

        if isinstance(raw_value, bool):
            return 1.0 if raw_value else 0.0

        if isinstance(raw_value, Number):
            try:
                numeric = float(raw_value)
            except (TypeError, ValueError):
                return None
            return numeric if math.isfinite(numeric) else None

        if isinstance(raw_value, str):
            value_str = raw_value.strip()
            if not value_str:
                return None

            lowered = value_str.lower()
            if lowered in {"true", "false"}:
                return 1.0 if lowered == "true" else 0.0

            try:
                numeric = float(value_str)
                return numeric if math.isfinite(numeric) else None
            except ValueError:
                logger.debug("Skipping non-numeric value for %s at %s: %r", tag_id, timestamp, raw_value)
                return None

        try:
            numeric = float(raw_value)
            return numeric if math.isfinite(numeric) else None
        except (TypeError, ValueError):
            logger.debug("Skipping unsupported value type for %s at %s: %r", tag_id, timestamp, raw_value)
            return None

    def _compute_timestamp_range(self, parquet_file: pq.ParquetFile, timestamp_column: Optional[str]) -> Tuple[Optional[datetime], Optional[datetime]]:
        if not timestamp_column:
            return None, None

        min_ts = None
        max_ts = None

        try:
            for batch in parquet_file.iter_batches(columns=[timestamp_column], batch_size=self.DEFAULT_BATCH_SIZE):
                batch_df = batch.to_pandas()
                if timestamp_column not in batch_df.columns:
                    continue
                series = batch_df[timestamp_column].dropna()
                if series.empty:
                    continue
                batch_min = series.min()
                batch_max = series.max()

                if pd.isna(batch_min) or pd.isna(batch_max):
                    continue

                min_ts = batch_min if min_ts is None else min(min_ts, batch_min)
                max_ts = batch_max if max_ts is None else max(max_ts, batch_max)

        except Exception as exc:
            logger.warning(f"Failed to compute timestamp range for {timestamp_column}: {exc}")

        def _convert(value):
            if value is None:
                return None
            return pd.Timestamp(value).to_pydatetime()

        return _convert(min_ts), _convert(max_ts)

    def _collect_long_format_metadata(
        self,
        parquet_file: pq.ParquetFile,
        tagid_column: str,
        timestamp_column: Optional[str]
    ) -> Tuple[Set[str], Dict[str, int], Optional[datetime], Optional[datetime]]:
        tag_counts: Counter = Counter()
        min_ts = None
        max_ts = None

        for batch in parquet_file.iter_batches(columns=[c for c in [tagid_column, timestamp_column] if c], batch_size=self.DEFAULT_BATCH_SIZE):
            batch_df = batch.to_pandas()

            if tagid_column in batch_df.columns:
                batch_tags = batch_df[tagid_column].dropna()
                if not batch_tags.empty:
                    tag_counts.update(batch_tags.astype(str))

            if timestamp_column and timestamp_column in batch_df.columns:
                series = batch_df[timestamp_column].dropna()
                if not series.empty:
                    batch_min = series.min()
                    batch_max = series.max()
                    if not pd.isna(batch_min):
                        min_ts = batch_min if min_ts is None else min(min_ts, batch_min)
                    if not pd.isna(batch_max):
                        max_ts = batch_max if max_ts is None else max(max_ts, batch_max)

        def _convert(value):
            if value is None:
                return None
            return pd.Timestamp(value).to_pydatetime()

        return set(tag_counts.keys()), {k: int(v) for k, v in tag_counts.items()}, _convert(min_ts), _convert(max_ts)

    def _collect_wide_format_metadata(
        self,
        parquet_file: pq.ParquetFile,
        timestamp_column: Optional[str],
        tag_columns: Set[str]
    ) -> Tuple[Optional[datetime], Optional[datetime], Dict[str, int]]:
        min_ts, max_ts = self._compute_timestamp_range(parquet_file, timestamp_column)
        record_counts: Dict[str, int] = {}

        total_rows = parquet_file.metadata.num_rows if parquet_file.metadata else 0

        for tag in tag_columns:
            column_index = parquet_file.schema.get_field_index(tag)
            if column_index == -1:
                record_counts[tag] = 0
                continue

            null_count = 0
            null_count_known = True

            if parquet_file.metadata is not None:
                for rg_idx in range(parquet_file.metadata.num_row_groups):
                    column_meta = parquet_file.metadata.row_group(rg_idx).column(column_index)
                    stats = column_meta.statistics
                    if stats is None:
                        null_count_known = False
                        break
                    if hasattr(stats, 'has_null_count') and not stats.has_null_count:
                        null_count_known = False
                        break
                    if stats.null_count is None:
                        null_count_known = False
                        break
                    null_count += stats.null_count
            else:
                null_count_known = False

            if not null_count_known:
                record_counts[tag] = total_rows
            else:
                record_counts[tag] = max(total_rows - null_count, 0)

        return min_ts, max_ts, record_counts
    
    def detect_format(self, columns_source) -> Tuple[bool, str]:
        """
        Detect parquet format (LONG or WIDE)
        Returns: (is_long_format, format_name)
        """
        if hasattr(columns_source, 'columns'):
            columns = list(columns_source.columns)
        else:
            columns = list(columns_source)

        columns_lower = {c.lower(): c for c in columns}
        
        # Long format: TagId, Timestamp, Value, [Quality]
        has_tagid = 'tagid' in columns_lower
        has_timestamp = 'timestamp' in columns_lower
        has_value = 'value' in columns_lower
        
        is_long_format = has_tagid and has_timestamp and has_value
        format_name = 'LONG' if is_long_format else 'WIDE'
        
        return is_long_format, format_name
    
    def extract_tag_ids(self, df: pd.DataFrame, is_long_format: bool) -> Set[str]:
        """Extract distinct tag IDs from dataframe"""
        try:
            if is_long_format:
                if 'TagId' in df.columns:
                    return set(df['TagId'].dropna().unique())
                else:
                    logger.warning("Long format but no TagId column")
                    return set()
            else:
                # Wide format: column names are tags (exclude Timestamp)
                return set(col for col in df.columns if col.lower() != 'timestamp')
        except Exception as e:
            logger.error(f"Error extracting tag IDs: {e}")
            return set()
    
    # =========================================================================
    # DATA PROCESSING & SAMPLING
    # =========================================================================
    
    def apply_sampling(self, tag_id: str, timestamp: datetime, 
                      sampling_freq: int) -> bool:
        """
        Apply sampling frequency filter
        Returns True if record should be imported, False if skipped
        """
        if sampling_freq <= 0:
            return True  # Import all records
        
        last_ts = self._sampling_state.get(tag_id)
        
        if last_ts is None:
            # First record for this tag
            self._sampling_state[tag_id] = timestamp
            return True
        
        time_diff = (timestamp - last_ts).total_seconds()
        
        if time_diff >= sampling_freq:
            self._sampling_state[tag_id] = timestamp
            return True
        else:
            return False  # Skip (too soon after last sample)
    
    def process_long_format(self, df: pd.DataFrame, tag_mappings: Dict[str, Dict],
                           tags_to_import: Set[str]) -> List[Dict]:
        """
        Process LONG format parquet: TagId, Timestamp, Value, [Quality]
        Returns list of records ready for insert
        """
        records = []
        
        try:
            # Filter to only mapped tags
            df_filtered = df[df['TagId'].isin(tags_to_import)].copy()
            
            if df_filtered.empty:
                return records
            
            # Ensure timestamp is datetime
            if not is_datetime64_any_dtype(df_filtered['Timestamp']):
                df_filtered['Timestamp'] = pd.to_datetime(df_filtered['Timestamp'], errors='coerce')

            df_filtered = df_filtered.dropna(subset=['Timestamp', 'Value'])
            df_filtered = df_filtered.sort_values('Timestamp')
            
            # Process each tag
            for tag_id in tags_to_import:
                mapping = tag_mappings.get(tag_id)
                if not mapping:
                    continue
                
                tag_data = df_filtered[df_filtered['TagId'] == tag_id]
                sampling_freq = mapping.get('sampling_frequency_seconds', 0)
                
                for _, row in tag_data.iterrows():
                    timestamp = row['Timestamp']

                    numeric_value = self._coerce_numeric_value(tag_id, timestamp, row['Value'])
                    if numeric_value is None:
                        continue

                    # Apply sampling after we confirm the value is usable
                    if not self.apply_sampling(tag_id, timestamp, sampling_freq):
                        continue

                    # Extract quality code (handle both integer and string)
                    quality_code = self._normalize_quality_code(row.get('Quality', 192))

                    records.append({
                        'timestamp': timestamp,
                        'tag_code': tag_id,
                        'tag_name': mapping.get('tag_name', tag_id),
                        'plant': mapping.get('plant', 'Unknown'),
                        'asset': mapping.get('asset', 'Unknown'),
                        'subsystem': mapping.get('subsystem', 'General'),
                        'unit': mapping.get('unit', ''),
                        'value': numeric_value,
                        'quality_code': quality_code,
                        'status_flag': 'OK' if quality_code == 192 else 'BAD',
                        'data_source': 'OPC_DA'
                    })
            
            return records
            
        except Exception as e:
            logger.error(f"Error processing long format: {e}", exc_info=True)
            return []
    
    def process_wide_format(self, df: pd.DataFrame, tag_mappings: Dict[str, Dict],
                           tags_to_import: Set[str]) -> List[Dict]:
        """
        Process WIDE format parquet: Timestamp, Tag1, Tag2, ...
        Returns list of records ready for insert
        """
        records = []
        
        try:
            if 'Timestamp' not in df.columns:
                logger.warning("No Timestamp column in wide format")
                return records
            
            # Ensure timestamp is datetime
            if not is_datetime64_any_dtype(df['Timestamp']):
                df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
            df = df.dropna(subset=['Timestamp'])
            df = df.sort_values('Timestamp')
            
            # Process each mapped tag column
            for tag_id in tags_to_import:
                if tag_id not in df.columns:
                    continue
                
                mapping = tag_mappings.get(tag_id)
                if not mapping:
                    continue
                
                sampling_freq = mapping.get('sampling_frequency_seconds', 0)
                
                series = df[tag_id]
                last_value = self._wide_last_values.get(tag_id)
                if last_value is not None:
                    series = series.fillna(last_value)
                series = series.ffill()
                
                valid_mask = series.notna()
                if not valid_mask.any():
                    continue
                
                for timestamp, raw_value in zip(df.loc[valid_mask, 'Timestamp'], series[valid_mask]):
                    numeric_value = self._coerce_numeric_value(tag_id, timestamp, raw_value)
                    if numeric_value is None:
                        continue

                    # Track last numeric value for forward fill on the next batch
                    self._wide_last_values[tag_id] = numeric_value

                    # Apply sampling filter
                    if not self.apply_sampling(tag_id, timestamp, sampling_freq):
                        continue

                    records.append({
                        'timestamp': timestamp,
                        'tag_code': tag_id,
                        'tag_name': mapping.get('tag_name', tag_id),
                        'plant': mapping.get('plant', 'Unknown'),
                        'asset': mapping.get('asset', 'Unknown'),
                        'subsystem': mapping.get('subsystem', 'General'),
                        'unit': mapping.get('unit', ''),
                        'value': numeric_value,
                        'quality_code': 192,
                        'status_flag': 'OK',
                        'data_source': 'OPC_DA'
                    })
            
            return records
            
        except Exception as e:
            logger.error(f"Error processing wide format: {e}", exc_info=True)
            return []
    
    # =========================================================================
    # BULK INSERT (High-Performance COPY Protocol)
    # =========================================================================
    
    def bulk_insert_records(self, records: List[Dict]) -> int:
        """
        Insert records using execute_values (fast batch insert)
        Returns number of records inserted
        """
        if not records:
            return 0
        
        try:
            unique_records: Dict[Tuple[datetime, str], Dict] = {}
            duplicate_counter = 0

            for record in records:
                key = (record['timestamp'], record['tag_code'])
                if key in unique_records:
                    duplicate_counter += 1
                unique_records[key] = record

            if duplicate_counter:
                logger.debug(
                    "Deduplicated %s duplicate rows based on (timestamp, tag_code)",
                    duplicate_counter
                )

            deduped_records = list(unique_records.values())

            values = [
                (
                    r['timestamp'],
                    r['tag_code'],
                    r['tag_name'],
                    r['plant'],
                    r['asset'],
                    r['subsystem'],
                    r['unit'],
                    r['value'],
                    r['quality_code'],
                    r['status_flag'],
                    r['data_source']
                )
                for r in deduped_records
            ]

            def _operation():
                with self.db_cursor() as (_, cursor):
                    execute_values(
                        cursor,
                        """
                        INSERT INTO sensor_data 
                        (timestamp, tag_code, tag_name, plant, asset, subsystem, unit, 
                         value, quality_code, status_flag, data_source)
                        VALUES %s
                        ON CONFLICT (timestamp, tag_code) DO NOTHING
                        """,
                        values,
                        page_size=1000
                    )
                    return cursor.rowcount

            return self._run_with_retry(_operation)
            
        except Exception as e:
            logger.error(f"Error bulk inserting records: {e}", exc_info=True)
            return 0
    
    def log_tag_imports(self, file_path: str, file_hash: str, 
                       tag_record_counts: Dict[str, int]):
        """Log per-tag import results to tag_imports table"""
        try:
            def _operation():
                with self.db_cursor() as (_, cursor):
                    for tag_id, count in tag_record_counts.items():
                        cursor.execute(
                            """
                            INSERT INTO tag_imports (file_path, file_hash, tag_id, records_imported, status)
                            VALUES (%s, %s, %s, %s, 'SUCCESS')
                            ON CONFLICT (file_path, file_hash, tag_id) DO UPDATE SET
                                records_imported = EXCLUDED.records_imported,
                                import_timestamp = NOW()
                            """,
                            (file_path, file_hash, tag_id, count)
                        )

            self._run_with_retry(_operation)

        except Exception as e:
            logger.error(f"Error logging tag imports: {e}")
    
    # =========================================================================
    # MAIN IMPORT WORKFLOW
    # =========================================================================
    
    def import_file(self, file_metadata: Dict) -> bool:
        """
        Import single file with full tracking
        
        Workflow:
        1. Read parquet & detect format
        2. Extract all tag IDs
        3. Update tag_catalog (all tags)
        4. Get mapped tags from config
        5. Determine which tags to import (exclude already imported)
        6. Process data with sampling
        7. Bulk insert to sensor_data
        8. Log results to tag_imports
        9. Mark file complete
        """
        file_id = file_metadata['id']
        file_path = file_metadata['file_path']
        file_hash = file_metadata['file_hash']
        file_size = file_metadata.get('file_size') or os.path.getsize(file_path)
        
        start_time = time.time()
        self._sampling_state.clear()
        self._wide_last_values.clear()
        
        try:
            if not file_path.lower().endswith('.parquet'):
                logger.warning(f"Skipping non-parquet file: {file_path}")
                self.mark_file_complete(
                    file_id,
                    'SKIPPED',
                    0,
                    0,
                    0,
                    "Unsupported file format",
                    None,
                    0,
                    0
                )
                self._stats['files_skipped'] += 1
                return True

            logger.info(f"=== PROCESSING FILE: {file_path} ===")
            
            try:
                parquet_file = pq.ParquetFile(file_path)
            except Exception as e:
                error_msg = f"Failed to open parquet file: {e}"
                logger.error(error_msg)
                self.mark_file_complete(file_id, 'FAILED', 0, 0, 0, error_msg)
                return False

            total_rows = parquet_file.metadata.num_rows if parquet_file.metadata else 0
            logger.info(f"Parquet metadata rows: {total_rows}")

            schema_names = parquet_file.schema.names
            columns_lower_map = {name.lower(): name for name in schema_names}

            # Step 2: Detect format
            is_long_format, format_name = self.detect_format(schema_names)
            logger.info(f"Format: {format_name}")
            
            # Step 3: Build tag metadata
            tag_mappings = self.config_manager.get_enabled_tag_mappings()

            if is_long_format:
                tagid_column = columns_lower_map.get('tagid')
                timestamp_column = columns_lower_map.get('timestamp')
                value_column = columns_lower_map.get('value')
                quality_column = columns_lower_map.get('quality') or columns_lower_map.get('qualitycode')

                if not all([tagid_column, timestamp_column, value_column]):
                    error_msg = "Required columns missing for long format import"
                    logger.error(error_msg)
                    self.mark_file_complete(file_id, 'FAILED', 0, 0, 0, error_msg, format_name, 0, total_rows)
                    return False

                all_tags, record_counts, min_ts, max_ts = self._collect_long_format_metadata(
                    parquet_file,
                    tagid_column,
                    timestamp_column
                )

                tag_map = {m['parquet_column']: m for m in tag_mappings if m.get('parquet_column')}
            else:
                timestamp_column = columns_lower_map.get('timestamp')
                if not timestamp_column:
                    error_msg = "Timestamp column required for wide format import"
                    logger.error(error_msg)
                    self.mark_file_complete(file_id, 'FAILED', 0, 0, 0, error_msg, format_name, 0, total_rows)
                    return False

                all_tags = set(col for col in schema_names if col != timestamp_column)
                min_ts, max_ts, record_counts = self._collect_wide_format_metadata(
                    parquet_file,
                    timestamp_column,
                    all_tags
                )

                lower_to_actual = {col.lower(): col for col in schema_names}
                tag_map = {}
                for mapping in tag_mappings:
                    parquet_column = mapping.get('parquet_column')
                    if not parquet_column:
                        continue
                    actual_column = lower_to_actual.get(parquet_column.lower())
                    if not actual_column:
                        continue
                    mapping_copy = dict(mapping)
                    mapping_copy['parquet_column'] = actual_column
                    tag_map[actual_column] = mapping_copy

            logger.info(f"Found {len(all_tags)} unique tags")
            
            if not all_tags:
                logger.warning("No tags found in file")
                self.mark_file_complete(
                    file_id,
                    'SKIPPED',
                    0,
                    0,
                    0,
                    "No tags found",
                    format_name,
                    0,
                    total_rows
                )
                return True

            mapped_tags = set(tag_map.keys())
            logger.info(f"Mapped tags in config: {len(mapped_tags)}")

            # Step 4: Update tag catalog (ALL tags, mapped or not)
            self.update_tag_catalog(
                all_tags,
                file_path,
                record_counts,
                min_ts,
                max_ts,
                mapped_tags,
                file_hash,
                file_size
            )

            # Step 5: Determine which tags to import
            tags_available_and_mapped = all_tags.intersection(mapped_tags)
            
            if not tags_available_and_mapped:
                logger.info("No mapped tags in this file - skipping data import")
                self.mark_file_complete(file_id, 'SKIPPED', 0, 0, len(all_tags), 
                                       "No mapped tags", format_name, len(all_tags), total_rows)
                self._stats['files_skipped'] += 1
                return True
            
            # Check which tags already imported from this file+hash
            def _fetch_imported():
                with self.db_cursor() as (_, cursor):
                    cursor.execute(
                        """
                        SELECT tag_id FROM tag_imports 
                        WHERE file_path = %s AND file_hash = %s
                        """,
                        (file_path, file_hash)
                    )
                    return {row[0] for row in cursor.fetchall()}

            already_imported_tags = self._run_with_retry(_fetch_imported)
            tags_to_import = tags_available_and_mapped - already_imported_tags
            
            if not tags_to_import:
                logger.info("All mapped tags already imported from this file")
                self.mark_file_complete(file_id, 'SUCCESS', 0, 0, len(all_tags), 
                                       None, format_name, len(all_tags), total_rows)
                self._stats['files_success'] += 1
                return True
            
            logger.info(f"Tags to import: {len(tags_to_import)} (already imported: {len(already_imported_tags)})")

            # Step 6: Process data with sampling (streamed)
            tag_record_counts: Counter = Counter()
            inserted_count = 0

            try:
                if is_long_format:
                    value_column = columns_lower_map.get('value')
                    quality_column = columns_lower_map.get('quality') or columns_lower_map.get('qualitycode')
                    columns_to_read = [col for col in [tagid_column, timestamp_column, value_column, quality_column] if col]

                    for batch in parquet_file.iter_batches(columns=columns_to_read, batch_size=self.DEFAULT_BATCH_SIZE):
                        batch_df = batch.to_pandas()
                        rename_map = {}
                        if tagid_column in batch_df.columns:
                            rename_map[tagid_column] = 'TagId'
                        if timestamp_column in batch_df.columns:
                            rename_map[timestamp_column] = 'Timestamp'
                        if value_column in batch_df.columns:
                            rename_map[value_column] = 'Value'
                        if quality_column and quality_column in batch_df.columns:
                            rename_map[quality_column] = 'Quality'
                        batch_df = batch_df.rename(columns=rename_map)

                        records = self.process_long_format(batch_df, tag_map, tags_to_import)
                        if not records:
                            continue

                        inserted = self.bulk_insert_records(records)
                        inserted_count += inserted
                        for record in records:
                            tag_record_counts[record['tag_code']] += 1
                else:
                    timestamp_column = columns_lower_map.get('timestamp')
                    columns_to_read = [timestamp_column] + sorted(tags_to_import)

                    for batch in parquet_file.iter_batches(columns=columns_to_read, batch_size=self.DEFAULT_BATCH_SIZE):
                        batch_df = batch.to_pandas()
                        batch_df = batch_df.rename(columns={timestamp_column: 'Timestamp'})

                        records = self.process_wide_format(batch_df, tag_map, tags_to_import)
                        if not records:
                            continue

                        inserted = self.bulk_insert_records(records)
                        inserted_count += inserted
                        for record in records:
                            tag_record_counts[record['tag_code']] += 1

            except Exception as processing_error:
                error_msg = f"Error processing data: {processing_error}"
                logger.error(error_msg, exc_info=True)
                self.mark_file_complete(
                    file_id,
                    'FAILED',
                    inserted_count,
                    len(tags_to_import),
                    len(all_tags) - len(tags_to_import),
                    error_msg,
                    format_name,
                    len(all_tags),
                    total_rows
                )
                self._stats['files_failed'] += 1
                return False

            logger.info(f"Inserted {inserted_count} records to sensor_data")

            # Step 7: Log per-tag results
            if tag_record_counts:
                for tag_id, count in tag_record_counts.items():
                    logger.info(f"  - {tag_id}: {count} records")
            else:
                logger.warning("No records extracted (possible sampling filter)")

            for tag_id in tags_to_import:
                tag_record_counts.setdefault(tag_id, 0)

            self.log_tag_imports(file_path, file_hash, dict(tag_record_counts))

            # Step 8: Mark complete
            imported_tag_count = len(tag_record_counts) if tag_record_counts else len(tags_to_import)
            self.mark_file_complete(
                file_id,
                'SUCCESS',
                inserted_count,
                imported_tag_count,
                len(all_tags) - len(tags_to_import),
                None,
                format_name,
                len(all_tags),
                total_rows
            )
            
            # Update stats
            self._stats['files_processed'] += 1
            self._stats['files_success'] += 1
            self._stats['total_records'] += inserted_count
            self._stats['total_tags'] += imported_tag_count
            
            elapsed = time.time() - start_time
            logger.info(f"=== FILE COMPLETE: {inserted_count} records, {elapsed:.2f}s ===")
            
            return True
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error importing file: {error_msg}", exc_info=True)
            self.mark_file_complete(file_id, 'FAILED', 0, 0, 0, error_msg)
            self._stats['files_failed'] += 1
            return False
    
    # =========================================================================
    # DIRECTORY PROCESSING
    # =========================================================================
    
    def scan_and_enqueue_directory(self, directory: str):
        """Scan directory and enqueue all parquet files"""
        try:
            parquet_files = list(Path(directory).glob('*.parquet'))
            logger.info(f"Scanning directory: {directory}")
            logger.info(f"Found {len(parquet_files)} parquet files")
            
            enqueued_count = 0
            for file_path in parquet_files:
                if self.enqueue_file(str(file_path)):
                    enqueued_count += 1
            
            logger.info(f"Enqueued {enqueued_count} new files")
            
        except Exception as e:
            logger.error(f"Error scanning directory: {e}")
    
    def process_queue(self, max_files: Optional[int] = None):
        """Process files from queue until empty or max_files reached"""
        processed = 0
        
        while True:
            if max_files and processed >= max_files:
                logger.info(f"Reached max_files limit ({max_files})")
                break
            
            # Get next file with lock
            file_metadata = self.get_next_pending_file()
            
            if not file_metadata:
                logger.info("Queue empty - no more files to process")
                break
            
            # Process file
            self.import_file(file_metadata)
            processed += 1
        
        logger.info(f"Processed {processed} files from queue")
        return processed
    
    def print_stats(self):
        """Print processing statistics"""
        logger.info("=" * 60)
        logger.info("IMPORT STATISTICS")
        logger.info("=" * 60)
        for key, value in self._stats.items():
            logger.info(f"  {key}: {value}")
        logger.info("=" * 60)


def main():
    """Main entry point for high-performance importer"""
    logger.info("=" * 80)
    logger.info("HIGH-PERFORMANCE PARQUET IMPORTER")
    logger.info("Enterprise-ready importer for 10K+ tags")
    logger.info("=" * 80)
    
    # Initialize importer
    importer = HighPerformanceImporter()
    
    # Get configuration
    config = get_config_manager()
    data_dir = config.get_parquet_source_config().get('data_directory')
    
    if not os.path.exists(data_dir):
        logger.error(f"Data directory not found: {data_dir}")
        return
    
    logger.info(f"Data directory: {data_dir}")
    
    # Scan and enqueue all files
    importer.scan_and_enqueue_directory(data_dir)
    
    # Process queue
    importer.process_queue()
    
    # Print stats
    importer.print_stats()
    
    logger.info("Importer finished")
    HighPerformanceImporter.close_db_pool()


if __name__ == "__main__":
    main()
