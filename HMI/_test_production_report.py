"""Test report system using ACTUAL production setup"""
import sys
sys.path.insert(0, '.')

from container import container
from services.report_service import ReportService
from datetime import date, timedelta

print("\n📊 PRODUCTION REPORT SYSTEM TEST\n")

# Use the REAL production connection (with RealDictCursor)
service = ReportService(container.historical_service.connection, container.config)

test_date = date.today() - timedelta(days=1)
print(f"Testing date: {test_date}\n")

try:
    result = service.build_daily_report(
        report_date=test_date,
        plant='Plant1',
        area='Area1',
        generated_by='PRODUCTION_TEST',
        page=1,
        page_size=5
    )
    
    print(f"✅ SUCCESS!")
    print(f"   Rows: {len(result['rows'])}")
    print(f"   Total: {result['pagination']['total_rows']}")
    print(f"   Columns: {len(result['columns'])}")
    
    if result['rows']:
        row = result['rows'][0]
        print(f"\n   Sample Row:")
        print(f"     Tag: {row['tag_id']}")
        print(f"     Desc: {row['description']}")
        print(f"     Avg: {row['avg']}")
        print(f"     Max: {row['max']}")
        print(f"     Min: {row['min']}")
        
        # Count non-null hourly values
        hourly = [row.get(col) for col in result['columns']]
        filled = sum(1 for v in hourly if v is not None)
        print(f"     Hourly data: {filled}/24 hours")
        
        if filled == 0:
            print("\n⚠️  WARNING: No hourly data found!")
            print("   Check v_daily_hourly_agg has data for this date")
    else:
        print("\n⚠️  No rows returned - possible issues:")
        print("   1. No report templates configured")
        print("   2. No historian data for this date")
        print("   3. Plant/Area mismatch")
        
except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n✅ TEST COMPLETE\n")
