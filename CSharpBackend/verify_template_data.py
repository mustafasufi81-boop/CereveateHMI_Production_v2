import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="Automation_DB",
    user="cereveate",
    password="cereveate@222"
)

cursor = conn.cursor()

print("=" * 80)
print("VERIFY FTP-1/POTLINE TEMPLATE DATA")
print("=" * 80)

# Check view data
cursor.execute("""
SELECT 
    s_no,
    tag_id,
    plant,
    area,
    equipment,
    sub_equipment,
    description,
    eng_unit
FROM historian_meta.v_report_template_tags
WHERE plant = 'FTP-1' AND area = 'POTLINE'
ORDER BY s_no;
""")

rows = cursor.fetchall()

print(f"\n✅ Found {len(rows)} tags in view")
print("\nTag Details:")
print("-" * 150)
print(f"{'S.No':<6} {'Tag ID':<15} {'Plant':<8} {'Area':<10} {'Equipment':<12} {'Sub Equip':<12} {'Description':<30} {'Unit':<10}")
print("-" * 150)

for row in rows:
    s_no, tag_id, plant, area, equipment, sub_equip, desc, unit = row
    
    # Clean None values
    sub_equip = '' if sub_equip is None or sub_equip == 'None' else sub_equip
    desc = '' if desc is None or desc == 'None' else desc
    unit = '' if unit is None or unit == 'None' else unit
    
    print(f"{s_no:<6} {tag_id:<15} {plant:<8} {area:<10} {equipment:<12} {sub_equip:<12} {desc:<30} {unit:<10}")

cursor.close()
conn.close()
