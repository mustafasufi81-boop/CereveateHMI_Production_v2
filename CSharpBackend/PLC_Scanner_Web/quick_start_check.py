#!/usr/bin/env python3
"""
Quick Start Test - Verifies plc_scanner_web.py is ready to run
"""

import sys

def main():
    print("\n" + "="*70)
    print("QUICK START CHECK - plc_scanner_web.py")
    print("="*70)
    
    checks_passed = 0
    checks_total = 5
    
    # Check 1: File exists
    print("\n[1/5] Checking file exists...")
    try:
        with open('plc_scanner_web.py', 'r', encoding='utf-8') as f:
            content = f.read()
        print("      ✓ plc_scanner_web.py found")
        checks_passed += 1
    except FileNotFoundError:
        print("      ✗ plc_scanner_web.py not found!")
        return 1
    
    # Check 2: PLC_PATH configuration
    print("\n[2/5] Checking PLC configuration...")
    if 'PLC_PATH = f"{PLC_IP}/1,0"' in content:
        print("      ✓ PLC_PATH configured correctly")
        checks_passed += 1
    else:
        print("      ✗ PLC_PATH not configured correctly")
    
    # Check 3: LogixDriver syntax
    print("\n[3/5] Checking LogixDriver syntax...")
    if 'LogixDriver(PLC_PATH)' in content:
        print("      ✓ LogixDriver syntax correct")
        checks_passed += 1
    else:
        print("      ✗ LogixDriver syntax incorrect")
    
    # Check 4: execute_values import
    print("\n[4/5] Checking imports...")
    if 'from psycopg2.extras import RealDictCursor, execute_values' in content:
        print("      ✓ execute_values imported at top level")
        checks_passed += 1
    else:
        print("      ✗ execute_values not imported correctly")
    
    # Check 5: Python syntax
    print("\n[5/5] Checking Python syntax...")
    import py_compile
    try:
        py_compile.compile('plc_scanner_web.py', doraise=True)
        print("      ✓ No syntax errors")
        checks_passed += 1
    except py_compile.PyCompileError as e:
        print(f"      ✗ Syntax error: {e}")
    
    # Results
    print("\n" + "="*70)
    print(f"RESULTS: {checks_passed}/{checks_total} checks passed")
    print("="*70)
    
    if checks_passed == checks_total:
        print("\n✓ ALL CHECKS PASSED!")
        print("\nYou can now run:")
        print("  python plc_scanner_web.py")
        print("\nWeb interface will be available at:")
        print("  http://localhost:7001")
        print("\n" + "="*70)
        return 0
    else:
        print("\n✗ SOME CHECKS FAILED")
        print("Please review the errors above.")
        print("="*70)
        return 1

if __name__ == '__main__':
    sys.exit(main())
