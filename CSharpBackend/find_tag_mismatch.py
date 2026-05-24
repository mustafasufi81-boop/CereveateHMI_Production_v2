"""Find why template tags don't match view data tags"""
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

# Get tags that the report query returns
print("=== Tags returned by report template query ===")
plant_placeholders = ",".join(['%s'] * len(plants))
area_placeholders = ",".join(['%s'] * len(areas))

cur.execute(f"""
    SELECT
        tm.tag_id,
        tm.plant,
        tm.area,
        tm.equipment
    FROM historian_meta.tag_master tm
    WHERE tm.plant IN ({plant_placeholders})
      AND tm.area IN ({area_placeholders})
      AND tm.enabled = TRUE
      AND COALESCE(tm.include_in_report, TRUE) = TRUE
      AND tm.tag_id IN (
          SELECT DISTINCT tag_id FROM historian_raw.v_daily_hourly_agg
      )
    ORDER BY tm.equipment, tm.tag_name
    LIMIT 10
""", (*plants, *areas))

template_tags = cur.fetchall()
print(f"Template tags (first 10 of {cur.rowcount if hasattr(cur, 'rowcount') else 'many'}):")
for row in template_tags:
    print(f"  {row[0]} | plant={row[1]}, area={row[2]}, equipment={row[3]}")

# Get tags that actually have data on 2026-05-18
print(f"\n=== Tags with data in view on {report_date} ===")
cur.execute(f"""
    SELECT DISTINCT v.tag_id, tm.plant, tm.area, tm.equipment
    FROM historian_raw.v_daily_hourly_agg v
    LEFT JOIN historian_meta.tag_master tm ON v.tag_id = tm.tag_id
    WHERE v.local_date = %s
    AND tm.plant IN ({plant_placeholders})
    AND tm.area IN ({area_placeholders})
    ORDER BY v.tag_id
""", (report_date, *plants, *areas))

view_tags = cur.fetchall()
print(f"Tags with data (total: {len(view_tags)}):")
for row in view_tags:
    print(f"  {row[0]} | plant={row[1]}, area={row[2]}, equipment={row[3]}")

# Find the mismatch
template_tag_ids = set(row[0] for row in template_tags) if template_tags else set()
view_tag_ids = set(row[0] for row in view_tags)

print(f"\n=== Analysis ===")
print(f"Template query returns: {len(template_tag_ids) if template_tags else 'unknown'} unique tags (sample of 10 shown)")
print(f"View has data for: {len(view_tag_ids)} tags on {report_date}")

if template_tags and view_tag_ids:
    # Check first 10 template tags
    sample_ids = [row[0] for row in template_tags[:10]]
    overlap = [tid for tid in sample_ids if tid in view_tag_ids]
    print(f"\nOf the first 10 template tags, {len(overlap)} have data on {report_date}")
    if overlap:
        print(f"  Tags with data: {overlap}")

conn.close()
