"""
Health Check CLI Utility
Checks service health and displays status
"""

import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.config_loader import ConfigLoader
from src.monitoring.logger import ServiceLogger
from src.database.db_connection import DatabaseConnection
from src.monitoring.logger import get_logger

ServiceLogger.initialize()
logger = get_logger(__name__)


def check_database():
    """Check database connectivity"""
    try:
        config = ConfigLoader.load('config/service_config.yaml')
        db = DatabaseConnection.get_instance()
        db.initialize(config['database'])
        
        if db.test_connection():
            print("✓ Database: HEALTHY")
            return True
        else:
            print("✗ Database: FAILED")
            return False
    except Exception as e:
        print(f"✗ Database: ERROR - {e}")
        return False


def check_config():
    """Check configuration file"""
    try:
        config = ConfigLoader.load('config/service_config.yaml')
        print("✓ Configuration: VALID")
        
        # Check required sections
        required = ['service', 'database', 'mqtt', 'processing', 'security', 'logging', 'monitoring']
        missing = [s for s in required if s not in config]
        
        if missing:
            print(f"  ⚠ Missing sections: {', '.join(missing)}")
            return False
        
        return True
    except Exception as e:
        print(f"✗ Configuration: ERROR - {e}")
        return False


def main():
    """Main health check"""
    print("=" * 60)
    print("MQTT Subscriber Service - Health Check")
    print("=" * 60)
    print()
    
    checks = {
        'Configuration': check_config(),
        'Database': check_database()
    }
    
    print()
    print("=" * 60)
    
    all_passed = all(checks.values())
    
    if all_passed:
        print("Overall Status: HEALTHY ✓")
        sys.exit(0)
    else:
        print("Overall Status: UNHEALTHY ✗")
        sys.exit(1)


if __name__ == '__main__':
    main()
