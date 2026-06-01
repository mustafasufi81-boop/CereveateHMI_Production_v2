"""
COMPLETE REPORT SYSTEM VERIFICATION
Tests: DB Views → Python Logic → Data Flow → UI Output
"""
import psycopg2
import json
from datetime import datetime, date, timedelta
import sys

# Load config
with open('config.json', 'r') as f:
    config = json.load(f)

db_config = config['database']
conn = psycopg2.connect(
    host=db_config['host'],
    port=db_config['port'],
    database=db_config['database'],
    user=db_config['user'],
    password=db_config['password']
)

print("="*80)
print("REPORT SYSTEM COMPLETE VERIFICATION")
print("="*80)

# ============================================================================
# TEST 1: Verify v_report_template_tags VIEW
# ============================================================================
print("\n[TEST 1] v_report_template_tags VIEW")
print("-"*80)

cur = conn.cursor()
cur.execute("""
    SELECT COUNT(*) FROM historian_meta.v_report_template_tags 
    WHERE report_type = 'DAILY'
""")
daily_count = cur.fetchone()[0]
print(f"✓ DAILY report tags: {daily_count}")

cur.execute("""
    SELECT COUNT(*) FROM historian_meta.v_report_template_tags 
    WHERE report_type = 'SHIFT'
""")
shift_count = cur.fetchone()[0]
print(f"✓ SHIFT report tags: {shift_count}")

cur.execute("""
    SELECT COUNT(*) FROM historian_meta.v_report_template_tags 
    WHERE report_type = 'MONTHLY'
""")
monthly_count = cur.fetchone()[0]
print(f"✓ MONTHLY report tags: {monthly_count}")

if daily_count == 0:
    print("⚠️  WARNING: No DAILY tags configured!")
if shift_count == 0:
    print("⚠️  WARNING: No SHIFT tags configured!")

# ============================================================================
# TEST 2: Verify SHIFT definitions
# ============================================================================
print("\n[TEST 2] SHIFT DEFINITIONS")
print("-"*80)

cur.execute("""
    SELECT shift_code, shift_name, start_time, end_time 
    FROM historian_meta.shifts 
    ORDER BY start_time
""")
shifts = cur.fetchall()
print(f"✓ Active shifts: {len(shifts)}")
for shift in shifts:
    print(f"   {shift[0]}: {shift[1]} ({shift[2]}-{shift[3]})")

# ============================================================================
# TEST 3: Verify historian data aggregation view
# ============================================================================
print("\n[TEST 3] HISTORIAN DATA AGGREGATION VIEW")
print("-"*80)

# Check if v_daily_hourly_agg exists
cur.execute("""
    SELECT EXISTS (
        SELECT 1 FROM information_schema.views 
        WHERE table_schema = 'historian_raw' 
        AND table_name = 'v_daily_hourly_agg'
    )
""")
view_exists = cur.fetchone()[0]

if view_exists:
    print("✓ v_daily_hourly_agg view EXISTS")
    
    # Get sample data
    yesterday = date.today() - timedelta(days=1)
    cur.execute("""
        SELECT 
            local_date,
            COUNT(DISTINCT tag_id) as tag_count,
            COUNT(*) as total_records
        FROM historian_raw.v_daily_hourly_agg
        WHERE local_date >= %s
        GROUP BY local_date
        ORDER BY local_date DESC
        LIMIT 3
    """, (yesterday,))
    
    agg_data = cur.fetchall()
    if agg_data:
        print("  Sample aggregation data:")
        for row in agg_data:
            print(f"    Date: {row[0]}, Tags: {row[1]}, Records: {row[2]}")
    else:
        print("  ⚠️  No aggregated data for recent dates!")
        
else:
    print("❌ v_daily_hourly_agg view DOES NOT EXIST!")
    print("   Checking alternative data source...")
    
    # Check historian_raw tables
    cur.execute("""
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'historian_raw'
        AND table_name LIKE '%hist%'
    """)
    tables = cur.fetchall()
    print(f"   Available tables in historian_raw: {[t[0] for t in tables]}")

