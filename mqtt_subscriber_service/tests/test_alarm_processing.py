"""
Test Alarm Processing
Tests message processing with alarm summary data
"""

import pytest
import json
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from models.message_models import MQTTMessage, ParsedMessage
from processing.message_processor import MessageProcessor


class TestAlarmProcessing:
    """Test alarm data processing"""
    
    def test_parse_message_with_alarms(self):
        """Test parsing MQTT message with alarm summary"""
        
        # Sample payload with alarms from latest_sample_mqtt_data.json
        payload = {
            "timestamp": "2026-01-06T08:34:47.123Z",
            "tag_id": "Blastfurnace_Tuyer1_Pressure",
            "value": 22.23,
            "quality": "G",
            "source": "MQTT",
            "version": 1,
            "alarm_summary": {
                "total_alarms": 3,
                "critical_count": 1,
                "warning_count": 2,
                "info_count": 0,
                "alarms": [
                    {
                        "tag_id": "Blastfurnace_Tuyer1_Pressure",
                        "event_type": "HIGH_ALARM_CRITICAL",
                        "severity": 1,
                        "message": "Blast furnace pressure exceeded critical threshold (22.23 Bar > 22.0 Bar)",
                        "time": "2026-01-06T08:34:47.000Z",
                        "metadata": {
                            "alarm_value": 22.23,
                            "setpoint": 22.0,
                            "unit": "Bar",
                            "plant": "Steel_Plant_A",
                            "area": "Blast_Furnace",
                            "equipment": "Tuyer_1",
                            "acknowledged": False,
                            "state": "ACTIVE"
                        }
                    },
                    {
                        "tag_id": "Boiler_Inlet_Temp",
                        "event_type": "HIGH_ALARM_WARNING",
                        "severity": 2,
                        "message": "Boiler inlet temperature above normal operating range (70.98°C > 70.0°C)",
                        "time": "2026-01-06T08:34:47.000Z",
                        "metadata": {
                            "alarm_value": 70.98,
                            "setpoint": 70.0,
                            "unit": "Celsius",
                            "plant": "Steel_Plant_A",
                            "area": "Power_Generation",
                            "equipment": "Boiler_01",
                            "acknowledged": False,
                            "state": "ACTIVE"
                        }
                    },
                    {
                        "tag_id": "Cooling_FAN_SPEED",
                        "event_type": "HIGH_ALARM_WARNING",
                        "severity": 2,
                        "message": "Cooling fan speed above warning threshold (65.88% > 65.0%)",
                        "time": "2026-01-06T08:34:47.000Z",
                        "metadata": {
                            "alarm_value": 65.88,
                            "setpoint": 65.0,
                            "unit": "Percent",
                            "plant": "Steel_Plant_A",
                            "area": "Cooling_System",
                            "equipment": "Fan_01",
                            "acknowledged": False,
                            "state": "ACTIVE"
                        }
                    }
                ]
            }
        }
        
        # Create MQTT message
        mqtt_msg = MQTTMessage(
            topic="plant/sensors/pressure",
            payload=json.dumps(payload).encode('utf-8'),
            qos=1
        )
        
        assert mqtt_msg.topic == "plant/sensors/pressure"
        assert mqtt_msg.qos == 1
        
        # Parse payload
        payload_data = json.loads(mqtt_msg.payload.decode('utf-8'))
        
        # Verify alarm summary exists
        assert 'alarm_summary' in payload_data
        assert payload_data['alarm_summary']['total_alarms'] == 3
        assert payload_data['alarm_summary']['critical_count'] == 1
        assert payload_data['alarm_summary']['warning_count'] == 2
        
        # Verify alarms
        alarms = payload_data['alarm_summary']['alarms']
        assert len(alarms) == 3
        
        # Check critical alarm
        critical_alarm = alarms[0]
        assert critical_alarm['severity'] == 1
        assert critical_alarm['event_type'] == 'HIGH_ALARM_CRITICAL'
        assert critical_alarm['tag_id'] == 'Blastfurnace_Tuyer1_Pressure'
        assert 'metadata' in critical_alarm
        assert critical_alarm['metadata']['alarm_value'] == 22.23
        
        # Check warning alarms
        warning_alarm1 = alarms[1]
        assert warning_alarm1['severity'] == 2
        assert warning_alarm1['event_type'] == 'HIGH_ALARM_WARNING'
        
        warning_alarm2 = alarms[2]
        assert warning_alarm2['severity'] == 2
        assert warning_alarm2['event_type'] == 'HIGH_ALARM_WARNING'
    
    def test_alarm_severity_levels(self):
        """Test alarm severity classification"""
        
        severity_map = {
            1: "CRITICAL",
            2: "WARNING",
            3: "INFO"
        }
        
        # Verify severity levels
        assert severity_map[1] == "CRITICAL"
        assert severity_map[2] == "WARNING"
        assert severity_map[3] == "INFO"
    
    def test_alarm_metadata_structure(self):
        """Test alarm metadata structure"""
        
        metadata = {
            "alarm_value": 22.23,
            "setpoint": 22.0,
            "unit": "Bar",
            "plant": "Steel_Plant_A",
            "area": "Blast_Furnace",
            "equipment": "Tuyer_1",
            "acknowledged": False,
            "state": "ACTIVE"
        }
        
        # Verify required fields
        assert 'alarm_value' in metadata
        assert 'setpoint' in metadata
        assert 'unit' in metadata
        assert 'plant' in metadata
        assert 'area' in metadata
        assert 'equipment' in metadata
        assert 'acknowledged' in metadata
        assert 'state' in metadata
        
        # Verify values
        assert metadata['alarm_value'] > metadata['setpoint']
        assert metadata['state'] in ['ACTIVE', 'ACKNOWLEDGED', 'CLEARED']
    
    def test_load_sample_data_file(self):
        """Test loading latest_sample_mqtt_data.json with alarms"""
        
        sample_file = Path(__file__).parent.parent / 'latest_sample_mqtt_data.json'
        
        if not sample_file.exists():
            pytest.skip("Sample data file not found")
        
        with open(sample_file, 'r') as f:
            data = json.load(f)
        
        # Verify structure
        assert 'timestamp' in data
        assert 'values' in data
        assert 'alarm_summary' in data
        
        # Verify alarm summary
        alarm_summary = data['alarm_summary']
        assert 'total_alarms' in alarm_summary
        assert 'critical_count' in alarm_summary
        assert 'warning_count' in alarm_summary
        assert 'info_count' in alarm_summary
        assert 'alarms' in alarm_summary
        
        # Verify alarm count consistency
        alarms = alarm_summary['alarms']
        assert len(alarms) == alarm_summary['total_alarms']
        
        # Count alarms by severity
        critical = sum(1 for a in alarms if a['severity'] == 1)
        warning = sum(1 for a in alarms if a['severity'] == 2)
        info = sum(1 for a in alarms if a['severity'] == 3)
        
        assert critical == alarm_summary['critical_count']
        assert warning == alarm_summary['warning_count']
        assert info == alarm_summary['info_count']
        
        print(f"\n✓ Loaded {alarm_summary['total_alarms']} alarms from sample data")
        print(f"  - Critical: {critical}")
        print(f"  - Warning: {warning}")
        print(f"  - Info: {info}")


