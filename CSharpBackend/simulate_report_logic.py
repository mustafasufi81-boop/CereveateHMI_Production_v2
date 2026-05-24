"""Simulate the exact logic of report_service.build_daily_report()"""
import psycopg2
from datetime import datetime, timedelta

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    dbname='Automation_DB',
    user='cereveate',
    password='cereveate@222'
)

report_date_str = '2026-05-18'
report_date = datetime.strptime(report_date_str, '%Y-%m-%d').date()
plants = ['FTP-1', 'PLANT_001', 'Plant1']
areas = ['AREA_A', 'Area-2', 'Area1', 'POTLINE', 'Production']

cur = conn.cursor()

# Step 1: Get template tags (fallback query, lines 103-130)
print("=== Step 1: Get template tags ===")
area_placeholders = ",".join(['%s'] * len(areas))
plant_placeholders = ",".join(['%s'] * len(plants))

query = f"""
    SELECT
        ROW_NUMBER() OVER (ORDER BY tm.equipment, tm.tag_name) AS s_no,
        tm.tag_id,
        tm.tag_name AS display_label,
        tm.equipment AS group_name,
        COALESCE(tm.eng_unit, tm.data_type, '') AS parameter_unit,
        tm.plant,
        tm.area
    FROM historian_meta.tag_master tm
    WHERE tm.plant IN ({plant_placeholders})
      AND tm.area IN ({area_placeholders})
      AND tm.enabled = TRUE
      AND COALESCE(tm.include_in_report, TRUE) = TRUE
      AND tm.tag_id IN (
          SELECT DISTINCT tag_id FROM historian_raw.v_daily_hourly_agg
      )
    ORDER BY tm.equipment, tm.tag_name
"""

cur.execute(query, (*plants, *areas))
template_rows = cur.fetchall()
print(f"Template rows: {len(template_rows)}")
if template_rows:
    print(f"First row: {template_rows[0]}")

# Step 2: Get tag_ids from template
tag_ids = [row[1] for row in template_rows]  # row[1] is tag_id
print(f"\nTag IDs to query: {len(tag_ids)}")

# Step 3: Query v_daily_hourly_agg for these tags on the report date
print(f"\n=== Step 2: Query hourly data for {report_date_str} ===")
cur.execute("""
    SELECT
        tag_id,
        local_date,
        local_hour AS hour,
        avg_val,
        max_val,
        min_val
    FROM historian_raw.v_daily_hourly_agg
    WHERE tag_id = ANY(%s)
      AND local_date = %s
    ORDER BY tag_id, local_date, local_hour
""", (tag_ids, report_date))

agg_rows = cur.fetchall()
print(f"Aggregated rows from view: {len(agg_rows)}")

if agg_rows:
    print(f"\nFirst 5 rows:")
    for row in agg_rows[:5]:
        print(f"  {row[0]} | date={row[1]} | hour={row[2]} | avg={row[3]}, max={row[4]}, min={row[5]}")
    
    # Group by tag
    tags_with_data = set(row[0] for row in agg_rows)
    print(f"\nUnique tags with data on {report_date_str}: {len(tags_with_data)}")
    print(f"Tags WITHOUT data: {len(tag_ids) - len(tags_with_data)}")
    
    # Show which tags have data
    print(f"\nTags WITH data (first 10):")
    for tag in list(tags_with_data)[:10]:
        print(f"  {tag}")
else:
    print("\n❌ NO AGGREGATED DATA RETURNED!")
    print("\nPossible reasons:")
    print("1. View has no data for this date")
    print("2. Tag IDs don't match")
    print("3. Date format mismatch")

# Step 4: Check if the ISSUE is that the report shows all 123 tags but most have no data
print(f"\n=== Step 3: Build report rows ===")
print(f"Would create {len(template_rows)} rows (one per template tag)")
print(f"But only {len(tags_with_data) if agg_rows else 0} tags have actual data")
print(f"\nThis explains why UI shows '{len(template_rows)} tags' but displays empty values!")

conn.close()
