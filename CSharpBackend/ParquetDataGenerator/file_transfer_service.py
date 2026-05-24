"""
File Transfer Service - Moves parquet data from Simulation to Main directory
Thread-safe with proper file locking
"""
import threading
import time
import pandas as pd
import pyarrow.parquet as pq
import pyarrow as pa
from datetime import datetime
from pathlib import Path
import os
import shutil


class FileTransferService:
    def __init__(self, config):
        self.config = config
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        
        # Directories
        self.source_dir = Path(config['Paths']['SimulationOutputDirectory'])
        self.target_dir = Path(config['Paths']['MainDataDirectory'])
        
        # Ensure target directory exists
        self.target_dir.mkdir(parents=True, exist_ok=True)
        
        # Statistics
        self.files_transferred = 0
        self.records_transferred = 0
        self.last_transfer_time = None
        self.errors = []
        
    def start(self):
        """Start transfer service in background"""
        if self.running:
            return {'success': False, 'message': 'Transfer service already running'}
        
        self.running = True
        self.thread = threading.Thread(target=self._transfer_loop, daemon=True)
        self.thread.start()
        return {'success': True, 'message': 'Transfer service started'}
    
    def stop(self):
        """Stop transfer service"""
        if not self.running:
            return {'success': False, 'message': 'Transfer service not running'}
        
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        return {'success': True, 'message': 'Transfer service stopped'}
    
    def _transfer_loop(self):
        """Main transfer loop"""
        print(f"[FileTransferService] Started - {self.source_dir} → {self.target_dir}")
        
        while self.running:
            try:
                self._process_pending_files()
                time.sleep(self.config['FileTransfer']['TransferIntervalSeconds'])
                
            except Exception as e:
                print(f"[FileTransferService] Error: {e}")
                with self.lock:
                    self.errors.append(str(e))
                time.sleep(1)
    
    def _process_pending_files(self):
        """Process all pending parquet files"""
        if not self.source_dir.exists():
            return
        
        # Find all parquet files
        parquet_files = list(self.source_dir.glob('*.parquet'))
        
        if not parquet_files:
            return
        
        for source_file in parquet_files:
            try:
                # Wait longer to ensure file is fully written and closed
                file_age = time.time() - source_file.stat().st_mtime
                if file_age < 30:  # Wait 30 seconds before processing
                    continue
                
                self._transfer_file(source_file)
                
            except Exception as e:
                print(f"[FileTransferService] Error processing {source_file.name}: {e}")
                with self.lock:
                    self.errors.append(f"{source_file.name}: {str(e)}")
    
    def _transfer_file(self, source_file):
        """Transfer single file to main directory"""
        try:
            # Read source data
            source_df = pd.read_parquet(source_file)
            record_count = len(source_df)
            
            if record_count == 0:
                print(f"[FileTransferService] ⚠️ Empty file: {source_file.name}")
                if self.config['FileTransfer']['DeleteAfterTransfer']:
                    os.remove(source_file)
                return
            
            # Find main target file (append to existing main file)
            target_file = self.target_dir / "ALL_SENSORS_COMPLETE_FORWARDFILL.parquet"
            
            with self.lock:
                # Read existing data if file exists
                if target_file.exists():
                    existing_df = pd.read_parquet(target_file)
                    print(f"[FileTransferService] Existing file has {len(existing_df)} records")
                    
                    # Get max RowId to continue sequence
                    max_row_id = existing_df['RowId'].max() if 'RowId' in existing_df.columns else 0
                    
                    # Update RowId for new records
                    source_df['RowId'] = range(max_row_id + 1, max_row_id + 1 + len(source_df))
                    
                    # Combine data
                    combined_df = pd.concat([existing_df, source_df], ignore_index=True)
                    print(f"[FileTransferService] Merged: {len(existing_df)} + {len(source_df)} = {len(combined_df)} records")
                else:
                    combined_df = source_df
                    print(f"[FileTransferService] Creating new main file with {len(combined_df)} records")
                
                # Ensure correct column order: RowId, TagId, Timestamp, Value, Quality
                if 'RowId' not in combined_df.columns:
                    combined_df['RowId'] = range(1, len(combined_df) + 1)
                if 'Quality' not in combined_df.columns:
                    combined_df['Quality'] = 'GOOD'
                
                combined_df = combined_df[['RowId', 'TagId', 'Timestamp', 'Value', 'Quality']]
                
                # Write to parquet with correct schema (microsecond precision)
                table = pa.Table.from_pandas(combined_df, schema=pa.schema([
                    ('Timestamp', pa.timestamp('us')),  # Match existing file format
                    ('TagId', pa.string()),
                    ('Value', pa.float64())
                ]))
                    
                # Append or create target file (thread-safe)
                self._append_to_target(target_file, table)
            
            # Update statistics
            with self.lock:
                self.files_transferred += 1
                self.records_transferred += record_count
                self.last_transfer_time = datetime.now()
            
            print(f"[FileTransferService] ✅ Transferred: {source_file.name} ({record_count} records)")
            
            # Delete or keep source file
            if self.config['FileTransfer']['DeleteAfterTransfer']:
                os.remove(source_file)
            else:
                # Move to processed folder
                processed_dir = self.source_dir / 'processed'
                processed_dir.mkdir(exist_ok=True)
                shutil.move(str(source_file), str(processed_dir / source_file.name))
            
        except Exception as e:
            raise Exception(f"Transfer failed: {e}")
    
    def _append_to_target(self, target_file, new_table):
        """Append data to target file with proper locking"""
        # Use file-based lock
        lock_file = Path(str(target_file) + '.lock')
        
        max_retries = 10
        retry_delay = 0.5
        
        for attempt in range(max_retries):
            try:
                # Try to create lock file (atomic operation)
                lock_fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                
                try:
                    # Read existing data if file exists
                    if target_file.exists():
                        existing_table = pq.read_table(target_file)
                        combined_table = pa.concat_tables([existing_table, new_table])
                    else:
                        combined_table = new_table
                    
                    # Write to temporary file first
                    temp_file = Path(str(target_file) + '.tmp')
                    pq.write_table(combined_table, temp_file, compression='snappy')
                    
                    # Atomic rename
                    temp_file.replace(target_file)
                    
                finally:
                    # Release lock
                    os.close(lock_fd)
                    lock_file.unlink()
                
                return  # Success
                
            except FileExistsError:
                # Lock file exists, retry
                time.sleep(retry_delay)
                continue
            
            except Exception as e:
                # Clean up lock if error
                try:
                    if lock_file.exists():
                        lock_file.unlink()
                except:
                    pass
                raise e
        
        raise Exception(f"Could not acquire lock after {max_retries} attempts")
    
    def get_status(self):
        """Get current status (thread-safe)"""
        with self.lock:
            pending_count = len(list(self.source_dir.glob('*.parquet'))) if self.source_dir.exists() else 0
            
            return {
                'running': self.running,
                'files_transferred': self.files_transferred,
                'records_transferred': self.records_transferred,
                'pending_files': pending_count,
                'last_transfer': self.last_transfer_time.isoformat() if self.last_transfer_time else None,
                'errors': self.errors[-10:] if self.errors else []  # Last 10 errors
            }
