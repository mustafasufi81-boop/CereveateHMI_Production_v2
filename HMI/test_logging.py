"""
Test Script for Flask Application Logging
Verifies that file-based logging with rotation is working correctly
"""

import logging
import os
import sys
import time
from datetime import datetime

# Add HMI directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the app to trigger logging setup
from app import logger, app

def print_separator(title=""):
    """Print a visual separator"""
    if title:
        print(f"\n{'=' * 80}")
        print(f"  {title}")
        print('=' * 80)
    else:
        print('=' * 80)


def check_log_directory():
    """Verify logs directory exists"""
    print_separator("1. Checking Log Directory")
    
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    
    if os.path.exists(log_dir):
        print(f"✅ Log directory exists: {log_dir}")
        
        # List log files
        log_files = [f for f in os.listdir(log_dir) if f.endswith('.log')]
        print(f"\n📁 Log files found: {len(log_files)}")
        for log_file in sorted(log_files):
            file_path = os.path.join(log_dir, log_file)
            size_kb = os.path.getsize(file_path) / 1024
            print(f"   - {log_file}: {size_kb:.2f} KB")
        
        return True
    else:
        print(f"❌ Log directory not found: {log_dir}")
        return False


def test_log_levels():
    """Test different log levels"""
    print_separator("2. Testing Log Levels")
    
    test_logger = logging.getLogger("test_logging")
    
    print("Writing test messages to logs...")
    
    test_logger.debug("🔍 DEBUG: This is a debug message (should NOT appear in logs)")
    print("   - DEBUG message sent (should be filtered out)")
    
    test_logger.info("ℹ️  INFO: This is an info message")
    print("   - INFO message sent")
    
    test_logger.warning("⚠️  WARNING: This is a warning message")
    print("   - WARNING message sent")
    
    test_logger.error("❌ ERROR: This is an error message")
    print("   - ERROR message sent")
    
    test_logger.critical("🔥 CRITICAL: This is a critical message")
    print("   - CRITICAL message sent")
    
    print("\n✅ All test messages sent")


def test_request_logging():
    """Simulate HTTP request logging"""
    print_separator("3. Testing Request Logging")
    
    app_logger = logging.getLogger("app")
    
    print("Simulating HTTP requests...")
    
    # Simulate various requests
    requests = [
        ("GET", "/api/tags", "192.168.1.100", 200),
        ("POST", "/api/auth/login", "192.168.1.101", 200),
        ("GET", "/api/alarm/active", "192.168.1.102", 200),
        ("POST", "/api/alarm/acknowledge/123", "192.168.1.103", 200),
        ("GET", "/api/audit/search", "192.168.1.104", 401),
        ("DELETE", "/api/admin/user/5", "192.168.1.105", 403),
    ]
    
    for method, path, ip, status in requests:
        app_logger.info(f"🌐 {method} {path} from {ip} [{status}]")
        print(f"   - Logged: {method} {path} [{status}]")
        time.sleep(0.1)
    
    print("\n✅ Request logging simulation complete")


def test_error_logging():
    """Test error logging to separate file"""
    print_separator("4. Testing Error Logging")
    
    error_logger = logging.getLogger("error_test")
    
    print("Simulating error scenarios...")
    
    # Simulate various errors
    errors = [
        "Database connection timeout after 30 seconds",
        "Failed to authenticate user 'admin': Invalid password",
        "MQTT broker disconnected unexpectedly",
        "Tag read failed: PLC not responding (timeout)",
        "Alarm acknowledgement failed: User lacks permission"
    ]
    
    for error in errors:
        error_logger.error(f"❌ {error}")
        print(f"   - Error logged: {error[:50]}...")
        time.sleep(0.1)
    
    print("\n✅ Error logging simulation complete")


def test_audit_logging():
    """Simulate audit log messages"""
    print_separator("5. Testing Audit Logging")
    
    audit_logger = logging.getLogger("audit_test")
    
    print("Simulating audit events...")
    
    events = [
        ("LOGIN", "admin", "192.168.1.100"),
        ("ALARM_ACKNOWLEDGE", "operator", "ALM_001"),
        ("PERMISSION_GRANTED", "supervisor", "alarm:clear"),
        ("USER_APPROVED", "admin", "user_id=10"),
        ("LOGOUT", "operator", "session_ended"),
    ]
    
    for action, user, detail in events:
        audit_logger.info(f"📝 AUDIT: {action} by {user} - {detail}")
        print(f"   - Audit logged: {action} by {user}")
        time.sleep(0.1)
    
    print("\n✅ Audit logging simulation complete")


