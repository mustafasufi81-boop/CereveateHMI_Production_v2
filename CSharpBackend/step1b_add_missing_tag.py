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
print("STEP 1b: Adding the missing TY1101A tag")
print("=" * 80)

# Add the missing tag
tag_id = 'TY1101A'  # 1# ID FAN FRONT BEARING TEMPERATURE

print(f"\n📋 Adding tag: {tag_id}")

# Check if exists in tag_master
cursor.execute("""
SELECT tag_id, tag_name, sub_equipment, description, eng_unit, plant, area 
FROM historian_meta.tag_master 
WHERE tag_id = %s;
""", (tag_id,))

tag_info = cursor.fetchone()
if not tag_info:
    print(f"❌ {tag_id} NOT FOUND in tag_master!")
else:
    _, tag_name, sub_eq, desc, unit, plant, area = tag_info
    print(f"\n✅ Found in tag_master:")
    print(f"   tag_name: {tag_name}")
    print(f"   sub_equipment: {sub_eq}")
    print(f"   description: {desc}")
    print(f"   eng_unit: {unit}")
    print(f"   plant: {plant}, area: {area}")
    
    # Check if already in report_templates
    cursor.execute("""
    SELECT COUNT(*) FROM historian_meta.report_templates 
    WHERE tag_id = %s AND report_type = 'DAILY';
    """, (tag_id,))
    
    if cursor.fetchone()[0] > 0:
        print(f"\n⏭️  Already in report_templates")
    else:
        # Get next s_no
        cursor.execute("SELECT COALESCE(MAX(s_no), 0) + 1 FROM historian_meta.report_templates;")
        next_s_no = cursor.fetchone()[0]
        
        # Insert
        cursor.execute("""
        INSERT INTO historian_meta.report_templates (report_type, s_no, tag_id, enabled)
        VALUES ('DAILY', %s, %s, TRUE);
        """, (next_s_no, tag_id))
        
        conn.commit()
        print(f"\n✅ INSERTED into report_templates (s_no={next_s_no})")

# Verify in view
cursor.execute("""
SELECT COUNT(*) FROM historian_meta.v_report_template_tags
WHERE plant = 'FTP-1' AND area = 'POTLINE';
""")
view_count = cursor.fetchone()[0]

print(f"\n{'=' * 80}")
print(f"Total FTP-1/POTLINE tags in view: {view_count}")
print("=" * 80)

cursor.execute("""
SELECT tag_id, display_label, group_name, parameter_unit
FROM historian_meta.v_report_template_tags
WHERE plant = 'FTP-1' AND area = 'POTLINE'
ORDER BY tag_id;
""")

print("\nAll tags in view:")
for tag_id, display_label, group_name, parameter_unit in cursor.fetchall():
    print(f"  - {tag_id}: {display_label} ({group_name}) [{parameter_unit}]")

cursor.close()
conn.close()

print("\n" + "=" * 80)
print("✅ STEP 1b COMPLETE - All existing tags now in view")
print("=" * 80)
