"""
QUICK TEST EXECUTION GUIDE - occurrence_id Fix
Run this after starting HMI to complete testing
"""

print("=" * 80)
print("OCCURRENCE_ID FIX - QUICK TEST GUIDE")
print("=" * 80)
print()

print("STEP 1: START HMI SERVICE")
print("-" * 80)
print("cd d:\\CereveateHMI_Production\\HMI")
print("python app.py")
print()
print("Wait for: 'Running on http://0.0.0.0:6001'")
print()

print("STEP 2: PERFORM TEST ACTIONS (choose one method)")
print("-" * 80)
print()
print("METHOD A - Via UI (Easiest):")
print("  1. Open browser: http://localhost:8090")
print("  2. Login: admin / admin123")
print("  3. Go to Alarms page")
print("  4. Click ACK on any active alarm")
print("  5. Click CLEAR on an acknowledged alarm")
print("  6. Click SUPPRESS on an alarm")
print()
print("METHOD B - Via PowerShell API:")
print("  Run the test commands in: _quick_api_test.ps1")
print()

print("STEP 3: RUN VERIFICATION")
print("-" * 80)
print("cd d:\\CereveateHMI_Production")
print("python _test_occurrence_id_fix.py --verify")
print()

print("EXPECTED RESULTS:")
print("-" * 80)
print("✅ New audit records have occurrence_id populated")
print("✅ occurrence_id matches alarm_active table")
print("✅ All action types write occurrence_id correctly")
print("✅ Old records remain NULL (expected)")
print()

print("VERIFICATION SCRIPTS:")
print("-" * 80)
print("1. Full audit:  python _audit_occurrence_id_changes.py")
print("2. Full test:   python _test_occurrence_id_fix.py")
print("3. Verify post: python _test_occurrence_id_fix.py --verify")
print("4. Quick check: python _verify_occurrence_id_fix.py")
print()

print("CURRENT STATUS:")
print("-" * 80)
print("✅ Code audit: PASSED (20/20 checks)")
print("✅ Database ready: 5 active alarms available")
print("⏳ HMI testing: PENDING (start HMI)")
print()

print("=" * 80)
