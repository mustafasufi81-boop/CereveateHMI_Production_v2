"""
Configuration Manager for PostgreSQL Logger
Handles tag mappings, database config, and auto-discovery
"""

import json
import os
from typing import List, Dict, Optional
from pathlib import Path
import threading

class ConfigManager:
    def __init__(self, config_path: str = "config/app_config.json"):
        self.config_path = config_path
        self.config = {}
        self._lock = threading.Lock()
        self.load_config()
    
    def load_config(self):
        """Load configuration from JSON file"""
        with self._lock:
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                print(f"[OK] Configuration loaded from {self.config_path}")
            except FileNotFoundError:
                print(f"[WARN] Config file not found: {self.config_path}")
                self.config = self._get_default_config()
                self.save_config()
            except Exception as e:
                print(f"[ERROR] Error loading config: {e}")
                self.config = self._get_default_config()
    
    def _save_config_unlocked(self):
        """Internal: Save config without acquiring lock (caller must hold lock)"""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            print(f"[OK] Configuration saved to {self.config_path}")
            return True
        except Exception as e:
            print(f"[ERROR] Error saving config: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def save_config(self):
        """Save configuration to JSON file"""
        with self._lock:
            return self._save_config_unlocked()
    
    def get_db_config(self) -> Dict:
        """Get database connection configuration"""
        return self.config.get('database', {})
    
    def get_parquet_source_config(self) -> Dict:
        """Get parquet source directory configuration"""
        return self.config.get('parquet_source', {})
    
    def get_tag_mappings(self) -> List[Dict]:
        """Get all tag mappings"""
        return self.config.get('tag_mappings', [])
    
    def get_enabled_tag_mappings(self) -> List[Dict]:
        """Get only enabled tag mappings"""
        return [m for m in self.get_tag_mappings() if m.get('enabled', True)]
    
    def get_tag_mapping(self, parquet_column: str) -> Optional[Dict]:
        """Get mapping for specific parquet column"""
        for mapping in self.get_tag_mappings():
            if mapping['parquet_column'] == parquet_column:
                return mapping
        return None
    
    def add_tag_mapping(self, mapping: Dict) -> bool:
        """Add new tag mapping"""
        print(f"[DEBUG ConfigManager] add_tag_mapping called with: {mapping}")
        with self._lock:
            # Check if already exists
            existing = self.get_tag_mapping(mapping['parquet_column'])
            print(f"[DEBUG ConfigManager] Existing mapping: {existing}")
            if existing:
                print(f"⚠ Tag mapping already exists for {mapping['parquet_column']}")
                return False
            
            print(f"[DEBUG ConfigManager] Appending to tag_mappings array")
            self.config['tag_mappings'].append(mapping)
            print(f"[DEBUG ConfigManager] Calling _save_config_unlocked()")
            result = self._save_config_unlocked()
            print(f"[DEBUG ConfigManager] _save_config_unlocked returned: {result}")
            return result
    
    def update_tag_mapping(self, parquet_column: str, updated_mapping: Dict) -> bool:
        """Update existing tag mapping"""
        with self._lock:
            for i, mapping in enumerate(self.config['tag_mappings']):
                if mapping['parquet_column'] == parquet_column:
                    self.config['tag_mappings'][i] = updated_mapping
                    return self._save_config_unlocked()
            return False
    
    def delete_tag_mapping(self, parquet_column: str) -> bool:
        """Delete tag mapping"""
        with self._lock:
            original_count = len(self.config['tag_mappings'])
            self.config['tag_mappings'] = [
                m for m in self.config['tag_mappings'] 
                if m['parquet_column'] != parquet_column
            ]
            if len(self.config['tag_mappings']) < original_count:
                return self._save_config_unlocked()
            return False
    
    def auto_discover_tags(self, parquet_columns: List[str]) -> List[Dict]:
        """
        Auto-discover new tags from parquet file columns
        Creates default mappings for unmapped columns
        """
        auto_config = self.config.get('auto_discovery', {})
        existing_columns = {m['parquet_column'] for m in self.get_tag_mappings()}
        
        new_mappings = []
        for column in parquet_columns:
            if column not in existing_columns and column != 'Timestamp':
                # Create default mapping
                new_mapping = {
                    "parquet_column": column,
                    "tag_name": column,
                    "plant": auto_config.get('default_plant', 'UnknownPlant'),
                    "asset": auto_config.get('default_asset', 'UnknownAsset'),
                    "subsystem": auto_config.get('default_subsystem', 'General'),
                    "unit": auto_config.get('default_unit', ''),
                    "sampling_frequency_seconds": auto_config.get('default_frequency_seconds', 5),
                    "enabled": True
                }
                new_mappings.append(new_mapping)
        
        return new_mappings
    
    def add_auto_discovered_tags(self, new_mappings: List[Dict]) -> int:
        """Add auto-discovered tags to configuration"""
        count = 0
        for mapping in new_mappings:
            if self.add_tag_mapping(mapping):
                count += 1
        return count
    
    def get_web_ui_config(self) -> Dict:
        """Get web UI configuration"""
        return self.config.get('web_ui', {})
    
    def get_import_settings(self) -> Dict:
        """Get import settings"""
        return self.config.get('import_settings', {})
    
    def _get_default_config(self) -> Dict:
        """Get default configuration"""
        return {
            "database": {
                "host": "localhost",
                "port": 5432,
                "database": "Cereveate",
                "user": "cereveate",
                "password": "cereveate@222"
            },
            "parquet_source": {
                "data_directory": "D:\\OpcLogs\\Data",
                "file_pattern": "*.parquet",
                "check_interval_seconds": 10,
                "stability_wait_seconds": 5
            },
            "tag_mappings": [],
            "auto_discovery": {
                "enabled": True,
                "default_plant": "UnknownPlant",
                "default_asset": "UnknownAsset",
                "default_subsystem": "General",
                "default_unit": ""
            },
            "import_settings": {
                "batch_size": 10000,
                "max_retries": 3,
                "retry_delay_seconds": 60,
                "enable_compression": True
            },
            "web_ui": {
                "port": 8001,
                "host": "0.0.0.0",
                "title": "Cereveate Database Trends",
                "refresh_interval_seconds": 5,
                "default_chart_points": 1000,
                "max_chart_points": 50000
            }
        }


# Global instance
_config_manager = None

def get_config_manager(config_path: str = "config/app_config.json") -> ConfigManager:
    """Get singleton config manager instance"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(config_path)
    return _config_manager
