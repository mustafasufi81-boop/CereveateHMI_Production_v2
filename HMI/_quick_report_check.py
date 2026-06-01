import psycopg2
import json
from datetime import date, timedelta

with open('config.json', 'r') as f:
    config = json.load(f)

db = config['database']
conn = psycopg2.connect(host=db['host'], port=db['port'], database=db['database'], user=db['user'], password=db['password'])
cur = conn.cursor()

print("\n🔍 QUICK REPORT AUDIT\n")

# 1. Report templates
cur.execute("SELECT COUNT(*) FROM historian_meta.v_report_template_tags WHERE report_type = 'DAILY'")
print(f"✓ DAILY tags: {cur.fetchone()[0]}")

# 2. Shifts
cur.execute("SELECT COUNT(*) FROM historian_meta.shifts")
print(f"✓ Shifts: {cur.fetchone()[0]}")

# 3. Check data view
cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.views WHERE table_schema='historian_raw' AND table_name='v_daily_hourly_agg')")
has_view = cur.fetchone()[0]
print(f"{'✓' if has_view else '❌'} v_daily_hourly_agg view: {'EXISTS' if has_view else 'MISSING'}")

if has_view:
    yesterday = date.today() - timedelta(days=1)
    cur.execute("SELECT COUNT(*) FROM historian_raw.v_daily_hourly_agg WHERE local_date = %s", (yesterday,))
    print(f"  Data for {yesterday}: {cur.fetchone()[0]} records")

# 4. Test Python service
print("\n📊 Testing Python Report Service...")
try:
    from services.report_service import ReportService
    rs = ReportService(conn, config)
    result = rs.build_daily_report(date.today() - timedelta(days=1), 'Plant1', 'Area1', 'TEST', page=1, page_size=5)
    print(f"✓ Report generated: {len(result['rows'])} rows")
    if result['rows']:
        print(f"  First tag: {result['rows'][0]['tag_id']}")
        print(f"  Has data: {result['rows'][0]['avg'] is not None}")
except Exception as e:
    print(f"❌ Error: {str(e)[:100]}")

cur.close()
conn.close()
print("\n✅ AUDIT DONE\n")
