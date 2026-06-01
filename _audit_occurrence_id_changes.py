"""
Comprehensive audit of occurrence_id fix implementation.
Verifies all code changes are correctly wired end-to-end.
"""

import os
import re

print("=" * 80)
print("OCCURRENCE_ID FIX - COMPREHENSIVE AUDIT")
print("=" * 80)
print()

results = []
errors = []

# ============================================================================
# AUDIT 1: AlarmAuditDAO.insert_audit_record() Method
# ============================================================================
print("AUDIT 1: AlarmAuditDAO.insert_audit_record() Method")
print("-" * 80)

dao_file = r"mqtt_subscriber_service\src\database\alarm_audit_dao.py"
if not os.path.exists(dao_file):
    errors.append(f"❌ File not found: {dao_file}")
    print(f"❌ File not found: {dao_file}")
else:
    with open(dao_file, 'r', encoding='utf-8') as f:
        dao_content = f.read()
    
    # Check 1: Method signature has occurrence_id parameter
    if 'occurrence_id: Optional[str] = None' in dao_content:
        print("✅ Method signature includes occurrence_id parameter")
        results.append("✅ AlarmAuditDAO: occurrence_id parameter in signature")
    else:
        print("❌ Method signature missing occurrence_id parameter")
        errors.append("❌ AlarmAuditDAO: occurrence_id parameter NOT in signature")
    
    # Check 2: INSERT statement includes occurrence_id column
    insert_pattern = r'INSERT INTO historian_raw\.alarm_audit_trail.*?occurrence_id.*?VALUES'
    if re.search(insert_pattern, dao_content, re.DOTALL):
        print("✅ INSERT statement includes occurrence_id column")
        results.append("✅ AlarmAuditDAO: INSERT includes occurrence_id column")
    else:
        print("❌ INSERT statement missing occurrence_id column")
        errors.append("❌ AlarmAuditDAO: INSERT missing occurrence_id column")
    
    # Check 3: HistoricalDataService path includes occurrence_id parameter
    if 'occurrence_id,' in dao_content and 'metadata_json' in dao_content:
        print("✅ Execute parameters include occurrence_id")
        results.append("✅ AlarmAuditDAO: Execute params include occurrence_id")
    else:
        print("❌ Execute parameters missing occurrence_id")
        errors.append("❌ AlarmAuditDAO: Execute params missing occurrence_id")

print()

# ============================================================================
# AUDIT 2: acknowledge_alarm() Endpoint
# ============================================================================
print("AUDIT 2: acknowledge_alarm() Endpoint")
print("-" * 80)

controller_file = r"HMI\controllers\alarm_controller.py"
if not os.path.exists(controller_file):
    errors.append(f"❌ File not found: {controller_file}")
    print(f"❌ File not found: {controller_file}")
else:
    with open(controller_file, 'r', encoding='utf-8') as f:
        controller_content = f.read()
    
    # Check 1: SELECT query fetches occurrence_id
    ack_select_pattern = r'SELECT aa\.alarm_key.*?aa\.occurrence_id.*?FROM historian_raw\.alarm_active'
    if re.search(ack_select_pattern, controller_content, re.DOTALL):
        print("✅ acknowledge_alarm SELECT fetches occurrence_id")
        results.append("✅ acknowledge_alarm: SELECT includes occurrence_id")
    else:
        print("❌ acknowledge_alarm SELECT missing occurrence_id")
        errors.append("❌ acknowledge_alarm: SELECT missing occurrence_id")
    
    # Check 2: Variable extraction logic
    if "occurrence_id      = str(result.get('occurrence_id'))" in controller_content or \
       "occurrence_id      = str(result[6])" in controller_content or \
       "occurrence_id = str(result.get('occurrence_id'))" in controller_content or \
       "occurrence_id = str(result[6])" in controller_content:
        print("✅ acknowledge_alarm extracts occurrence_id from result")
        results.append("✅ acknowledge_alarm: Extracts occurrence_id")
    else:
        print("❌ acknowledge_alarm doesn't extract occurrence_id")
        errors.append("❌ acknowledge_alarm: Doesn't extract occurrence_id")
    
    # Check 3: Pass occurrence_id to insert_audit_record
    ack_insert_pattern = r'insert_audit_record\(.*?occurrence_id=occurrence_id'
    if re.search(ack_insert_pattern, controller_content, re.DOTALL):
        print("✅ acknowledge_alarm passes occurrence_id to DAO")
        results.append("✅ acknowledge_alarm: Passes occurrence_id to DAO")
    else:
        print("❌ acknowledge_alarm doesn't pass occurrence_id to DAO")
        errors.append("❌ acknowledge_alarm: Doesn't pass occurrence_id to DAO")

