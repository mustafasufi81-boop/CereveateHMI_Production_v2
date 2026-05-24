"""
Tag Cache Service - Loads mapped tags from database
Runs in background, refreshes every 30 seconds
"""
import logging
import psycopg2
import threading
import time

logger = logging.getLogger(__name__)


class TagCacheService:
    """
    Manages the list of mapped tags from database
    Background thread keeps cache fresh
    """
    
    def __init__(self, db_config):
        self.db_config = db_config
        self.mapped_tags = []  # List of tag dictionaries
        self.tag_ids = set()   # Set of tag IDs for quick lookup
        self.last_update = 0
        self.refresh_interval = 30  # Refresh every 30 seconds
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        
    def start(self):
        """Start background refresh thread"""
        if self.running:
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self.thread.start()
        logger.info("[OK] Tag cache service started")
        
    def stop(self):
        """Stop background thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("[STOP] Tag cache service stopped")
        
    def _refresh_loop(self):
        """Background loop to refresh tag cache"""
        # Initial load
        self._load_tags()
        
        while self.running:
            time.sleep(self.refresh_interval)
            self._load_tags()
            
    def _load_tags(self):
        """Load mapped tags from database"""
        try:
            conn = psycopg2.connect(
                host=self.db_config['host'],
                port=self.db_config['port'],
                database=self.db_config['database'],
                user=self.db_config['user'],
                password=self.db_config['password']
            )
            
            cur = conn.cursor()
            cur.execute("""
                SELECT tag_id, tag_name, data_type, eng_unit, plant, area, equipment
                FROM historian_meta.tag_master
                WHERE enabled = true
                ORDER BY tag_id
            """)
            
            rows = cur.fetchall()
            
            with self.lock:
                self.mapped_tags = [
                    {
                        'tag_id': row[0],
                        'tag_name': row[1],
                        'data_type': row[2],
                        'eng_unit': row[3] or '',
                        'plant': row[4] or '',
                        'area': row[5] or '',
                        'equipment': row[6] or ''
                    }
                    for row in rows
                ]
                self.tag_ids = {tag['tag_id'] for tag in self.mapped_tags}
                self.last_update = time.time()
                
            cur.close()
            conn.close()
            
            logger.info(f"[OK] Loaded {len(self.mapped_tags)} mapped tags from database")
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to load tags from database: {e}")
            
    def get_all_tags(self):
        """Get all mapped tags (thread-safe)"""
        with self.lock:
            return self.mapped_tags.copy()
            
    def get_tag_ids(self):
        """Get set of tag IDs (thread-safe)"""
        with self.lock:
            return self.tag_ids.copy()
            
    def is_tag_mapped(self, tag_id):
        """Check if tag is mapped (thread-safe)"""
        with self.lock:
            return tag_id in self.tag_ids
