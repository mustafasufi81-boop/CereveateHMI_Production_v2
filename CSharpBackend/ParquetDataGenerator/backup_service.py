"""
Backup Service - Optional file backup to custom location
Thread-safe background service
"""
import threading
import time
from datetime import datetime
from pathlib import Path
import shutil
import os


class BackupService:
    def __init__(self, config):
        self.config = config
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        
        # Directories
        self.source_dir = Path(config['Paths']['MainDataDirectory'])
        self.backup_dir = Path(config['Paths']['BackupDirectory']) if config['Paths']['BackupDirectory'] else None
        
        # Statistics
        self.files_backed_up = 0
        self.last_backup_time = None
        self.errors = []
        
    def start(self):
        """Start backup service"""
        if not self.config['Backup']['Enabled']:
            return {'success': False, 'message': 'Backup service not enabled in config'}
        
        if not self.backup_dir:
            print("[BackupService] No backup directory configured")
            return {'success': False, 'message': 'No backup directory configured'}
        
        if self.running:
            return {'success': False, 'message': 'Backup service already running'}
        
        # Create backup directory
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        self.running = True
        self.thread = threading.Thread(target=self._backup_loop, daemon=True)
        self.thread.start()
        return {'success': True, 'message': 'Backup service started'}
    
    def stop(self):
        """Stop backup service"""
        if not self.running:
            return {'success': False, 'message': 'Backup service not running'}
        
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        return {'success': True, 'message': 'Backup service stopped'}
    
    def _backup_loop(self):
        """Main backup loop"""
        print(f"[BackupService] Started - {self.source_dir} → {self.backup_dir}")
        
        while self.running:
            try:
                self._perform_backup()
                time.sleep(self.config['Backup']['BackupIntervalSeconds'])
                
            except Exception as e:
                print(f"[BackupService] Error: {e}")
                with self.lock:
                    self.errors.append(str(e))
                time.sleep(1)
    
    def _perform_backup(self):
        """Perform backup of new/modified files"""
        if not self.source_dir.exists():
            return
        
        parquet_files = list(self.source_dir.glob('*.parquet'))
        
        for source_file in parquet_files:
            try:
                target_file = self.backup_dir / source_file.name
                
                # Check if backup needed
                if target_file.exists():
                    source_mtime = source_file.stat().st_mtime
                    target_mtime = target_file.stat().st_mtime
                    
                    if source_mtime <= target_mtime:
                        continue  # Already backed up
                
                # Copy file
                shutil.copy2(source_file, target_file)
                
                with self.lock:
                    self.files_backed_up += 1
                    self.last_backup_time = datetime.now()
                
                print(f"[BackupService] 💾 Backed up: {source_file.name}")
                
            except Exception as e:
                print(f"[BackupService] Error backing up {source_file.name}: {e}")
                with self.lock:
                    self.errors.append(f"{source_file.name}: {str(e)}")
    
    def get_status(self):
        """Get current status"""
        with self.lock:
            return {
                'running': self.running,
                'enabled': self.config['Backup']['Enabled'],
                'backup_directory': str(self.backup_dir) if self.backup_dir else None,
                'files_backed_up': self.files_backed_up,
                'last_backup': self.last_backup_time.isoformat() if self.last_backup_time else None,
                'errors': self.errors[-10:] if self.errors else []
            }
