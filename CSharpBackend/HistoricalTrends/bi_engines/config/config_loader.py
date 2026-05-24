"""
Configuration loader for BI engines
Loads and validates YAML configuration
"""

import yaml
import os
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Loads and manages BI engine configuration"""
    
    def __init__(self, config_path: str = None):
        """
        Initialize config loader
        
        Args:
            config_path: Path to YAML config file
        """
        if config_path is None:
            # Default to bi_config.yaml in same directory
            config_path = os.path.join(
                os.path.dirname(__file__),
                'bi_config.yaml'
            )
        
        self.config_path = config_path
        self.config = self._load_config()
        
        logger.info(f"Configuration loaded from {config_path}")
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            return config
        except FileNotFoundError:
            logger.error(f"❌ Config file not found: {self.config_path}")
            return {}
        except yaml.YAMLError as e:
            logger.error(f"❌ Error parsing YAML: {e}")
            return {}
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation
        
        Args:
            key_path: Dot-separated path (e.g., 'baseline_engine.outlier_method')
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        keys = key_path.split('.')
        value = self.config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def get_engine_config(self, engine_name: str) -> Dict:
        """
        Get full configuration for a specific engine
        
        Args:
            engine_name: Name of engine (e.g., 'baseline_engine')
            
        Returns:
            Engine configuration dictionary
        """
        return self.config.get(engine_name, {})
    
    def reload(self):
        """Reload configuration from file"""
        self.config = self._load_config()
        logger.info("Configuration reloaded")


# Global config instance
_global_config = None


def get_config(config_path: str = None) -> ConfigLoader:
    """
    Get global configuration instance
    
    Args:
        config_path: Optional path to config file
        
    Returns:
        ConfigLoader instance
    """
    global _global_config
    
    if _global_config is None or config_path is not None:
        _global_config = ConfigLoader(config_path)
    
    return _global_config
