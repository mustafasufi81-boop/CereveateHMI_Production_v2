"""
Environment-based Configuration Manager for HMI Flask Application
Loads settings from .env file or environment variables
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if exists
BASE_DIR = Path(__file__).resolve().parent
env_file = BASE_DIR / '.env'
if env_file.exists():
    load_dotenv(env_file)
    print(f"✅ Loaded environment from {env_file}")
else:
    print(f"⚠️  No .env file found at {env_file}, using environment variables")


class Config:
    """Base configuration"""
    
    # Environment
    ENV = os.getenv('HMI_ENV', 'development')
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Server
    HMI_HOST = os.getenv('HMI_HOST', '0.0.0.0')
    HMI_PORT = int(os.getenv('HMI_PORT', '6001'))
    
    # Database
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = int(os.getenv('DB_PORT', '5432'))
    DB_NAME = os.getenv('DB_NAME', 'Cereveate')
    DB_USER = os.getenv('DB_USER', 'postgres')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'cereveate@222')
    DB_POOL_MIN = int(os.getenv('DB_POOL_MIN', '2'))
    DB_POOL_MAX = int(os.getenv('DB_POOL_MAX', '10'))
    
    # C# Backend / SignalR
    CSHARP_HOST = os.getenv('CSHARP_HOST', '127.0.0.1')
    CSHARP_PORT = int(os.getenv('CSHARP_PORT', '5001'))
    SIGNALR_HUB = os.getenv('SIGNALR_HUB', '/opcHub')
    
    # MQTT
    MQTT_BROKER_HOST = os.getenv('MQTT_BROKER_HOST', '127.0.0.1')
    MQTT_BROKER_PORT = int(os.getenv('MQTT_BROKER_PORT', '1883'))
    MQTT_USERNAME = os.getenv('MQTT_USERNAME', None)
    MQTT_PASSWORD = os.getenv('MQTT_PASSWORD', None)
    MQTT_CLIENT_ID = os.getenv('MQTT_CLIENT_ID', 'hmi_backend')
    MQTT_KEEPALIVE = int(os.getenv('MQTT_KEEPALIVE', '60'))
    
    # CORS
    CORS_ORIGINS = os.getenv('CORS_ORIGINS', '*')
    
    # Security
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES', '3600'))
    JWT_REFRESH_TOKEN_EXPIRES = int(os.getenv('JWT_REFRESH_TOKEN_EXPIRES', '604800'))
    SESSION_TIMEOUT = int(os.getenv('SESSION_TIMEOUT', '1800'))
    MAX_LOGIN_ATTEMPTS = int(os.getenv('MAX_LOGIN_ATTEMPTS', '5'))
    ACCOUNT_LOCKOUT_DURATION = int(os.getenv('ACCOUNT_LOCKOUT_DURATION', '900'))
    
    # Performance
    MAX_POINTS_LIVE = int(os.getenv('MAX_POINTS_LIVE', '1000'))
    MAX_POINTS_HISTORICAL = int(os.getenv('MAX_POINTS_HISTORICAL', '10000'))
    UPDATE_INTERVAL_MS = int(os.getenv('UPDATE_INTERVAL_MS', '1000'))
    WEBSOCKET_BUFFER = int(os.getenv('WEBSOCKET_BUFFER', '50'))
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_MAX_BYTES = int(os.getenv('LOG_MAX_BYTES', '5242880'))
    LOG_BACKUP_COUNT = int(os.getenv('LOG_BACKUP_COUNT', '10'))
    LOG_RETENTION_DAYS = int(os.getenv('LOG_RETENTION_DAYS', '30'))
    
    # Monitoring
    SENTRY_DSN = os.getenv('SENTRY_DSN', '')
    ENABLE_METRICS = os.getenv('ENABLE_METRICS', 'False').lower() == 'true'
    METRICS_PORT = int(os.getenv('METRICS_PORT', '9090'))
    
    # Reverse Proxy
    PROXY_FIX_ENABLED = os.getenv('PROXY_FIX_ENABLED', 'True').lower() == 'true'
    PROXY_FIX_X_FOR = int(os.getenv('PROXY_FIX_X_FOR', '1'))
    PROXY_FIX_X_PROTO = int(os.getenv('PROXY_FIX_X_PROTO', '1'))
    PROXY_FIX_X_HOST = int(os.getenv('PROXY_FIX_X_HOST', '1'))
    
    # WSGI Server (Gunicorn)
    GUNICORN_WORKERS = int(os.getenv('GUNICORN_WORKERS', '4'))
    GUNICORN_WORKER_CLASS = os.getenv('GUNICORN_WORKER_CLASS', 'eventlet')
    GUNICORN_BIND = os.getenv('GUNICORN_BIND', '0.0.0.0:6001')
    GUNICORN_TIMEOUT = int(os.getenv('GUNICORN_TIMEOUT', '120'))
    GUNICORN_KEEPALIVE = int(os.getenv('GUNICORN_KEEPALIVE', '5'))
    
    # WSGI Server (Waitress)
    WAITRESS_THREADS = int(os.getenv('WAITRESS_THREADS', '6'))
    WAITRESS_CHANNEL_TIMEOUT = int(os.getenv('WAITRESS_CHANNEL_TIMEOUT', '120'))
    WAITRESS_CONNECTION_LIMIT = int(os.getenv('WAITRESS_CONNECTION_LIMIT', '1000'))
    
    # SSL/TLS
    SSL_ENABLED = os.getenv('SSL_ENABLED', 'False').lower() == 'true'
    SSL_CERT_PATH = os.getenv('SSL_CERT_PATH', '')
    SSL_KEY_PATH = os.getenv('SSL_KEY_PATH', '')
    
    # Feature Flags
    ENABLE_SIGNALR = os.getenv('ENABLE_SIGNALR', 'True').lower() == 'true'
    ENABLE_MQTT = os.getenv('ENABLE_MQTT', 'True').lower() == 'true'
    ENABLE_AUDIT_LOGGING = os.getenv('ENABLE_AUDIT_LOGGING', 'True').lower() == 'true'
    ENABLE_ALARM_NOTIFICATIONS = os.getenv('ENABLE_ALARM_NOTIFICATIONS', 'True').lower() == 'true'
    ENABLE_RBAC = os.getenv('ENABLE_RBAC', 'True').lower() == 'true'
    
    @classmethod
    def to_dict(cls):
        """Convert config to dictionary (excluding sensitive data)"""
        return {
            key: value for key, value in cls.__dict__.items()
            if not key.startswith('_') 
            and key.isupper()
            and 'PASSWORD' not in key
            and 'SECRET' not in key
            and 'KEY' not in key
        }
    
    @classmethod
    def validate(cls):
        """Validate critical configuration"""
        errors = []
        
        if cls.ENV == 'production':
            if cls.SECRET_KEY == 'dev-secret-key-change-in-production':
                errors.append("❌ SECRET_KEY must be changed in production!")
            
            if cls.DEBUG:
                errors.append("❌ DEBUG must be False in production!")
            
            if cls.DB_PASSWORD == 'cereveate@222':
                errors.append("⚠️  Consider using a stronger database password!")
        
        if errors:
            print("\n".join(errors))
            if cls.ENV == 'production':
                raise ValueError("Configuration validation failed. Fix errors before deploying to production.")
        
        return True


class ProductionConfig(Config):
    """Production-specific configuration"""
    ENV = 'production'
    DEBUG = False


class StagingConfig(Config):
    """Staging-specific configuration"""
    ENV = 'staging'
    DEBUG = False


class DevelopmentConfig(Config):
    """Development-specific configuration"""
    ENV = 'development'
    DEBUG = True
    LOG_LEVEL = 'DEBUG'


# Configuration dictionary
config_by_name = {
    'production': ProductionConfig,
    'staging': StagingConfig,
    'development': DevelopmentConfig,
    'default': DevelopmentConfig
}


def get_config(env=None):
    """
    Get configuration object based on environment
    
    Args:
        env: Environment name (production/staging/development)
    
    Returns:
        Configuration class
    """
    if env is None:
        env = os.getenv('HMI_ENV', 'development')
    
    config_class = config_by_name.get(env, DevelopmentConfig)
    config_class.validate()
    
    return config_class


if __name__ == "__main__":
    """Test configuration loading"""
    print("=" * 80)
    print("HMI Configuration Test")
    print("=" * 80)
    
    config = get_config()
    print(f"\n📋 Environment: {config.ENV}")
    print(f"🔍 Debug Mode: {config.DEBUG}")
    print(f"🌐 Server: {config.HMI_HOST}:{config.HMI_PORT}")
    print(f"🗄️  Database: {config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}")
    print(f"📡 MQTT: {config.MQTT_BROKER_HOST}:{config.MQTT_BROKER_PORT}")
    print(f"🔒 CORS Origins: {config.CORS_ORIGINS}")
    
    print("\n✅ Configuration loaded successfully!")
    print("=" * 80)
