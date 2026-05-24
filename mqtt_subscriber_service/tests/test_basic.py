"""
Basic validation tests for MQTT Subscriber Service
Run with: pytest tests/test_basic.py -v
"""

import pytest
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from models.message_models import MQTTMessage, ParsedMessage, ValidationResult
from datetime import datetime


class TestModels:
    """Test data models"""
    
    def test_mqtt_message_creation(self):
        """Test MQTTMessage creation"""
        msg = MQTTMessage(
            topic="test/topic",
            payload=b'{"tag_id":"TAG001","value":123.45}',
            qos=1
        )
        
        assert msg.topic == "test/topic"
        assert msg.qos == 1
        assert len(msg.payload) > 0
        assert isinstance(msg.received_at, datetime)
    
    def test_parsed_message_creation(self):
        """Test ParsedMessage creation"""
        msg = ParsedMessage(
            message_id="test-123",
            topic="test/topic",
            received_at=datetime.utcnow(),
            payload_data={"tag_id": "TAG001", "value": 123.45},
            tag_id="TAG001",
            value_num=123.45
        )
        
        assert msg.message_id == "test-123"
        assert msg.tag_id == "TAG001"
        assert msg.value_num == 123.45
    
    def test_validation_result(self):
        """Test ValidationResult"""
        result = ValidationResult(is_valid=True)
        
        assert result.is_valid
        assert not result.has_errors()
        
        result.add_error("Test error")
        
        assert not result.is_valid
        assert result.has_errors()
        assert len(result.errors) == 1
    
    def test_validation_warnings(self):
        """Test validation warnings"""
        result = ValidationResult(is_valid=True)
        
        result.add_warning("Test warning")
        
        assert result.is_valid  # Warnings don't invalidate
        assert result.has_warnings()
        assert len(result.warnings) == 1


class TestConfigLoader:
    """Test configuration loader"""
    
    def test_config_file_exists(self):
        """Test config file exists"""
        config_path = Path(__file__).parent.parent / 'config' / 'service_config.yaml'
        assert config_path.exists(), "service_config.yaml not found"
    
    def test_logging_config_exists(self):
        """Test logging config exists"""
        config_path = Path(__file__).parent.parent / 'config' / 'logging_config.json'
        assert config_path.exists(), "logging_config.json not found"


class TestSQLSchema:
    """Test SQL schema file"""
    
    def test_schema_file_exists(self):
        """Test schema SQL file exists"""
        schema_path = Path(__file__).parent.parent / 'sql' / 'create_subscriber_tables.sql'
        assert schema_path.exists(), "create_subscriber_tables.sql not found"
    
    def test_schema_contains_tables(self):
        """Test schema contains required tables"""
        schema_path = Path(__file__).parent.parent / 'sql' / 'create_subscriber_tables.sql'
        content = schema_path.read_text()
        
        assert 'mqtt_topic_config' in content
        assert 'mqtt_audit_main' in content
        assert 'mqtt_audit_history' in content


class TestRequirements:
    """Test requirements file"""
    
    def test_requirements_file_exists(self):
        """Test requirements.txt exists"""
        req_path = Path(__file__).parent.parent / 'requirements.txt'
        assert req_path.exists(), "requirements.txt not found"
    
    def test_requirements_has_dependencies(self):
        """Test requirements has all needed dependencies"""
        req_path = Path(__file__).parent.parent / 'requirements.txt'
        content = req_path.read_text()
        
        required_packages = [
            'paho-mqtt',
            'psycopg2-binary',
            'PyYAML',
            'python-json-logger',
            'cryptography',
            'pytest'
        ]
        
        for package in required_packages:
            assert package in content, f"Missing package: {package}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
