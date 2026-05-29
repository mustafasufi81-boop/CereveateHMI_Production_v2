"""
Topic-Tag Mapper Service
Maps MQTT topics to tags based on plc_name/server_progid relationship
Loads configuration from mqtt_topic_config and tag_master tables
"""

import logging
import threading
from typing import Dict, List, Optional, Set
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


class TopicTagMapper:
    """
    Maps MQTT topics to tags based on database configuration
    Relationship: mqtt_topic_config.plc_name ↔ tag_master.server_progid
    """
    
    def __init__(self, db_config: dict, refresh_interval: int = 300):
        """
        Initialize Topic-Tag Mapper
        
        Args:
            db_config: Database configuration dict
            refresh_interval: Cache refresh interval in seconds (default: 5 minutes)
        """
        self.db_config = db_config
        self.refresh_interval = refresh_interval
        
        # Cache structures
        self._topic_to_plc_map: Dict[str, dict] = {}  # topic_name -> {plc_name, qos, ...}
        self._plc_to_tags_map: Dict[str, List[dict]] = {}  # plc_name -> [tag_info, ...]
        self._tag_to_plc_map: Dict[str, str] = {}  # tag_id -> plc_name
        
        self._lock = threading.RLock()
        self._refresh_timer = None
        
        logger.info(f"TopicTagMapper initialized with {refresh_interval}s refresh interval")
    
    def load_configuration(self):
        """Load topic and tag configuration from database"""
        with self._lock:
            try:
                logger.info("Loading topic-tag mapping configuration...")
                
                # Load mqtt_topic_config
                self._load_topic_config()
                
                # Load tag_master and build plc-to-tags mapping
                self._load_tag_mappings()
                
                logger.info(f"✓ Configuration loaded: {len(self._topic_to_plc_map)} topics, "
                          f"{len(self._plc_to_tags_map)} PLCs, {len(self._tag_to_plc_map)} tags")
                
                # Schedule next refresh
                self._schedule_refresh()
                
            except Exception as e:
                logger.error(f"Failed to load topic-tag mapping configuration: {e}")
                raise
    
    def _load_topic_config(self):
        """Load MQTT topic configuration from database"""
        try:
            conn = psycopg2.connect(**self.db_config)
            
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                query = """
                    SELECT 
                        topic_id,
                        topic_name,
                        plc_name,
                        qos,
                        is_active,
                        thread_group
                    FROM historian_raw.mqtt_topic_config
                    WHERE is_active = true
                    ORDER BY topic_name
                """
                
                cursor.execute(query)
                rows = cursor.fetchall()
                
                new_map = {}
                for row in rows:
                    topic_name = row['topic_name']
                    new_map[topic_name] = {
                        'topic_id': row['topic_id'],
                        'topic_name': topic_name,
                        'plc_name': row['plc_name'],
                        'qos': row['qos'],
                        'is_active': row['is_active'],
                        'thread_group': row['thread_group']
                    }
                
                self._topic_to_plc_map = new_map
                logger.info(f"✓ Loaded {len(self._topic_to_plc_map)} active MQTT topics")
            
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to load MQTT topic configuration: {e}")
            raise
    
    def _load_tag_mappings(self):
        """Load tag master and build PLC-to-tags mapping"""
        try:
            conn = psycopg2.connect(**self.db_config)
            
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Get all enabled tags with server_progid
                query = """
                    SELECT 
                        tag_id,
                        tag_name,
                        server_progid,
                        data_type,
                        eng_unit,
                        plant,
                        area,
                        equipment,
                        description
                    FROM historian_meta.tag_master
                    WHERE enabled = true 
                        AND server_progid IS NOT NULL
                    ORDER BY tag_id
                """
                
                cursor.execute(query)
                rows = cursor.fetchall()
                
                # Build plc_name -> tags mapping
                plc_to_tags = {}
                tag_to_plc = {}
                
                for row in rows:
                    tag_id = row['tag_id']
                    server_progid = row['server_progid']
                    
                    tag_info = {
                        'tag_id': tag_id,
                        'tag_name': row['tag_name'],
                        'server_progid': server_progid,
                        'data_type': row['data_type'],
                        'eng_unit': row['eng_unit'],
                        'plant': row['plant'],
                        'area': row['area'],
                        'equipment': row['equipment'],
                        'description': row['description']
                    }
                    
                    # Add to plc_to_tags map
                    if server_progid not in plc_to_tags:
                        plc_to_tags[server_progid] = []
                    plc_to_tags[server_progid].append(tag_info)
                    
                    # Add to tag_to_plc map
                    tag_to_plc[tag_id] = server_progid
                
                self._plc_to_tags_map = plc_to_tags
                self._tag_to_plc_map = tag_to_plc
                
                # ── ROOT-LEVEL AUTO-DERIVE ─────────────────────────────────────────────
                # For every server_progid in tag_master, automatically register the
                # canonical topic  opc/{server_progid}/tags/bulk  so that NO manual
                # mqtt_topic_config rows are ever needed.  This is the permanent fix:
                # any new OPC server added to tag_master instantly gets a working topic.
                for server_progid in plc_to_tags:
                    auto_topic = f"opc/{server_progid}/tags/bulk"
                    if auto_topic not in self._topic_to_plc_map:
                        self._topic_to_plc_map[auto_topic] = {
                            'topic_id': None,
                            'topic_name': auto_topic,
                            'plc_name': server_progid,
                            'qos': 0,
                            'is_active': True,
                            'thread_group': 'auto'
                        }
                        logger.info(f"  [auto-topic] {auto_topic} → {server_progid}")
                # ──────────────────────────────────────────────────────────────────────
                
                logger.info(f"✓ Loaded {len(tag_to_plc)} tags mapped to {len(plc_to_tags)} PLCs")
            
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to load tag mappings: {e}")
            raise
    
    def _schedule_refresh(self):
        """Schedule automatic cache refresh"""
        if self._refresh_timer:
            self._refresh_timer.cancel()
        
        self._refresh_timer = threading.Timer(self.refresh_interval, self.load_configuration)
        self._refresh_timer.daemon = True
        self._refresh_timer.start()
    
    def filter_tags_for_topic(self, topic: str, tags: List[dict]) -> List[dict]:
        """
        Filter tags that belong to the given MQTT topic
        Based on topic -> plc_name -> server_progid -> tags relationship
        
        Args:
            topic: MQTT topic name
            tags: List of tag dicts from MQTT payload
            
        Returns:
            Filtered list of tags that match the topic's PLC
        """
        with self._lock:
            # Get plc_name for this topic
            topic_info = self._topic_to_plc_map.get(topic)
            
            # ── PERMANENT PATTERN FALLBACK ─────────────────────────────────────────
            # If the topic is not in our map yet (e.g. cache cold, or brand-new
            # server_progid), parse it directly from the canonical pattern
            # opc/{server_progid}/tags/bulk — no DB row required.
            if not topic_info:
                parts = topic.split('/')
                derived_progid = None
                # Pattern 1: opc/{server_progid}/tags/bulk  (OPC DA topics)
                if len(parts) == 4 and parts[0] == 'opc' and parts[2] == 'tags' and parts[3] == 'bulk':
                    derived_progid = parts[1]
                # Pattern 2: bare topic IS the server_progid (PLC gateway topics, e.g. "Rockwel_PLC_001")
                elif topic in self._plc_to_tags_map:
                    derived_progid = topic
                if derived_progid:
                    logger.info(f"[auto-derive] Topic '{topic}' -> server_progid='{derived_progid}'")
                    topic_info = {'plc_name': derived_progid}
                    # Register it so next message is instant
                    self._topic_to_plc_map[topic] = {
                        'topic_id': None, 'topic_name': topic,
                        'plc_name': derived_progid, 'qos': 0,
                        'is_active': True, 'thread_group': 'auto'
                    }
            # ──────────────────────────────────────────────────────────────────────
            
            if not topic_info:
                logger.warning(f"Topic not found in configuration: {topic}")
                return []
            
            plc_name = topic_info['plc_name']
            
            # Get valid tag_ids and tag_names for this PLC
            valid_tags = self._plc_to_tags_map.get(plc_name, [])
            valid_tag_ids = {tag['tag_id'] for tag in valid_tags}
            valid_tag_names = {tag['tag_name'] for tag in valid_tags}
            
            # Filter incoming tags (match by tag_id OR tag_name)
            filtered = []
            for tag in tags:
                tag_id = tag.get('tag_id')
                # Check both tag_id (numeric) and tag name (string)
                if (tag_id and tag_id in valid_tag_ids) or (tag_id and tag_id in valid_tag_names):
                    filtered.append(tag)
            
            return filtered
    
    def get_active_topics(self) -> List[dict]:
        """Get list of all active MQTT topics"""
        with self._lock:
            return list(self._topic_to_plc_map.values())

    def get_all_plc_names(self) -> List[str]:
        """Get all PLC/server_progid names from tag master mapping"""
        with self._lock:
            return list(self._plc_to_tags_map.keys())
    
    def get_tags_for_topic(self, topic: str) -> List[dict]:
        """
        Get all tags associated with a topic
        
        Args:
            topic: MQTT topic name
            
        Returns:
            List of tag info dicts
        """
        with self._lock:
            topic_info = self._topic_to_plc_map.get(topic)
            if not topic_info:
                return []
            
            plc_name = topic_info['plc_name']
            return self._plc_to_tags_map.get(plc_name, [])
    
    def get_tags_for_plc(self, plc_name: str) -> List[dict]:
        """
        Get all tags for a specific PLC
        
        Args:
            plc_name: PLC name (server_progid)
            
        Returns:
            List of tag info dicts
        """
        with self._lock:
            return self._plc_to_tags_map.get(plc_name, []).copy()
    
    def get_plc_for_topic(self, topic: str) -> Optional[str]:
        """Get PLC name for a topic"""
        with self._lock:
            topic_info = self._topic_to_plc_map.get(topic)
            return topic_info['plc_name'] if topic_info else None
    
    def get_topic_for_plc(self, plc_name: str) -> Optional[str]:
        """Get topic name for a PLC"""
        with self._lock:
            for topic, info in self._topic_to_plc_map.items():
                if info['plc_name'] == plc_name:
                    return topic
            return None
    
    def is_tag_valid_for_topic(self, topic: str, tag_id: str) -> bool:
        """Check if a tag_id is valid for a given topic"""
        with self._lock:
            topic_info = self._topic_to_plc_map.get(topic)
            if not topic_info:
                return False
            
            plc_name = topic_info['plc_name']
            return self._tag_to_plc_map.get(tag_id) == plc_name
    
    def get_summary(self) -> dict:
        """Get configuration summary statistics"""
        with self._lock:
            return {
                'total_topics': len(self._topic_to_plc_map),
                'total_plcs': len(self._plc_to_tags_map),
                'total_tags': len(self._tag_to_plc_map),
                'topics': list(self._topic_to_plc_map.keys()),
                'plcs': list(self._plc_to_tags_map.keys())
            }