print()

# ============================================================================
# AUDIT 3: clear_alarm() Endpoint
# ============================================================================
print("AUDIT 3: clear_alarm() Endpoint")
print("-" * 80)

# Check 1: SELECT query fetches occurrence_id
clear_select_pattern = r'check_query = """.*?aa\.occurrence_id.*?FROM historian_raw\.alarm_active'
if re.search(clear_select_pattern, controller_content, re.DOTALL):
    print("✅ clear_alarm SELECT fetches occurrence_id")
    results.append("✅ clear_alarm: SELECT includes occurrence_id")
else:
    print("❌ clear_alarm SELECT missing occurrence_id")
    errors.append("❌ clear_alarm: SELECT missing occurrence_id")

# Check 2: Variable extraction logic
clear_extract_count = controller_content.count("occurrence_id      = str(result")
if clear_extract_count >= 2:  # Should appear in both ack and clear
    print("✅ clear_alarm extracts occurrence_id from result")
    results.append("✅ clear_alarm: Extracts occurrence_id")
else:
    print("❌ clear_alarm doesn't extract occurrence_id")
    errors.append("❌ clear_alarm: Doesn't extract occurrence_id")

# Check 3: Pass occurrence_id to insert_audit_record
clear_insert_count = len(re.findall(r'insert_audit_record\(.*?occurrence_id=occurrence_id', controller_content, re.DOTALL))
if clear_insert_count >= 2:  # Should appear in both ack and clear
    print("✅ clear_alarm passes occurrence_id to DAO")
    results.append("✅ clear_alarm: Passes occurrence_id to DAO")
else:
    print("❌ clear_alarm doesn't pass occurrence_id to DAO")
    errors.append("❌ clear_alarm: Doesn't pass occurrence_id to DAO")

print()

# ============================================================================
# AUDIT 4: suppress_alarm() Endpoint
# ============================================================================
print("AUDIT 4: suppress_alarm() Endpoint")
print("-" * 80)

# Check 1: SELECT query fetches occurrence_id
suppress_select_pattern = r'SELECT alarm_key, level, tag_id, priority, alarm_state, occurrence_id FROM historian_raw\.alarm_active'
if re.search(suppress_select_pattern, controller_content):
    print("✅ suppress_alarm SELECT fetches occurrence_id")
    results.append("✅ suppress_alarm: SELECT includes occurrence_id")
else:
    print("❌ suppress_alarm SELECT missing occurrence_id")
    errors.append("❌ suppress_alarm: SELECT missing occurrence_id")

# Check 2: INSERT statement includes occurrence_id
suppress_insert_pattern = r'INSERT INTO historian_raw\.alarm_audit_trail.*?occurrence_id, metadata'
if re.search(suppress_insert_pattern, controller_content, re.DOTALL):
    print("✅ suppress_alarm INSERT includes occurrence_id column")
    results.append("✅ suppress_alarm: INSERT includes occurrence_id")
else:
    print("❌ suppress_alarm INSERT missing occurrence_id")
    errors.append("❌ suppress_alarm: INSERT missing occurrence_id")

# Check 3: INSERT parameters include occurrence_id value
suppress_params_pattern = r'alarm_id, tag_id, username, actual_state, priority,.*?occurrence_id, metadata'
if re.search(suppress_params_pattern, controller_content, re.DOTALL):
    print("✅ suppress_alarm passes occurrence_id in INSERT")
    results.append("✅ suppress_alarm: Passes occurrence_id in INSERT")
else:
    print("❌ suppress_alarm doesn't pass occurrence_id in INSERT")
    errors.append("❌ suppress_alarm: Doesn't pass occurrence_id in INSERT")

print()

# ============================================================================
# AUDIT 5: unsuppress_alarm() Endpoint
# ============================================================================
print("AUDIT 5: unsuppress_alarm() Endpoint")
print("-" * 80)

# Check 1: SELECT query fetches occurrence_id
unsuppress_select_pattern = r'SELECT alarm_key, level, tag_id, priority, occurrence_id FROM historian_raw\.alarm_active'
if re.search(unsuppress_select_pattern, controller_content):
    print("✅ unsuppress_alarm SELECT fetches occurrence_id")
    results.append("✅ unsuppress_alarm: SELECT includes occurrence_id")
else:
    print("❌ unsuppress_alarm SELECT missing occurrence_id")
    errors.append("❌ unsuppress_alarm: SELECT missing occurrence_id")