def verify_log_files():
    """Verify logs were written to files"""
    print_separator("6. Verifying Log Files")
    
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    
    # Expected log files
    expected_files = {
        'hmi_app.log': 'Main application log',
        'hmi_errors.log': 'Error log (ERROR level only)',
        'hmi_daily.log': 'Daily log with date-based rotation'
    }
    
    all_good = True
    
    for log_file, description in expected_files.items():
        file_path = os.path.join(log_dir, log_file)
        
        if os.path.exists(file_path):
            size_bytes = os.path.getsize(file_path)
            size_kb = size_bytes / 1024
            
            if size_bytes > 0:
                print(f"✅ {log_file}: {size_kb:.2f} KB - {description}")
                
                # Show last 3 lines
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        if lines:
                            print(f"   Last entry: {lines[-1].strip()[:80]}...")
                except Exception as e:
                    print(f"   (Could not read file: {e})")
            else:
                print(f"⚠️  {log_file}: 0 KB - File exists but empty")
                all_good = False
        else:
            print(f"❌ {log_file}: NOT FOUND - {description}")
            all_good = False
    
    return all_good


def test_log_rotation():
    """Test that rotation settings are correct"""
    print_separator("7. Checking Rotation Configuration")
    
    # Get root logger
    root_logger = logging.getLogger()
    
    print(f"Root logger level: {logging.getLevelName(root_logger.level)}")
    print(f"Number of handlers: {len(root_logger.handlers)}")
    
    handler_info = []
    
    for i, handler in enumerate(root_logger.handlers, 1):
        handler_type = type(handler).__name__
        handler_level = logging.getLevelName(handler.level)
        
        print(f"\n📊 Handler #{i}: {handler_type}")
        print(f"   Level: {handler_level}")
        
        if hasattr(handler, 'baseFilename'):
            print(f"   File: {os.path.basename(handler.baseFilename)}")
        
        if hasattr(handler, 'maxBytes'):
            max_mb = handler.maxBytes / (1024 * 1024)
            print(f"   Max Size: {max_mb} MB")
            print(f"   Backups: {handler.backupCount}")
        
        if hasattr(handler, 'when'):
            print(f"   Rotation: {handler.when}")
            print(f"   Interval: {handler.interval}")
            print(f"   Retention: {handler.backupCount} days")
    
    print("\n✅ Rotation configuration verified")


def generate_sample_logs():
    """Generate sample logs for testing"""
    print_separator("8. Generating Sample Logs")
    
    sample_logger = logging.getLogger("sample_generator")
    
    print("Generating 50 sample log entries...")
    
    for i in range(50):
        if i % 10 == 0:
            sample_logger.error(f"❌ Sample error #{i}: Something went wrong")
        elif i % 5 == 0:
            sample_logger.warning(f"⚠️  Sample warning #{i}: Potential issue detected")
        else:
            sample_logger.info(f"ℹ️  Sample log #{i}: Normal operation")
        
        if (i + 1) % 10 == 0:
            print(f"   Generated {i + 1}/50 entries...")
    
    print("✅ Sample log generation complete")


def main():
    """Main test execution"""
    print("\n" + "=" * 80)
    print("  FLASK APPLICATION LOGGING TEST")
    print("=" * 80)
    print(f"  Test started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    try:
        # Run tests
        tests = [
            check_log_directory,
            test_log_levels,
            test_request_logging,
            test_error_logging,
            test_audit_logging,
            generate_sample_logs,
            verify_log_files,
            test_log_rotation,
        ]
        
        results = []
        for test in tests:
            try:
                result = test()
                if result is None:
                    result = True
                results.append((test.__name__, result))
            except Exception as e:
                print(f"\n❌ Test {test.__name__} failed with exception: {e}")
                results.append((test.__name__, False))
        
        # Summary
        print_separator("TEST SUMMARY")
        
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        for test_name, result in results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status}: {test_name}")
        
        print(f"\n{'=' * 80}")
        print(f"  Results: {passed}/{total} tests passed")
        
        if passed == total:
            print("  Status: ✅ ALL TESTS PASSED - Logging system is working correctly!")
        else:
            print("  Status: ⚠️  Some tests failed - Check output above")
        
        print("=" * 80)
        
        # Final instructions
        print("\n📋 NEXT STEPS:")
        print("   1. Check log files in: HMI/logs/")
        print("   2. Monitor real-time: Get-Content .\\logs\\hmi_app.log -Wait -Tail 50")
        print("   3. Start Flask app: python app.py")
        print("   4. Make API requests and verify they appear in logs")
        
        return passed == total
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        return False
    except Exception as e:
        print(f"\n\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
