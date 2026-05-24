#!/usr/bin/env python3
"""Debug PLC connection settings and read behavior"""
from pycomm3 import LogixDriver
import time

print("=" * 80)
print("TESTING PLC CONNECTION SETTINGS")
print("=" * 80)

# Test 1: Default connection
print("\n[TEST 1] Default connection (same as scanner)")
try:
    plc = LogixDriver('192.168.0.20/1,0')
    plc.open()
    print(f"✅ Connected")
    print(f"   - Path: {plc._cfg['path']}")
    print(f"   - Timeout: {plc._cfg.get('timeout', 'default')}")
    
    # Test rapid batch reads (like scanner does)
    print("\n[TEST 1A] Rapid batch reads (10 iterations)")
    tags = ["Welding_Current_A", "Welding_Voltage_V", "Arc"]
    errors = 0
    for i in range(10):
        results = plc.read(*tags)
        for tag, result in zip(tags, results):
            if hasattr(result, 'error') and result.error:
                print(f"   ❌ Iteration {i+1}: {tag} - {result.error}")
                errors += 1
        time.sleep(0.01)  # 10ms like scanner
    
    if errors == 0:
        print(f"   ✅ All 10 iterations successful (0 errors)")
    else:
        print(f"   ❌ Total errors: {errors}/30 reads")
    
    plc.close()
except Exception as e:
    print(f"❌ ERROR: {e}")

# Test 2: Connection with longer timeout
print("\n[TEST 2] Connection with extended timeout")
try:
    plc = LogixDriver('192.168.0.20/1,0', init_tags=False, init_info=False)
    plc.open()
    print(f"✅ Connected")
    
    # Test with all welding tags at once
    print("\n[TEST 2A] Read all 9 welding tags at once")
    all_tags = [
        "Welding_Current_A", "Welding_Voltage_V", "Arc",
        "Power", "Welder_id", "WPS_ID",
        "Joint_Id", "Pipe_Id", "sim_step"
    ]
    
    results = plc.read(*all_tags)
    success = 0
    for tag, result in zip(all_tags, results):
        if hasattr(result, 'error') and result.error:
            print(f"   ❌ {tag}: {result.error}")
        else:
            success += 1
    
    print(f"   ✅ Success: {success}/{len(all_tags)} tags")
    
    plc.close()
except Exception as e:
    print(f"❌ ERROR: {e}")

# Test 3: Individual tag reads vs batch
print("\n[TEST 3] Individual reads vs batch reads")
try:
    plc = LogixDriver('192.168.0.20/1,0')
    plc.open()
    
    test_tags = ["Welding_Current_A", "Welding_Voltage_V", "Arc"]
    
    print("\n[TEST 3A] Individual reads (one by one)")
    for tag in test_tags:
        result = plc.read(tag)
        if hasattr(result, 'error') and result.error:
            print(f"   ❌ {tag}: {result.error}")
        else:
            print(f"   ✅ {tag}: {result.value}")
    
    print("\n[TEST 3B] Batch read (all at once)")
    results = plc.read(*test_tags)
    for tag, result in zip(test_tags, results):
        if hasattr(result, 'error') and result.error:
            print(f"   ❌ {tag}: {result.error}")
        else:
            print(f"   ✅ {tag}: {result.value}")
    
    plc.close()
    print("\n✅ Test complete")
    
except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("RECOMMENDATION:")
print("If batch reads show errors but individual reads work,")
print("the scanner should read tags one-by-one instead of batch mode.")
print("=" * 80)
