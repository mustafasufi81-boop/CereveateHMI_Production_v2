"""
Baseline Configuration Manager
Handles ALL configuration settings for Advanced BI Dashboard
"""
import json
import os
from datetime import datetime

class BaselineConfigManager:
    def __init__(self, config_path='baseline_config.json'):
        self.config_path = config_path
        self.config = self._load_config()
    
    def _load_config(self):
        """Load baseline configuration"""
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                return json.load(f)
        return {"global_settings": {}, "tags": {}}
    
    def _save_config(self):
        """Save baseline configuration"""
        self.config['_config_info']['last_updated'] = datetime.now().isoformat()
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def get_global_setting(self, key, default=None):
        """Get global setting value"""
        return self.config.get('global_settings', {}).get(key, default)
    
    def get_tag_config(self, tag):
        """Get complete configuration for a tag"""
        return self.config.get('tags', {}).get(tag, {})
    
    def get_all_tags(self):
        """Get list of all configured tags"""
        return list(self.config.get('tags', {}).keys())
    
    def get_target_production(self, tag):
        """Get target production for a tag"""
        tag_config = self.config.get('tags', {}).get(tag)
        if not tag_config:
            return None
        
        target = tag_config.get('target_production', {})
        
        # If user defined, return user value
        if target.get('user_defined') and target.get('value') is not None:
            return {
                'value': target['value'],
                'source': 'user'
            }
        
        # Otherwise return rated capacity if available
        rated_capacity = tag_config.get('rated_capacity')
        if rated_capacity:
            return {
                'value': rated_capacity,
                'source': 'machine'
            }
        
        return None
    
    def set_user_target(self, tag, value):
        """Set user-defined target production"""
        if 'tags' not in self.config:
            self.config['tags'] = {}
        if tag not in self.config['tags']:
            self.config['tags'][tag] = {}
        
        self.config['tags'][tag]['target_production'] = {
            'value': value,
            'source': 'user',
            'user_defined': True
        }
        self.config['tags'][tag]['last_updated'] = datetime.now().isoformat()
        self._save_config()
    
    def clear_user_target(self, tag):
        """Clear user-defined target, revert to machine calculation"""
        if tag in self.config.get('tags', {}) and 'target_production' in self.config['tags'][tag]:
            self.config['tags'][tag]['target_production'] = {
                'value': None,
                'source': 'machine',
                'user_defined': False
            }
            self.config['tags'][tag]['last_updated'] = datetime.now().isoformat()
            self._save_config()
    
    def get_baseline_performance(self, tag):
        """Get baseline performance (historical best)"""
        tag_config = self.config.get('tags', {}).get(tag)
        if not tag_config:
            return None
        return tag_config.get('baseline_performance')
    
    def set_baseline_performance(self, tag, value, sample_size=None):
        """Set baseline performance (auto-calculated from historical data)"""
        if 'tags' not in self.config:
            self.config['tags'] = {}
        if tag not in self.config['tags']:
            self.config['tags'][tag] = {}
        
        self.config['tags'][tag]['baseline_performance'] = value
        self.config['tags'][tag]['baseline_calculated_date'] = datetime.now().isoformat()
        if sample_size:
            self.config['tags'][tag]['baseline_sample_size'] = sample_size
        self._save_config()
    
    def get_rated_capacity(self, tag):
        """Get rated capacity for a tag"""
        tag_config = self.config.get('tags', {}).get(tag)
        if not tag_config:
            return None
        return tag_config.get('rated_capacity')
    
    def set_rated_capacity(self, tag, value):
        """Set rated capacity"""
        if 'tags' not in self.config:
            self.config['tags'] = {}
        if tag not in self.config['tags']:
            self.config['tags'][tag] = {}
        
        self.config['tags'][tag]['rated_capacity'] = value
        self.config['tags'][tag]['last_updated'] = datetime.now().isoformat()
        self._save_config()
    
    def get_production_tags(self):
        """Get all tags marked as production tags"""
        tags = self.config.get('tags', {})
        return [tag for tag, config in tags.items() if config.get('is_production_tag', False)]
    
    def get_tag_thresholds(self, tag):
        """Get thresholds for a specific tag"""
        tag_config = self.config.get('tags', {}).get(tag)
        if not tag_config:
            return None
        return tag_config.get('thresholds')
    
    def get_stability_thresholds(self):
        """Get stability rating thresholds"""
        return self.get_global_setting('stability_thresholds', {
            'excellent': 0.95,
            'good': 0.85,
            'fair': 0.70,
            'poor': 0.50
        })
    
    def get_recommendation_thresholds(self):
        """Get recommendation trigger thresholds"""
        return self.get_global_setting('recommendation_thresholds', {
            'stability_index_min': 0.7,
            'loss_factor_max': 0.15,
            'availability_min': 85
        })
        
        self.config[tag]['rated_capacity'] = value
        self.config[tag]['last_updated'] = datetime.now().isoformat()
        self._save_config()
    
    def get_all_tags(self):
        """Get all configured tags"""
        return list(self.config.keys())
