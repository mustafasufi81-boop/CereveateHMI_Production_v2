"""Verify that the tag filtering is working but date-specific data check is missing"""
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    dbname='Automation_DB',
    user='cereveate',
    password='cereveate@222'
)
cur = conn.cursor()

report_date = '2026-05-18'
plants = ['FTP-1', 'PLANT_001', 'Plant1']
areas = ['AREA_A', 'Area-2', 'Area1', 'POTLINE', 'Production']

# Simulate the CURRENT fallback query (line 103-130 in report_service.py)
print("=== CURRENT Query (checks ANY date in view) ===")
cur.execute("""
    SELECT
        tm.tag_id,
        tm.plant,
        tm.area
    FROM historian_meta.tag_master tm
    WHERE tm.plant IN ('FTP-1', 'PLANT_001', 'Plant1')
      AND tm.area IN ('AREA_A', 'Area-2', 'Area1', 'POTLINE', 'Production')
      AND tm.enabled = TRUE
      AND COALESCE(tm.include_in_report, TRUE) = TRUE
      AND tm.tag_id IN (
          SELECT DISTINCT tag_id FROM historian_raw.v_daily_hourly_agg
      )
    ORDER BY tm.equipment, tm.tag_name
""")
current_tags = cur.fetchall()
print(f"Tags returned by CURRENT query: {len(current_tags)}")
if current_tags:
    print("First 5 tags:")
    for row in current_tags[:5]:
        print(f"  {row[0]} | plant={row[1]}, area={row[2]}")

# Now check how many of these tags actually have data on 2026-05-18
current_tag_ids = [row[0] for row in current_tags]
if current_tag_ids:
    cur.execute("""
        SELECT COUNT(DISTINCT tag_id)
        FROM historian_raw.v_daily_hourly_agg
        WHERE tag_id = ANY(%s)
        AND local_date = %s
    """, (current_tag_ids, report_date))
    tags_with_data_today = cur.fetchone()[0]
    print(f"\nOf these {len(current_tags)} tags, only {tags_with_data_today} have data on {report_date}")

# Show which tags have data and which don't
print(f"\n=== Tags WITH data on {report_date} ===")
cur.execute("""
    SELECT DISTINCT v.tag_id, tm.plant, tm.area
    FROM historian_raw.v_daily_hourly_agg v
    JOIN historian_meta.tag_master tm ON v.tag_id = tm.tag_id
    WHERE v.local_date = %s
    AND tm.plant IN ('FTP-1', 'PLANT_001', 'Plant1')
    AND tm.area IN ('AREA_A', 'Area-2', 'Area1', 'POTLINE', 'Production')
    ORDER BY v.tag_id
""", (report_date,))
tags_with_data = cur.fetchall()
print(f"Count: {len(tags_with_data)}")
for row in tags_with_data[:10]:
    print(f"  {row[0]} | plant={row[1]}, area={row[2]}")

print(f"\n=== Tags WITHOUT data on {report_date} (but in tag_master) ===")
cur.execute("""
    SELECT tm.tag_id, tm.plant, tm.area
    FROM historian_meta.tag_master tm
    WHERE tm.plant IN ('FTP-1', 'PLANT_001', 'Plant1')
      AND tm.area IN ('AREA_A', 'Area-2', 'Area1', 'POTLINE', 'Production')
      AND tm.enabled = TRUE
      AND tm.tag_id NOT IN (
          SELECT DISTINCT tag_id 
          FROM historian_raw.v_daily_hourly_agg
          WHERE local_date = %s
      )
    ORDER BY tm.tag_id
    LIMIT 10
""", (report_date,))
tags_without_data = cur.fetchall()
print(f"Count: {len(tags_without_data)} (showing first 10)")
for row in tags_without_data:
    print(f"  {row[0]} | plant={row[1]}, area={row[2]}")

conn.close()
