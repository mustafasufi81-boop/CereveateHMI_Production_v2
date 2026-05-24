"""
Centralized Logging Module
Configures structured logging for the service
"""

import logging
import logging.config
import json
import os
from pathlib import Path
from typing import Optional
from datetime import datetime


class ServiceLogger:
    """Centralized logging configuration"""
    
    _initialized = False
    
    @classmethod
    def initialize(cls, config: dict = None, log_dir: str = "./logs"):
        """
        Initialize logging configuration
        
        Args:
            config: Logging configuration dictionary
            log_dir: Directory for log files
        """
        if cls._initialized:
            return
        
        # Create log directory
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        
        if config is None:
            # Load default logging config
            config_path = Path(__file__).parent.parent.parent / "config" / "logging_config.json"
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
            else:
                config = cls._get_default_config(log_dir)
        
        # Update log file paths with actual log_dir
        if 'handlers' in config:
            for handler in config['handlers'].values():
                if 'filename' in handler:
                    # Replace logs/ with actual log_dir
                    filename = handler['filename'].replace('logs/', f'{log_dir}/')
                    handler['filename'] = filename
        
        # Apply configuration
        logging.config.dictConfig(config)
        
        cls._initialized = True
        
        logger = logging.getLogger('mqtt_subscriber')
        logger.info("Logging initialized", extra={
            'log_dir': log_dir,
            'timestamp': datetime.utcnow().isoformat()
        })
    
    @staticmethod
    def _get_default_config(log_dir: str) -> dict:
        """Get default logging configuration"""
        return {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "simple": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": "INFO",
                    "formatter": "simple",
                    "stream": "ext://sys.stdout"
                },
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": "INFO",
                    "formatter": "simple",
                    "filename": f"{log_dir}/mqtt_subscriber.log",
                    "maxBytes": 104857600,
                    "backupCount": 10
                }
            },
            "root": {
                "level": "INFO",
                "handlers": ["console", "file"]
            }
        }
    
    @staticmethod
    def get_logger(name: str) -> logging.Logger:
        """
        Get logger instance
        
        Args:
            name: Logger name
            
        Returns:
            Logger instance
        """
        return logging.getLogger(name)


def get_logger(name: str) -> logging.Logger:
    """
    Convenience function to get logger
    
    Args:
        name: Logger name
        
    Returns:
        Logger instance
    """
    return ServiceLogger.get_logger(name)
