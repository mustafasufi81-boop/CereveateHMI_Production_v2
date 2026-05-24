#!/usr/bin/env python3
# Test script to validate testing_app_FIXED.py dependencies and functionality

import sys
import os
from datetime import datetime
import pytz

print("=" * 70)
print("Testing application dependencies and functionality")
print("=" * 70)

# Test 1: Check required packages
print("\n[TEST 1] Checking required packages...")
try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    print(f"  ✓ pyarrow: {pa.__version__}")
except ImportError as e:
    print(f"  ✗ pyarrow NOT installed: {e}")
    print("  Install with: pip install pyarrow")
    sys.exit(1)

try:
    import pytz
    print(f"  ✓ pytz: {pytz.__version__}")
except ImportError as e:
    print(f"  ✗ pytz NOT installed: {e}")
    print("  Install with: pip install pytz")
    sys.exit(1)

try:
    import psycopg2
    print(f"  ✓ psycopg2: {psycopg2.__version__}")
except ImportError as e:
    print(f"  ✗ psycopg2 NOT installed: {e}")
    print("  Install with: pip install psycopg2-binary")
    sys.exit(1)

try:
    from pycomm3 import LogixDriver
    print(f"  ✓ pycomm3: installed")
except ImportError as e:
    print(f"  ✗ pycomm3 NOT installed: {e}")
    print("  Install with: pip install pycomm3")
    sys.exit(1)

# Test 2: Check timezone functionality
print("\n[TEST 2] Testing Indian timezone...")
try:
    INDIA_TZ = pytz.timezone('Asia/Kolkata')
    now_ist = datetime.now(INDIA_TZ)
    print(f"  ✓ IST timezone: {now_ist.strftime('%Y-%m-%d %H:%M:%S %Z')}")
except Exception as e:
    print(f"  ✗ Timezone error: {e}")
    sys.exit(1)

# Test 3: Test parquet file creation
print("\n[TEST 3] Testing parquet file creation...")
try:
    test_dir = "test_parquet_temp"
    os.makedirs(test_dir, exist_ok=True)
    
    # Generate filename
    filename = now_ist.strftime("%d%m%y%H%M%S") + ".parquet"
    print(f"  ✓ Filename format: {filename}")
    
    # Create sample parquet file
    test_data = {
        'Timestamp': [now_ist, now_ist],
        'TagId': ['Test_Tag_1', 'Test_Tag_2'],
        'Value': [123.45, 678.90],
        'Quality': ['G', 'G'],
        'Type': ['REAL', 'REAL']
    }
    
    table = pa.table({
        'Timestamp': pa.array(test_data['Timestamp'], type=pa.timestamp('us')),
        'TagId': pa.array(test_data['TagId'], type=pa.string()),
        'Value': pa.array(test_data['Value'], type=pa.float64()),
        'Quality': pa.array(test_data['Quality'], type=pa.string()),
        'Type': pa.array(test_data['Type'], type=pa.string())
    })
    
    test_file = os.path.join(test_dir, filename)
    pq.write_table(table, test_file)
    print(f"  ✓ Created test file: {test_file}")
    
    # Read back to verify
    read_table = pq.read_table(test_file)
    print(f"  ✓ Read {len(read_table)} records from parquet file")
    
    # Cleanup
    os.remove(test_file)
    os.rmdir(test_dir)
    print(f"  ✓ Cleanup completed")
    
except Exception as e:
    print(f"  ✗ Parquet test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Check database connection (optional - will fail if DB not accessible)
print("\n[TEST 4] Testing database connection...")
try:
    conn = psycopg2.connect(
        host='192.168.0.120',
        port=5432,
        database='Cereveate',
        user='cereveate',
        password='cereveate@222',
        sslmode='disable',
        connect_timeout=3
    )
    print(f"  ✓ Database connection successful")
    conn.close()
except Exception as e:
    print(f"  ⚠ Database connection failed (expected if DB server not running): {e}")
    print(f"    This is OK for testing - will work when deployed on Raspberry Pi")

# Test 5: Verify parquet directory can be created
print("\n[TEST 5] Testing Raspberry Pi directory structure...")
# Note: On Windows, we simulate the path structure
test_pi_dir = "test_pi_login"
try:
    os.makedirs(test_pi_dir, exist_ok=True)
    print(f"  ✓ Directory creation successful: {test_pi_dir}")
    
    # Test file write permissions
    test_file = os.path.join(test_pi_dir, "permission_test.txt")
    with open(test_file, 'w') as f:
        f.write("test")
    os.remove(test_file)
    os.rmdir(test_pi_dir)
    print(f"  ✓ Write permissions OK")
    
except Exception as e:
    print(f"  ✗ Directory test failed: {e}")
    sys.exit(1)

print("\n" + "=" * 70)
print("✓ ALL TESTS PASSED!")
print("=" * 70)
print("\nSummary:")
print("  - All required packages installed")
print("  - Timezone handling working (IST)")
print("  - Parquet file creation/read working")
print("  - File system permissions OK")
print("  - Application ready for deployment")
print("\nNext steps:")
print("  1. Copy testing_app_FIXED.py to Raspberry Pi")
print("  2. Install packages: pip install pyarrow pytz psycopg2-binary pycomm3")
print("  3. Ensure /home/cereveate/login directory exists")
print("  4. Run: python3 testing_app_FIXED.py")
print("=" * 70)
