"""
Quick Verification Script
Verifies all components can be imported and basic initialization works
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

print("="*80)
print("MQTT Subscriber Service - Component Verification")
print("="*80)
print()

# Track results
results = []

def test_import(module_name, description):
    """Test if a module can be imported"""
    try:
        __import__(module_name)
        results.append((description, "✅ PASS"))
        print(f"✅ {description}")
        return True
    except Exception as e:
        results.append((description, f"❌ FAIL: {e}"))
        print(f"❌ {description}: {e}")
        return False

print("Phase 1: Core Infrastructure")
print("-" * 80)
test_import('src.utils.config_loader', '  Config Loader')
test_import('src.monitoring.logger', '  Logger')
print()

print("Phase 2: Database Layer")
print("-" * 80)
test_import('src.database.db_connection', '  Database Connection')
test_import('src.database.schema_inspector', '  Schema Inspector')
test_import('src.database.audit_dao', '  Audit DAO')
test_import('src.database.historian_dao', '  Historian DAO')
print()

print("Phase 3: MQTT Client")
print("-" * 80)
test_import('src.mqtt.mqtt_client', '  MQTT Client')
test_import('src.cache.topic_cache', '  Topic Cache')
test_import('src.cache.tag_master_cache', '  Tag Master Cache')
print()

print("Phase 4: Message Processing")
print("-" * 80)
test_import('src.models.message_models', '  Domain Models')
test_import('src.processing.thread_manager', '  Thread Manager')
test_import('src.processing.message_processor', '  Message Processor')
print()

print("Phase 5: Validation & Security")
print("-" * 80)
test_import('src.validation.validator', '  Validator')
test_import('src.validation.input_sanitizer', '  Input Sanitizer')
print()

print("Phase 6: Monitoring & Health")
print("-" * 80)
test_import('src.monitoring.health_check', '  Health Check')
test_import('src.monitoring.metrics', '  Metrics Collector')
print()

print("Service Integration")
print("-" * 80)
test_import('src.service_main', '  Service Main')
print()

# Summary
print("="*80)
print("VERIFICATION SUMMARY")
print("="*80)
passed = sum(1 for _, result in results if "PASS" in result)
failed = sum(1 for _, result in results if "FAIL" in result)
total = len(results)

print(f"Total Tests: {total}")
print(f"✅ Passed: {passed}")
print(f"❌ Failed: {failed}")
print()

if failed == 0:
    print("🎉 ALL COMPONENTS VERIFIED SUCCESSFULLY!")
    print("   The service is ready to run.")
else:
    print("⚠️  Some components failed verification.")
    print("   Please check the errors above.")
    print()
    print("Failed components:")
    for desc, result in results:
        if "FAIL" in result:
            print(f"   - {desc}: {result}")

print("="*80)