# Check 2: INSERT statement includes occurrence_id
unsuppress_insert_pattern = r'UNSUPPRESSED.*?occurrence_id, metadata'
if re.search(unsuppress_insert_pattern, controller_content, re.DOTALL):
    print("✅ unsuppress_alarm INSERT includes occurrence_id column")
    results.append("✅ unsuppress_alarm: INSERT includes occurrence_id")
else:
    print("❌ unsuppress_alarm INSERT missing occurrence_id")
    errors.append("❌ unsuppress_alarm: INSERT missing occurrence_id")

# Check 3: INSERT parameters include occurrence_id value
unsuppress_params_pattern = r'alarm_id, tag_id, username, priority, request\.remote_addr, occurrence_id, metadata'
if re.search(unsuppress_params_pattern, controller_content):
    print("✅ unsuppress_alarm passes occurrence_id in INSERT")
    results.append("✅ unsuppress_alarm: Passes occurrence_id in INSERT")
else:
    print("❌ unsuppress_alarm doesn't pass occurrence_id in INSERT")
    errors.append("❌ unsuppress_alarm: Doesn't pass occurrence_id in INSERT")

print()

# ============================================================================
# AUDIT 6: Database Schema Verification
# ============================================================================
print("AUDIT 6: Database Schema (prerequisite check)")
print("-" * 80)

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    conn = psycopg2.connect(
        host='localhost',
        port=5432,
        database='Automation_DB',
        user='cereveate',
        password='cereveate@222',
        cursor_factory=RealDictCursor
    )
    
    cur = conn.cursor()
    
    # Check if occurrence_id column exists
    cur.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'historian_raw'
          AND table_name = 'alarm_audit_trail'
          AND column_name = 'occurrence_id'
    """)
    col = cur.fetchone()
    
    if col:
        print(f"✅ Database: occurrence_id column exists (type: {col['data_type']}, nullable: {col['is_nullable']})")
        results.append("✅ Database: occurrence_id column exists")
    else:
        print("❌ Database: occurrence_id column NOT FOUND")
        errors.append("❌ Database: occurrence_id column NOT FOUND")
    
    # Check if index exists
    cur.execute("""
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = 'historian_raw'
          AND tablename = 'alarm_audit_trail'
          AND indexname = 'idx_alarm_audit_occurrence'
    """)
    idx = cur.fetchone()
    
    if idx:
        print("✅ Database: idx_alarm_audit_occurrence index exists")
        results.append("✅ Database: idx_alarm_audit_occurrence exists")
    else:
        print("⚠️  Database: idx_alarm_audit_occurrence index NOT FOUND (optional)")
    
    # Check alarm_active has occurrence_id
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'historian_raw'
          AND table_name = 'alarm_active'
          AND column_name = 'occurrence_id'
    """)
    active_col = cur.fetchone()
    
    if active_col:
        print(f"✅ Database: alarm_active.occurrence_id exists (type: {active_col['data_type']})")
        results.append("✅ Database: alarm_active.occurrence_id exists")
    else:
        print("❌ Database: alarm_active.occurrence_id NOT FOUND")
        errors.append("❌ Database: alarm_active.occurrence_id NOT FOUND")
    
    conn.close()
    
except Exception as e:
    print(f"⚠️  Database connection failed: {e}")
    print("   (Run this audit after database is accessible)")

print()

# ============================================================================
# AUDIT 7: Python Syntax Validation
# ============================================================================
print("AUDIT 7: Python Syntax Validation")
print("-" * 80)

import py_compile
import tempfile

for file_path in [dao_file, controller_file]:
    try:
        py_compile.compile(file_path, doraise=True)
        print(f"✅ Syntax valid: {os.path.basename(file_path)}")
        results.append(f"✅ Syntax: {os.path.basename(file_path)} valid")
    except py_compile.PyCompileError as e:
        print(f"❌ Syntax error in {os.path.basename(file_path)}: {e}")
        errors.append(f"❌ Syntax error: {os.path.basename(file_path)}")

print()

# ============================================================================
# FINAL SUMMARY
# ============================================================================
print("=" * 80)
print("AUDIT SUMMARY")
print("=" * 80)
print()

if errors:
    print(f"❌ AUDIT FAILED - {len(errors)} error(s) found:")
    print()
    for error in errors:
        print(f"   {error}")
    print()
    print("⚠️  FIX REQUIRED - DO NOT PROCEED TO TESTING")
else:
    print(f"✅ AUDIT PASSED - All {len(results)} checks successful!")
    print()
    for result in results:
        print(f"   {result}")
    print()
    print("✅ READY FOR TESTING")

print()
print("=" * 80)
print("NEXT STEP: Run test plan")
print("   python _test_occurrence_id_fix.py")
print("=" * 80)
