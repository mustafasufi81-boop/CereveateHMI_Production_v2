import psycopg2

# Connect with correct credentials
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="Automation_DB",
    user="cereveate",
    password="cereveate@222"
)

cursor = conn.cursor()

# Check what the template query returns
query = """
SELECT vt.s_no, vt.tag_id, vt.display_label, vt.group_name, vt.parameter_unit,
       vt.plant, vt.area, tm.sub_equipment, tm.description, tm.eng_unit
FROM historian_meta.v_report_template_tags vt
LEFT JOIN historian_meta.tag_master tm ON vt.tag_id = tm.tag_id
WHERE vt.plant = 'PLANT_001' AND vt.area = 'TURBINE'
  AND vt.tag_id IN (
    SELECT DISTINCT tag_id 
    FROM historian_raw.v_daily_hourly_agg
    WHERE local_date = '2026-05-18'
  )
LIMIT 5;
"""

print("=== Testing Template Query ===")
cursor.execute(query)
rows = cursor.fetchall()

print(f"Found {len(rows)} rows\n")
for row in rows:
    s_no, tag_id, display_label, group_name, parameter_unit, plant, area, sub_equipment, description, eng_unit = row
    print(f"Tag: {tag_id}")
    print(f"  display_label: '{display_label}'")
    print(f"  group_name: '{group_name}'")
    print(f"  parameter_unit: '{parameter_unit}'")
    print(f"  sub_equipment: '{sub_equipment}'")
    print(f"  description: '{description}'")
    print(f"  eng_unit: '{eng_unit}'")
    print()

# Check tag_master directly
print("\n=== Checking tag_master directly ===")
cursor.execute("""
SELECT tag_id, tag_name, description, sub_equipment, eng_unit, plant, area
FROM historian_meta.tag_master
WHERE plant = 'PLANT_001' AND area = 'TURBINE'
LIMIT 5;
""")

rows = cursor.fetchall()
print(f"Found {len(rows)} rows in tag_master\n")
for row in rows:
    print(f"Tag: {row[0]}")
    print(f"  tag_name: '{row[1]}'")
    print(f"  description: '{row[2]}'")
    print(f"  sub_equipment: '{row[3]}'")
    print(f"  eng_unit: '{row[4]}'")
    print(f"  plant: '{row[5]}', area: '{row[6]}'")
    print()

# Check what plants/areas have data on 2026-05-18
print("\n=== Plants/Areas with data on 2026-05-18 ===")
cursor.execute("""
SELECT DISTINCT tm.plant, tm.area, COUNT(*) as tag_count
FROM historian_raw.v_daily_hourly_agg v
JOIN historian_meta.tag_master tm ON v.tag_id = tm.tag_id
WHERE v.local_date = '2026-05-18'
GROUP BY tm.plant, tm.area
ORDER BY tm.plant, tm.area;
""")

for plant, area, count in cursor.fetchall():
    print(f"Plant: '{plant}' | Area: '{area}' | Tags: {count}")

cursor.close()
conn.close()
