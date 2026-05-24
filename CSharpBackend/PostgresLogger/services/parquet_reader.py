"""
Safe Parquet File Reader
Non-blocking reader with file lock detection and auto-discovery
"""

import os
import time
import hashlib
import pyarrow.parquet as pq
import pandas as pd
from pathlib import Path
from typing import Tuple, List, Optional
import logging

logger = logging.getLogger(__name__)

class SafeParquetReader:
    """Non-blocking, safe parquet file reader with auto-discovery"""
    
    def __init__(self, stability_seconds: int = 5):
        self.stability_seconds = stability_seconds
    
    def is_file_ready(self, file_path: str) -> bool:
        """
        Check if file is stable (not being written)
        Returns True only if file size hasn't changed for N seconds
        """
        try:
            # Check if file exists
            if not os.path.exists(file_path):
                return False
            
            # Get initial file stats
            initial_size = os.path.getsize(file_path)
            initial_mtime = os.path.getmtime(file_path)
            
            # Wait for stability period
            time.sleep(self.stability_seconds)
            
            # Check if file still exists
            if not os.path.exists(file_path):
                return False
            
            # Check if file changed
            current_size = os.path.getsize(file_path)
            current_mtime = os.path.getmtime(file_path)
            
            if current_size != initial_size or current_mtime != initial_mtime:
                logger.warning(f"File still being written: {file_path}")
                return False
            
            # Try to open exclusively to check locks
            try:
                # Open in read mode to check if accessible
                with open(file_path, 'rb') as f:
                    # Try to read first byte
                    f.read(1)
                return True
            except (IOError, PermissionError) as e:
                logger.warning(f"File is locked: {file_path} - {e}")
                return False
                
        except Exception as e:
            logger.error(f"Error checking file readiness: {e}")
            return False
    
    def calculate_checksum(self, file_path: str) -> str:
        """Calculate SHA256 checksum of file"""
        try:
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                # Read in chunks to handle large files
                for byte_block in iter(lambda: f.read(65536), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            logger.error(f"Error calculating checksum: {e}")
            return ""
    
    def get_column_names(self, file_path: str) -> List[str]:
        """Get column names from parquet file without loading data"""
        try:
            parquet_file = pq.ParquetFile(file_path)
            schema = parquet_file.schema_arrow
            return schema.names
        except Exception as e:
            logger.error(f"Error getting column names from {file_path}: {e}")
            return []
    
    def read_with_checksum(self, file_path: str, columns: Optional[List[str]] = None) -> Tuple[Optional[pd.DataFrame], str, int]:
        """
        Read parquet file and return data with checksum
        Uses READ-ONLY mode to prevent blocking OPC writer
        
        Returns: (dataframe, checksum, row_count)
        """
        if not self.is_file_ready(file_path):
            raise FileNotFoundError(f"File not ready: {file_path}")
        
        try:
            # Calculate checksum BEFORE reading data
            checksum_before = self.calculate_checksum(file_path)
            
            logger.info(f"Reading parquet file: {file_path}")
            
            # Read parquet using memory-mapped mode (non-blocking)
            # use_threads=False to avoid potential conflicts
            if columns:
                table = pq.read_table(
                    file_path, 
                    columns=columns,
                    memory_map=True, 
                    use_threads=False
                )
            else:
                table = pq.read_table(
                    file_path, 
                    memory_map=True, 
                    use_threads=False
                )
            
            # Convert to pandas for easier processing
            df = table.to_pandas()
            
            # Verify checksum AFTER reading
            checksum_after = self.calculate_checksum(file_path)
            
            if checksum_before != checksum_after:
                raise ValueError("File changed during read - checksum mismatch")
            
            row_count = len(df)
            logger.info(f"✓ Successfully read {row_count} rows from {file_path}")
            
            return df, checksum_before, row_count
            
        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")
            raise Exception(f"Failed to read {file_path}: {e}")
    
    def read_sample(self, file_path: str, max_rows: int = 100) -> Optional[pd.DataFrame]:
        """Read a small sample from parquet file for preview"""
        try:
            if not self.is_file_ready(file_path):
                return None
            
            table = pq.read_table(file_path, memory_map=True, use_threads=False)
            df = table.to_pandas()
            
            if len(df) > max_rows:
                return df.head(max_rows)
            return df
            
        except Exception as e:
            logger.error(f"Error reading sample from {file_path}: {e}")
            return None
    
    def get_file_metadata(self, file_path: str) -> dict:
        """Get metadata about parquet file"""
        try:
            parquet_file = pq.ParquetFile(file_path)
            metadata = parquet_file.metadata
            
            return {
                'num_rows': metadata.num_rows,
                'num_columns': metadata.num_columns,
                'num_row_groups': metadata.num_row_groups,
                'serialized_size': metadata.serialized_size,
                'columns': parquet_file.schema_arrow.names,
                'file_size': os.path.getsize(file_path),
                'modified_time': os.path.getmtime(file_path)
            }
        except Exception as e:
            logger.error(f"Error getting metadata from {file_path}: {e}")
            return {}


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    reader = SafeParquetReader(stability_seconds=3)
    
    # Test file
    test_file = "D:\\OpcLogs\\Data\\ALL_SENSORS_COMPLETE_FORWARDFILL.parquet"
    
    if os.path.exists(test_file):
        print(f"Testing file: {test_file}")
        
        # Get column names
        columns = reader.get_column_names(test_file)
        print(f"\nColumns ({len(columns)}): {columns[:5]}...")  # Show first 5
        
        # Get metadata
        metadata = reader.get_file_metadata(test_file)
        print(f"\nMetadata:")
        print(f"  Rows: {metadata.get('num_rows')}")
        print(f"  Columns: {metadata.get('num_columns')}")
        print(f"  File size: {metadata.get('file_size') / 1024 / 1024:.2f} MB")
        
        # Read sample
        sample = reader.read_sample(test_file, max_rows=5)
        if sample is not None:
            print(f"\nSample data:")
            print(sample)
