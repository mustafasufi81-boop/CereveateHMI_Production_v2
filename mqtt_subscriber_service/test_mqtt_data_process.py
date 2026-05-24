"""
MQTT Data Process Test Suite
Tests the complete message processing pipeline end-to-end

This script tests:
1. Message parsing
2. Validation
3. Audit record creation
4. Timeseries insertion
5. Alarm/Event processing
6. Batch message processing
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime
from colorama import init, Fore, Style

# Initialize colorama for colored output
init(autoreset=True)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.utils.config_loader import ConfigLoader
from src.database.db_connection import DatabaseConnection
from src.database.audit_dao import AuditDAO
from src.database.historian_dao import HistorianDAO
from src.cache.topic_cache import TopicCache
from src.cache.tag_master_cache import TagMasterCache
from src.validation.validator import MessageValidator
from src.processing.message_processor import MessageProcessor
from src.models.message_models import MQTTMessage
from src.monitoring.logger import ServiceLogger, get_logger

logger = get_logger(__name__)


class TestResults:
    """Track test results"""
    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def add_pass(self, test_name):
        self.total += 1
        self.passed += 1
        print(f"{Fore.GREEN}✓ PASS:{Style.RESET_ALL} {test_name}")
    
    def add_fail(self, test_name, error):
        self.total += 1
        self.failed += 1
        self.errors.append((test_name, error))
        print(f"{Fore.RED}✗ FAIL:{Style.RESET_ALL} {test_name}")
        print(f"  {Fore.YELLOW}Error:{Style.RESET_ALL} {error}")
    
    def print_summary(self):
        print("\n" + "="*70)
        print(f"{Fore.CYAN}TEST SUMMARY{Style.RESET_ALL}")
        print("="*70)
        print(f"Total Tests:  {self.total}")
        print(f"{Fore.GREEN}Passed:       {self.passed}{Style.RESET_ALL}")
        print(f"{Fore.RED}Failed:       {self.failed}{Style.RESET_ALL}")
        print(f"Success Rate: {(self.passed/self.total*100):.1f}%")
        
        if self.errors:
            print(f"\n{Fore.RED}Failed Tests:{Style.RESET_ALL}")
            for test_name, error in self.errors:
                print(f"  - {test_name}: {error}")


class MQTTDataProcessTest:
    """MQTT Data Process Test Suite"""
    
    def __init__(self):
        self.results = TestResults()
        self.config = None
        self.db = None
        self.processor = None
        
    def setup(self):
        """Initialize test environment"""
        print(f"\n{Fore.CYAN}{'='*70}")
        print(f"MQTT DATA PROCESS TEST SUITE")
        print(f"{'='*70}{Style.RESET_ALL}\n")
        
        try:
            # Setup logging
            ServiceLogger.initialize()
            
            # Load configuration
            print("Loading configuration...")
            config_loader = ConfigLoader('config/service_config.yaml')
            self.config = config_loader.load()
            
            # Initialize database
            print("Connecting to database...")
            self.db = DatabaseConnection.get_instance()
            self.db.initialize(self.config['database'])
            
            if not self.db.test_connection():
                raise Exception("Database connection test failed")
            
            print(f"{Fore.GREEN}✓ Database connected successfully{Style.RESET_ALL}")
            
            # Initialize caches
            print("Loading caches...")
            topic_cache = TopicCache(self.db, self.config)
            tag_master_cache = TagMasterCache(self.db, self.config)
            
            topic_cache.load_all()
            tag_master_cache.load_all()
            
            print(f"{Fore.GREEN}✓ Caches loaded successfully{Style.RESET_ALL}")
            
            # Initialize DAOs
            audit_dao = AuditDAO(self.db)
            historian_dao = HistorianDAO(self.db)
            
            # Initialize validator
            validator = MessageValidator(self.config)
            
            # Initialize message processor
            self.processor = MessageProcessor(
                config=self.config,
                topic_cache=topic_cache,
                tag_master_cache=tag_master_cache,
                audit_dao=audit_dao,
                historian_dao=historian_dao,
                validator=validator
            )
            
            print(f"{Fore.GREEN}✓ Message processor initialized{Style.RESET_ALL}\n")
            
        except Exception as e:
            print(f"{Fore.RED}✗ Setup failed: {e}{Style.RESET_ALL}")
            raise
    
    def test_single_tag_message(self):
        """Test 1: Process single-tag message"""
        test_name = "Single Tag Message Processing"
        print(f"\n{Fore.YELLOW}Running:{Style.RESET_ALL} {test_name}")
        
        try:
            payload = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "tag_id": "TEST.Temperature.Sensor1",
                "value": 85.5,
                "quality": "Good",
                "source": "MQTT",
                "version": 1
            }
            
            mqtt_msg = MQTTMessage(
                topic="test/gateway/data",
                payload=json.dumps(payload).encode('utf-8'),
                qos=1
            )
            
            result = self.processor.process_message(mqtt_msg)
            
            if result.success and result.records_inserted > 0:
                self.results.add_pass(test_name)
                print(f"  Records inserted: {result.records_inserted}")
                print(f"  Processing time: {result.processing_time_ms:.2f}ms")
            else:
                self.results.add_fail(test_name, result.error_message or "No records inserted")
                
        except Exception as e:
            self.results.add_fail(test_name, str(e))
    
    def test_batch_message(self):
        """Test 2: Process batch message with multiple tags"""
        test_name = "Batch Message Processing"
        print(f"\n{Fore.YELLOW}Running:{Style.RESET_ALL} {test_name}")
        
        try:
            timestamp = datetime.utcnow().isoformat() + "Z"
            
            payload = {
                "timestamp": timestamp,
                "publishIntervalMs": 1000,
                "tagCount": 5,
                "totalSamples": 25,
                "values": [
                    {
                        "plcId": "TEST_PLC_001",
                        "tag": "TEST.Pressure.Tank1",
                        "dataType": "float",
                        "scanRateMs": 200,
                        "sampleCount": 5,
                        "samples": [
                            {"value": 22.1, "quality": "Good", "timestamp": timestamp},
                            {"value": 22.2, "quality": "Good", "timestamp": timestamp},
                            {"value": 22.3, "quality": "Good", "timestamp": timestamp},
                            {"value": 22.2, "quality": "Good", "timestamp": timestamp},
                            {"value": 22.3, "quality": "Good", "timestamp": timestamp}
                        ],
                        "value": 22.3,
                        "quality": "Good",
                        "timestamp": timestamp
                    },
                    {
                        "plcId": "TEST_PLC_001",
                        "tag": "TEST.Temperature.Boiler",
                        "dataType": "float",
                        "value": 70.5,
                        "quality": "Good",
                        "timestamp": timestamp
                    },
                    {
                        "plcId": "TEST_PLC_001",
                        "tag": "TEST.Motor.Status",
                        "dataType": "bool",
                        "value": True,
                        "quality": "Good",
                        "timestamp": timestamp
                    }
                ]
            }
            
            mqtt_msg = MQTTMessage(
                topic="test/gateway/data",
                payload=json.dumps(payload).encode('utf-8'),
                qos=1
            )
            
            result = self.processor.process_message(mqtt_msg)
            
            if result.success and result.records_inserted >= 7:  # 5 samples + 2 single values
                self.results.add_pass(test_name)
                print(f"  Records inserted: {result.records_inserted}")
                print(f"  Processing time: {result.processing_time_ms:.2f}ms")
            else:
                self.results.add_fail(test_name, 
                    result.error_message or f"Expected >=7 records, got {result.records_inserted}")
                
        except Exception as e:
            self.results.add_fail(test_name, str(e))
    
    def test_message_with_alarms(self):
        """Test 3: Process message with alarm summary"""
        test_name = "Message with Alarms Processing"
        print(f"\n{Fore.YELLOW}Running:{Style.RESET_ALL} {test_name}")
        
        try:
            timestamp = datetime.utcnow().isoformat() + "Z"
            
            payload = {
                "timestamp": timestamp,
                "tag_id": "TEST.Pressure.Critical",
                "value": 95.5,
                "quality": "Good",
                "source": "MQTT",
                "version": 1,
                "alarm_summary": {
                    "total_alarms": 2,
                    "critical_count": 1,
                    "warning_count": 1,
                    "alarms": [
                        {
                            "tag_id": "TEST.Pressure.Critical",
                            "event_type": "ALARM_HIGH_CRITICAL",
                            "severity": 1,
                            "message": "Pressure exceeded critical threshold (95.5 > 90.0)",
                            "time": timestamp,
                            "metadata": {
                                "alarm_value": 95.5,
                                "setpoint": 90.0,
                                "unit": "Bar",
                                "acknowledged": False,
                                "state": "ACTIVE"
                            }
                        },
                        {
                            "tag_id": "TEST.Temperature.Warning",
                            "event_type": "ALARM_HIGH_WARNING",
                            "severity": 2,
                            "message": "Temperature above warning threshold (75.5 > 70.0)",
                            "time": timestamp,
                            "metadata": {
                                "alarm_value": 75.5,
                                "setpoint": 70.0,
                                "unit": "Celsius",
                                "acknowledged": False,
                                "state": "ACTIVE"
                            }
                        }
                    ]
                }
            }
            
            mqtt_msg = MQTTMessage(
                topic="test/gateway/data",
                payload=json.dumps(payload).encode('utf-8'),
                qos=1
            )
            
            result = self.processor.process_message(mqtt_msg)
            
            # Should insert 1 timeseries + 2 alarm events = 3 records
            if result.success and result.records_inserted >= 3:
                self.results.add_pass(test_name)
                print(f"  Records inserted: {result.records_inserted} (1 timeseries + 2 alarms)")
                print(f"  Processing time: {result.processing_time_ms:.2f}ms")
            else:
                self.results.add_fail(test_name, 
                    result.error_message or f"Expected >=3 records, got {result.records_inserted}")
                
        except Exception as e:
            self.results.add_fail(test_name, str(e))
    
    def test_invalid_message(self):
        """Test 4: Handle invalid message gracefully"""
        test_name = "Invalid Message Handling"
        print(f"\n{Fore.YELLOW}Running:{Style.RESET_ALL} {test_name}")
        
        try:
            # Invalid JSON
            mqtt_msg = MQTTMessage(
                topic="test/gateway/data",
                payload=b"Invalid JSON {{{",
                qos=1
            )
            
            result = self.processor.process_message(mqtt_msg)
            
            # Should fail gracefully without crashing
            if not result.success and result.error_message:
                self.results.add_pass(test_name)
                print(f"  Handled gracefully: {result.error_message}")
            else:
                self.results.add_fail(test_name, "Should have failed validation")
                
        except Exception as e:
            self.results.add_fail(test_name, f"Should not raise exception: {e}")
    
    def test_audit_trail(self):
        """Test 5: Verify audit trail creation"""
        test_name = "Audit Trail Creation"
        print(f"\n{Fore.YELLOW}Running:{Style.RESET_ALL} {test_name}")
        
        try:
            timestamp = datetime.utcnow().isoformat() + "Z"
            
            payload = {
                "timestamp": timestamp,
                "tag_id": "TEST.Audit.Check",
                "value": 42.0,
                "quality": "Good",
                "source": "MQTT",
                "version": 1
            }
            
            mqtt_msg = MQTTMessage(
                topic="test/gateway/data",
                payload=json.dumps(payload).encode('utf-8'),
                qos=1
            )
            
            result = self.processor.process_message(mqtt_msg)
            
            # Check if audit_id was created
            if result.success and result.audit_id:
                self.results.add_pass(test_name)
                print(f"  Audit ID created: {result.audit_id}")
                print(f"  Message ID: {result.message_id}")
            else:
                self.results.add_fail(test_name, "No audit_id created")
                
        except Exception as e:
            self.results.add_fail(test_name, str(e))
    
    def test_performance(self):
        """Test 6: Process multiple messages and check performance"""
        test_name = "Performance Test (10 messages)"
        print(f"\n{Fore.YELLOW}Running:{Style.RESET_ALL} {test_name}")
        
        try:
            start_time = time.time()
            message_count = 10
            successful = 0
            
            for i in range(message_count):
                timestamp = datetime.utcnow().isoformat() + "Z"
                
                payload = {
                    "timestamp": timestamp,
                    "tag_id": f"TEST.Performance.Tag{i:03d}",
                    "value": 10.0 + i,
                    "quality": "Good",
                    "source": "MQTT",
                    "version": 1
                }
                
                mqtt_msg = MQTTMessage(
                    topic="test/gateway/data",
                    payload=json.dumps(payload).encode('utf-8'),
                    qos=1
                )
                
                result = self.processor.process_message(mqtt_msg)
                if result.success:
                    successful += 1
            
            elapsed_time = time.time() - start_time
            avg_time = (elapsed_time / message_count) * 1000  # ms
            
            if successful == message_count:
                self.results.add_pass(test_name)
                print(f"  Messages processed: {successful}/{message_count}")
                print(f"  Total time: {elapsed_time:.2f}s")
                print(f"  Average time per message: {avg_time:.2f}ms")
                print(f"  Throughput: {message_count/elapsed_time:.1f} msg/s")
            else:
                self.results.add_fail(test_name, f"Only {successful}/{message_count} succeeded")
                
        except Exception as e:
            self.results.add_fail(test_name, str(e))
    
    def run_all_tests(self):
        """Run all tests"""
        try:
            self.setup()
            
            print(f"\n{Fore.CYAN}{'='*70}")
            print(f"RUNNING TESTS")
            print(f"{'='*70}{Style.RESET_ALL}")
            
            # Run tests
            self.test_single_tag_message()
            self.test_batch_message()
            self.test_message_with_alarms()
            self.test_invalid_message()
            self.test_audit_trail()
            self.test_performance()
            
            # Print results
            self.results.print_summary()
            
            # Cleanup
            if self.db:
                self.db.cleanup()
            
            return self.results.failed == 0
            
        except Exception as e:
            print(f"\n{Fore.RED}Test suite failed: {e}{Style.RESET_ALL}")
            return False


def main():
    """Main entry point"""
    try:
        test_suite = MQTTDataProcessTest()
        success = test_suite.run_all_tests()
        
        if success:
            print(f"\n{Fore.GREEN}✓ All tests passed!{Style.RESET_ALL}\n")
            sys.exit(0)
        else:
            print(f"\n{Fore.RED}✗ Some tests failed{Style.RESET_ALL}\n")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n{Fore.RED}Fatal error: {e}{Style.RESET_ALL}\n")
        sys.exit(1)


if __name__ == '__main__':
    main()
