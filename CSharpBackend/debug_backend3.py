import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="Automation_DB",
    user="cereveate",
    password="cereveate@222"
)

cursor = conn.cursor()

# Check the tags from your screenshot (PY1103A, TY1101A, etc.)
print("=== Checking Tags from Screenshot ===")
cursor.execute("""
SELECT tag_id, tag_name, description, sub_equipment, eng_unit, plant, area
FROM historian_meta.tag_master
WHERE tag_id IN ('PY1103A', 'TY1101A', 'PY1101A', 'TY1103B')
ORDER BY tag_id;
""")

rows = cursor.fetchall()
if len(rows) == 0:
    print("❌ Tags not found in database!")
else:
    print(f"Found {len(rows)} tags:\n")
    for row in rows:
        tag_id, tag_name, description, sub_equipment, eng_unit, plant, area = row
        print(f"Tag: {tag_id}")
        print(f"  description: '{description}'")
        print(f"  sub_equipment: '{sub_equipment}'")
        print(f"  eng_unit: '{eng_unit}'")
        print(f"  plant: '{plant}', area: '{area}'")
        
        # Check for string 'None'
        if description == 'None' or description is None:
            print(f"  ⚠️ description is 'None' string or NULL")
        if sub_equipment == 'None' or sub_equipment is None:
            print(f"  ⚠️ sub_equipment is 'None' string or NULL")
        if eng_unit == 'None' or eng_unit is None:
            print(f"  ⚠️ eng_unit is 'None' string or NULL")
        print()

# Check what plant/area these tags belong to
print("\n=== Checking which plant/area has data on 2026-05-18 ===")
cursor.execute("""
SELECT tm.plant, tm.area, COUNT(*) as tag_count,
       COUNT(CASE WHEN tm.description != 'None' AND tm.description IS NOT NULL THEN 1 END) as with_desc,
       COUNT(CASE WHEN tm.sub_equipment != 'None' AND tm.sub_equipment IS NOT NULL THEN 1 END) as with_sub,
       COUNT(CASE WHEN tm.eng_unit != 'None' AND tm.eng_unit IS NOT NULL THEN 1 END) as with_unit
FROM historian_raw.v_daily_hourly_agg v
JOIN historian_meta.tag_master tm ON v.tag_id = tm.tag_id
WHERE v.local_date = '2026-05-18'
GROUP BY tm.plant, tm.area
ORDER BY tm.plant, tm.area;
""")

print("Plant | Area | Total Tags | With Description | With Sub Equipment | With Unit")
print("-" * 90)
for plant, area, total, with_desc, with_sub, with_unit in cursor.fetchall():
    print(f"{plant:15} | {area:15} | {total:10} | {with_desc:16} | {with_sub:18} | {with_unit:9}")

cursor.close()
conn.close()
