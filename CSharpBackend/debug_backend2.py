import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="Automation_DB",
    user="cereveate",
    password="cereveate@222"
)

cursor = conn.cursor()

# Test with Plant1/Area1 (148 tags with data)
print("=== Testing with Plant1/Area1 ===")
query = """
SELECT vt.s_no, vt.tag_id, vt.display_label, vt.group_name, vt.parameter_unit,
       vt.plant, vt.area, tm.sub_equipment, tm.description, tm.eng_unit
FROM historian_meta.v_report_template_tags vt
LEFT JOIN historian_meta.tag_master tm ON vt.tag_id = tm.tag_id
WHERE vt.plant = 'Plant1' AND vt.area = 'Area1'
  AND vt.tag_id IN (
    SELECT DISTINCT tag_id 
    FROM historian_raw.v_daily_hourly_agg
    WHERE local_date = '2026-05-18'
  )
LIMIT 5;
"""

cursor.execute(query)
rows = cursor.fetchall()

if len(rows) == 0:
    print("⚠️ No rows from template query - checking tag_master directly")
    
    # Check tag_master for Plant1/Area1
    cursor.execute("""
    SELECT tag_id, tag_name, description, sub_equipment, eng_unit, plant, area
    FROM historian_meta.tag_master
    WHERE tag_id IN (
        SELECT DISTINCT tag_id 
        FROM historian_raw.v_daily_hourly_agg
        WHERE local_date = '2026-05-18'
    )
    LIMIT 5;
    """)
    
    tm_rows = cursor.fetchall()
    print(f"\nFound {len(tm_rows)} rows directly from tag_master:\n")
    for row in tm_rows:
        tag_id, tag_name, description, sub_equipment, eng_unit, plant, area = row
        print(f"Tag: {tag_id}")
        print(f"  tag_name: '{tag_name}'")
        print(f"  description: '{description}'")
        print(f"  sub_equipment: '{sub_equipment}'")
        print(f"  eng_unit: '{eng_unit}'")
        print(f"  plant: '{plant}', area: '{area}'")
        
        # Check if fields are empty
        if not sub_equipment:
            print(f"  ❌ sub_equipment is NULL/empty")
        if not description:
            print(f"  ❌ description is NULL/empty")
        if not eng_unit:
            print(f"  ❌ eng_unit is NULL/empty")
        print()
else:
    print(f"Found {len(rows)} rows from template query:\n")
    for row in rows:
        s_no, tag_id, display_label, group_name, parameter_unit, plant, area, sub_equipment, description, eng_unit = row
        print(f"Tag: {tag_id}")
        print(f"  display_label: '{display_label}'")
        print(f"  sub_equipment: '{sub_equipment}'")
        print(f"  description: '{description}'")
        print(f"  eng_unit: '{eng_unit}'")
        print()

cursor.close()
conn.close()
