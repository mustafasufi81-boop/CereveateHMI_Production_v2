"""
SignalR Listener Service
Connects to C# OPC backend and receives real-time tag updates
Uses tag cache to subscribe only to mapped tags
"""
import logging
from signalrcore.hub_connection_builder import HubConnectionBuilder
import time
import threading

logger = logging.getLogger(__name__)


class SignalRListener:
    """
    Manages SignalR connection to C# backend
    Subscribes to tags from tag cache and forwards updates to callback
    """
    
    def __init__(self, signalr_config, tag_cache, on_update_callback):
        """
        Initialize SignalR listener
        
        Args:
            signalr_config: Dict with host, port, hub_path
            tag_cache: TagCacheService instance
            on_update_callback: Function to call with tag updates
        """
        self.host = signalr_config['host']
        self.port = signalr_config['port']
        self.hub_path = signalr_config['hub_path']
        self.base_url = f"http://{self.host}:{self.port}"
        self.hub_url = f"{self.base_url}{self.hub_path}"
        self.tag_cache = tag_cache
        self.on_update_callback = on_update_callback
        
        self.connection = None
        self.is_connected = False
        
        # Batching to reduce update frequency
        self.update_buffer = []
        self.buffer_lock = threading.Lock()
        self.batch_interval = 0.2  # 200ms batching
        self.last_batch_time = time.time()
        
    def connect(self):
        """Establish SignalR connection"""
        try:
            logger.info(f"🔌 Connecting to SignalR hub: {self.hub_url}")
            
            self.connection = HubConnectionBuilder() \
                .with_url(self.hub_url) \
                .configure_logging(logging.WARNING) \
                .with_automatic_reconnect({
                    "type": "interval",
                    "intervals": [0, 2, 5, 10, 30]
                }) \
                .build()
            
            # Register handler for tag updates
            self.connection.on("TagValuesUpdated", self._on_tag_values_updated)
            
            # Connection lifecycle handlers
            self.connection.on_open(self._on_connected)
            self.connection.on_close(self._on_disconnected)
            self.connection.on_error(self._on_error)
            
            # Start connection
            self.connection.start()
            
            logger.info("✅ SignalR connection initiated")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to SignalR: {e}")
            self.is_connected = False
            
    def _on_connected(self):
        """Called when connection is established"""
        self.is_connected = True
        logger.info("✅ SignalR connected successfully")
        
        # Start subscription in background thread
        threading.Thread(target=self._subscribe_to_tags, daemon=True).start()
        
    def _on_disconnected(self):
        """Called when connection is lost"""
        self.is_connected = False
        logger.warning("⚠️  SignalR disconnected")
        
    def _on_error(self, error):
        """Called on connection error"""
        logger.error(f"❌ SignalR error: {error}")
        
    def _subscribe_to_tags(self):
        """
        Subscribe to tags from tag cache after connection is established
        Runs in separate thread
        """
        time.sleep(2)  # Give connection and tag cache time to initialize
        
        try:
            # Get tag IDs from cache
            tag_ids = list(self.tag_cache.get_tag_ids())
            
            if tag_ids:
                logger.info(f"📝 Subscribing to {len(tag_ids)} tags from cache...")
                logger.info(f"   Sample tags: {tag_ids[:5]}")
                
                # Call SubscribeToTags hub method
                self.connection.send("SubscribeToTags", [tag_ids])
                logger.info(f"✅ Subscribed to {len(tag_ids)} tags")
            else:
                logger.warning("⚠️  No tags in cache - waiting for tag cache to load...")
                # Wait a bit and try again
                time.sleep(2)
                tag_ids = list(self.tag_cache.get_tag_ids())
                if tag_ids:
                    self.connection.send("SubscribeToTags", [tag_ids])
                    logger.info(f"✅ Subscribed to {len(tag_ids)} tags (retry)")
                else:
                    logger.error("❌ Still no tags in cache - check database connection")
                
        except Exception as e:
            logger.error(f"❌ Failed to subscribe to tags: {e}")
            
    def _on_tag_values_updated(self, data):
        """
        Handle TagValuesUpdated event from C# backend
        Batches updates to reduce callback frequency
        
        Args:
            data: Can be array of tags [[{tag1}, {tag2}]] or [{tag1}, {tag2}]
        """
        try:
            # Unwrap nested array if present (signalrcore sometimes wraps data)
            if isinstance(data, list) and len(data) > 0:
                if isinstance(data[0], list):
                    tags_data = data[0]  # Unwrap [[tags]] -> [tags]
                else:
                    tags_data = data     # Already [tags]
            else:
                tags_data = data
                
            if not isinstance(tags_data, list):
                return
                
            # Add to buffer
            with self.buffer_lock:
                self.update_buffer.extend(tags_data)
                
                # Check if batch interval elapsed
                current_time = time.time()
                if current_time - self.last_batch_time >= self.batch_interval:
                    # Flush buffer
                    if self.update_buffer:
                        batch = self.update_buffer.copy()
                        self.update_buffer.clear()
                        self.last_batch_time = current_time
                        
                        # Call callback (runs in background)
                        threading.Thread(
                            target=self.on_update_callback,
                            args=(batch,),
                            daemon=True
                        ).start()
                        
        except Exception as e:
            logger.error(f"❌ Error processing tag update: {e}")
            
    def stop(self):
        """Stop SignalR connection"""
        try:
            if self.connection:
                self.connection.stop()
                self.is_connected = False
                logger.info("✅ SignalR connection stopped")
        except Exception as e:
            logger.error(f"❌ Error stopping SignalR: {e}")
