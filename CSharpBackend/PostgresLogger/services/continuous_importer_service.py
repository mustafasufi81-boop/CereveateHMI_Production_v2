"""
CONTINUOUS IMPORTER SERVICE
Monitors parquet directory and processes new files automatically

Features:
- File system watcher (detects new files instantly)
- Config change detection (re-processes when new tags mapped)
- Periodic queue processing (handles backlog)
- Graceful shutdown (Ctrl+C)
"""

import os
import sys
import time
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.high_performance_importer import HighPerformanceImporter
from utils.config_manager import get_config_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    handlers=[
        logging.FileHandler('continuous_importer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ParquetFileEventHandler(FileSystemEventHandler):
    """Handle file system events for parquet files"""
    
    def __init__(self, importer, stability_wait=5):
        self.importer = importer
        self.stability_wait = stability_wait
        self.pending_files = {}
    
    def on_created(self, event):
        """New file created"""
        if event.is_directory:
            return
        
        if event.src_path.endswith('.parquet'):
            logger.info(f"📁 New file detected: {event.src_path}")
            self.pending_files[event.src_path] = time.time()
    
    def on_modified(self, event):
        """File modified (still being written)"""
        if event.is_directory:
            return
        
        if event.src_path.endswith('.parquet'):
            # Update last modified time
            self.pending_files[event.src_path] = time.time()
    
    def process_pending_files(self):
        """Process files that haven't been modified for stability_wait seconds"""
        current_time = time.time()
        files_to_process = []
        
        for file_path, last_modified in list(self.pending_files.items()):
            if current_time - last_modified > self.stability_wait:
                files_to_process.append(file_path)
                del self.pending_files[file_path]
        
        for file_path in files_to_process:
            logger.info(f"⚙️  Processing stable file: {file_path}")
            
            # Enqueue file
            if self.importer.enqueue_file(file_path):
                # Process immediately
                file_metadata = self.importer.get_next_pending_file()
                if file_metadata:
                    self.importer.import_file(file_metadata)


class ContinuousImporterService:
    """
    Continuous importer service with:
    - File system monitoring
    - Config change detection
    - Periodic queue processing
    """
    
    def __init__(self):
        self.config_manager = get_config_manager()
        self.importer = HighPerformanceImporter()
        self.observer = None
        self.running = False
        
        # Track config state
        self._last_tag_count = len(self.config_manager.get_enabled_tag_mappings())
        self._last_config_check = time.time()
    
    def initial_scan(self):
        """Scan directory and enqueue existing files"""
        logger.info("=" * 80)
        logger.info("INITIAL DIRECTORY SCAN")
        logger.info("=" * 80)
        
        data_dir = self.config_manager.get_parquet_source_config().get('data_directory')
        
        if not os.path.exists(data_dir):
            logger.error(f"❌ Data directory not found: {data_dir}")
            return False
        
        logger.info(f"📂 Scanning: {data_dir}")
        
        # Enqueue all files
        self.importer.scan_and_enqueue_directory(data_dir)
        
        # Process queue
        logger.info("⚙️  Processing enqueued files...")
        processed = self.importer.process_queue()
        
        self.importer.print_stats()
        
        logger.info("=" * 80)
        logger.info(f"✅ Initial scan complete ({processed} files processed)")
        logger.info("=" * 80)
        
        return True
    
    def check_config_changes(self):
        """Check if tag mappings changed and trigger re-import if needed"""
        current_tag_count = len(self.config_manager.get_enabled_tag_mappings())
        
        if current_tag_count != self._last_tag_count:
            logger.info("=" * 80)
            logger.info(f"🔄 CONFIG CHANGE DETECTED")
            logger.info(f"   Tag count: {self._last_tag_count} → {current_tag_count}")
            logger.info("=" * 80)
            
            if current_tag_count > self._last_tag_count:
                # New tags added - re-process all files
                added_count = current_tag_count - self._last_tag_count
                logger.info(f"➕ {added_count} new tag(s) added")
                logger.info("⚙️  Re-processing all files for new tags...")
                
                # Re-enqueue all files (idempotent)
                data_dir = self.config_manager.get_parquet_source_config().get('data_directory')
                self.importer.scan_and_enqueue_directory(data_dir)
                
                # Process queue
                processed = self.importer.process_queue()
                
                logger.info(f"✅ Re-import complete ({processed} files processed)")
                self.importer.print_stats()
            
            self._last_tag_count = current_tag_count
            logger.info("=" * 80)
    
    def start_file_watcher(self):
        """Start file system watcher"""
        data_dir = self.config_manager.get_parquet_source_config().get('data_directory')
        stability_wait = self.config_manager.get_parquet_source_config().get('stability_wait_seconds', 5)
        
        event_handler = ParquetFileEventHandler(self.importer, stability_wait)
        self.observer = Observer()
        self.observer.schedule(event_handler, data_dir, recursive=False)
        self.observer.start()
        
        logger.info(f"👁️  Watching directory: {data_dir}")
        logger.info(f"⏱️  Stability wait: {stability_wait} seconds")
        
        return event_handler
    
    def run(self):
        """Main service loop"""
        logger.info("=" * 80)
        logger.info("CONTINUOUS PARQUET IMPORTER SERVICE")
        logger.info("=" * 80)
        
        # Initial scan and import
        if not self.initial_scan():
            logger.error("❌ Initial scan failed")
            return
        
        # Start file watcher
        event_handler = self.start_file_watcher()
        
        logger.info("=" * 80)
        logger.info("✅ SERVICE RUNNING")
        logger.info("   Press Ctrl+C to stop")
        logger.info("=" * 80)
        
        self.running = True
        
        # Configuration
        queue_check_interval = self.config_manager.get_parquet_source_config().get('check_interval_seconds', 10)
        config_check_interval = 5  # Check config every 5 seconds
        
        last_queue_check = time.time()
        last_config_check = time.time()
        
        try:
            while self.running:
                current_time = time.time()
                
                # Process pending files from watcher
                event_handler.process_pending_files()
                
                # Periodic queue check (handle any backlog)
                if current_time - last_queue_check >= queue_check_interval:
                    processed = self.importer.process_queue(max_files=10)
                    if processed > 0:
                        logger.info(f"⚙️  Processed {processed} files from queue")
                    last_queue_check = current_time
                
                # Periodic config check
                if current_time - last_config_check >= config_check_interval:
                    self.check_config_changes()
                    last_config_check = current_time
                
                # Sleep briefly
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("\n🛑 Shutdown requested...")
            self.stop()
    
    def stop(self):
        """Stop service gracefully"""
        logger.info("Stopping file watcher...")
        if self.observer:
            self.observer.stop()
            self.observer.join()
        
        logger.info("Printing final statistics...")
        self.importer.print_stats()
        
        logger.info("=" * 80)
        logger.info("✅ SERVICE STOPPED")
        logger.info("=" * 80)
        
        self.running = False


def main():
    """Main entry point"""
    service = ContinuousImporterService()
    service.run()


if __name__ == "__main__":
    main()