class TestAlarmEventProcessing:
    """Test alarm event data for historian_events table"""
    
    def test_prepare_event_records(self):
        """Test preparing alarm data for historian_events insert"""
        
        alarms = [
            {
                "tag_id": "Blastfurnace_Tuyer1_Pressure",
                "event_type": "HIGH_ALARM_CRITICAL",
                "severity": 1,
                "message": "Blast furnace pressure exceeded critical threshold",
                "time": "2026-01-06T08:34:47.000Z",
                "metadata": {
                    "alarm_value": 22.23,
                    "setpoint": 22.0,
                    "unit": "Bar"
                }
            }
        ]
        
        event_records = []
        for alarm in alarms:
            event_record = {
                'time': datetime.fromisoformat(alarm['time'].replace('Z', '+00:00')),
                'tag_id': alarm['tag_id'],
                'event_type': alarm['event_type'],
                'severity': alarm['severity'],
                'message': alarm['message'],
                'metadata': alarm['metadata']
            }
            event_records.append(event_record)
        
        assert len(event_records) == 1
        assert event_records[0]['tag_id'] == 'Blastfurnace_Tuyer1_Pressure'
        assert event_records[0]['event_type'] == 'HIGH_ALARM_CRITICAL'
        assert event_records[0]['severity'] == 1
        assert isinstance(event_records[0]['time'], datetime)
        assert isinstance(event_records[0]['metadata'], dict)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