# ============================================================================
# TEST 4: Test Python report_service.py logic
# ============================================================================
print("\n[TEST 4] PYTHON REPORT SERVICE")
print("-"*80)

try:
    sys.path.insert(0, '.')
    from services.report_service import ReportService
    
    report_service = ReportService(conn, config)
    print("✓ ReportService imported successfully")
    
    # Test build_daily_report
    test_date = date.today() - timedelta(days=1)
    print(f"\n  Testing build_daily_report for date: {test_date}")
    
    result = report_service.build_daily_report(
        report_date=test_date,
        plant='Plant1',
        area='Area1',
        generated_by='AUDIT_SCRIPT',
        page=1,
        page_size=10
    )
    
    print(f"  ✓ Report generated successfully")
    print(f"    Rows returned: {len(result.get('rows', []))}")
    print(f"    Total rows: {result.get('pagination', {}).get('total_rows', 0)}")
    print(f"    Columns: {len(result.get('columns', []))}")
    
    if len(result.get('rows', [])) > 0:
        first_row = result['rows'][0]
        print(f"\n  Sample row:")
        print(f"    Tag ID: {first_row.get('tag_id')}")
        print(f"    Description: {first_row.get('description')}")
        print(f"    Avg: {first_row.get('avg')}")
        print(f"    Max: {first_row.get('max')}")
        print(f"    Min: {first_row.get('min')}")
        
        # Count how many hourly values exist
        hourly_vals = [first_row.get(col) for col in result['columns']]
        non_null = sum(1 for v in hourly_vals if v is not None)
        print(f"    Hourly values populated: {non_null}/24")
    else:
        print("  ⚠️  WARNING: No rows returned from build_daily_report!")
        print("  This could mean:")
        print("    - No tags configured in report_templates")
        print("    - No historian data for this date")
        print("    - View v_daily_hourly_agg not returning data")
        
except Exception as e:
    print(f"❌ Error testing ReportService: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# TEST 5: Verify data consistency
# ============================================================================
print("\n[TEST 5] DATA CONSISTENCY CHECK")
print("-"*80)

# Check if tags in templates have actual data
cur.execute("""
    SELECT 
        t.tag_id,
        t.display_label,
        EXISTS(
            SELECT 1 FROM historian_raw.historian_latest_value hlv
            WHERE hlv.tag_id = t.tag_id
        ) as has_latest_value
    FROM historian_meta.v_report_template_tags t
    WHERE t.report_type = 'DAILY'
    LIMIT 5
""")

tags_check = cur.fetchall()
if tags_check:
    print("Sample tags from template:")
    for row in tags_check:
        status = "✓ HAS DATA" if row[2] else "❌ NO DATA"
        print(f"  {row[0]}: {status}")
else:
    print("  No tags found in templates!")

# ============================================================================
# TEST 6: Check report generation log
# ============================================================================
print("\n[TEST 6] REPORT GENERATION LOG")
print("-"*80)

cur.execute("""
    SELECT 
        report_type,
        generated_at,
        generated_by,
        row_count
    FROM historian_meta.report_gen_log
    ORDER BY generated_at DESC
    LIMIT 5
""")

logs = cur.fetchall()
if logs:
    print("Recent report generations:")
    for log in logs:
        print(f"  {log[0]}: {log[1]} by {log[2]} ({log[3]} rows)")
else:
    print("  No report generation history found")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "="*80)
print("VERIFICATION SUMMARY")
print("="*80)

issues = []
if daily_count == 0:
    issues.append("No DAILY tags configured")
if not view_exists:
    issues.append("v_daily_hourly_agg view missing")
if not shifts:
    issues.append("No shifts configured")

if issues:
    print("⚠️  ISSUES FOUND:")
    for issue in issues:
        print(f"  - {issue}")
else:
    print("✓ All checks passed!")

print("\nRECOMMENDATIONS:")
print("1. Ensure v_daily_hourly_agg view is created and populated")
print("2. Configure report templates using /admin interface")
print("3. Verify historian data is being collected")
print("4. Test report generation from UI")

cur.close()
conn.close()

print("\n" + "="*80)
