"""
Configuration Loader Module
Loads and validates service configuration from YAML file
"""

import os
import yaml
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Loads and manages service configuration"""
    
    def __init__(self, config_path: str = None):
        """
        Initialize configuration loader
        
        Args:
            config_path: Path to config file (default: config/service_config.yaml)
        """
        if config_path is None:
            # Get path relative to project root
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config" / "service_config.yaml"
        
        self.config_path = Path(config_path)
        self._config: Optional[Dict[str, Any]] = None
        
    def load(self) -> Dict[str, Any]:
        """
        Load configuration from YAML file
        
        Returns:
            Configuration dictionary
            
        Raises:
            FileNotFoundError: If config file not found
            yaml.YAMLError: If config file invalid
        """
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        try:
            with open(self.config_path, 'r') as f:
                self._config = yaml.safe_load(f)
                
            logger.info(f"Configuration loaded from {self.config_path}")
            
            # Apply environment variable overrides
            self._apply_env_overrides()
            
            # Validate configuration
            self._validate()
            
            return self._config
            
        except yaml.YAMLError as e:
            logger.error(f"Error parsing configuration file: {e}")
            raise
    
    def _apply_env_overrides(self):
        """Apply environment variable overrides to configuration"""
        # Database overrides
        if os.getenv('DB_HOST'):
            self._config['database']['host'] = os.getenv('DB_HOST')
        if os.getenv('DB_PORT'):
            self._config['database']['port'] = int(os.getenv('DB_PORT'))
        if os.getenv('DB_NAME'):
            self._config['database']['database'] = os.getenv('DB_NAME')
        if os.getenv('DB_USER'):
            self._config['database']['username'] = os.getenv('DB_USER')
        if os.getenv('DB_PASSWORD'):
            self._config['database']['password'] = os.getenv('DB_PASSWORD')
        
        # MQTT overrides
        if os.getenv('MQTT_BROKER'):
            self._config['mqtt']['broker_host'] = os.getenv('MQTT_BROKER')
        if os.getenv('MQTT_PORT'):
            self._config['mqtt']['broker_port'] = int(os.getenv('MQTT_PORT'))
        if os.getenv('MQTT_USERNAME'):
            self._config['security']['mqtt_username'] = os.getenv('MQTT_USERNAME')
        if os.getenv('MQTT_PASSWORD'):
            self._config['security']['mqtt_password'] = os.getenv('MQTT_PASSWORD')
    
    def _validate(self):
        """Validate configuration has required fields"""
        required_sections = ['service', 'mqtt', 'database', 'processing', 'logging']
        
        for section in required_sections:
            if section not in self._config:
                raise ValueError(f"Missing required configuration section: {section}")
        
        # Validate specific fields
        if self._config['service']['worker_threads'] < 1:
            raise ValueError("worker_threads must be >= 1")
        
        if self._config['mqtt']['qos'] not in [0, 1, 2]:
            raise ValueError("mqtt.qos must be 0, 1, or 2")
        
        if self._config['database']['pool_size'] < 1:
            raise ValueError("database.pool_size must be >= 1")
        
        logger.info("Configuration validation passed")
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get configuration value by dot-notation path
        
        Args:
            key_path: Dot-notation path (e.g., 'database.host')
            default: Default value if key not found
            
        Returns:
            Configuration value
            
        Example:
            >>> config.get('database.host')
            'localhost'
        """
        if self._config is None:
            self.load()
        
        keys = key_path.split('.')
        value = self._config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    @property
    def config(self) -> Dict[str, Any]:
        """Get full configuration dictionary"""
        if self._config is None:
            self.load()
        return self._config


# Singleton instance
_config_instance: Optional[ConfigLoader] = None


def get_config(config_path: str = None) -> ConfigLoader:
    """
    Get singleton configuration instance
    
    Args:
        config_path: Path to config file (only used on first call)
        
    Returns:
        ConfigLoader instance
    """
    global _config_instance
    
    if _config_instance is None:
        _config_instance = ConfigLoader(config_path)
        _config_instance.load()
    
    return _config_instance
