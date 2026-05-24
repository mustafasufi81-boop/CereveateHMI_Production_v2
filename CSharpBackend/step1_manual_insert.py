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
print("STEP 1: MANUAL INSERT - Adding FTP-1/POTLINE tags to report_templates")
print("=" * 80)

# Get FTP-1/POTLINE tags that exist in tag_master
# We'll add these manually first, then test trigger with new ones
tags_to_add = [
    'PY1103A',  # ROOTS FAN OUTLET OF PRESSURE #1
    'PY1103B',  # ROOTS FAN OUTLET OF PRESSURE #2
    'PY1101A',  # FILTER INLET PRESSURE 1#
    'PY1101B',  # FILTER INLET PRESSURE 2#
    # TY1101A will be saved for trigger test
]

print(f"\n📋 Tags from your screenshot to add: {len(tags_to_add)}")
for tag in tags_to_add:
    print(f"  - {tag}")

# Get next available s_no
cursor.execute("SELECT COALESCE(MAX(s_no), 0) FROM historian_meta.report_templates;")
next_s_no = cursor.fetchone()[0]
print(f"\nNext available s_no: {next_s_no}")

# Check current count in report_templates
cursor.execute("SELECT COUNT(*) FROM historian_meta.report_templates;")
before_count = cursor.fetchone()[0]
print(f"Current report_templates count: {before_count}")

# Insert each tag
print(f"\n{'=' * 80}")
print("INSERTING TAGS...")
print("=" * 80)

inserted = 0
for tag_id in tags_to_add:
    next_s_no += 1
    
    # Check if tag exists in tag_master
    cursor.execute("""
    SELECT tag_id, tag_name, plant, area 
    FROM historian_meta.tag_master 
    WHERE tag_id = %s;
    """, (tag_id,))
    
    tag_info = cursor.fetchone()
    if not tag_info:
        print(f"\n❌ {tag_id} - NOT FOUND in tag_master! Skipping...")
        continue
    
    _, tag_name, plant, area = tag_info
    print(f"\n✅ {tag_id} found in tag_master")
    print(f"   tag_name: {tag_name}")
    print(f"   plant: {plant}, area: {area}")
    
    # Check if already in report_templates
    cursor.execute("""
    SELECT COUNT(*) FROM historian_meta.report_templates 
    WHERE tag_id = %s AND report_type = 'DAILY';
    """, (tag_id,))
    
    if cursor.fetchone()[0] > 0:
        print(f"   ⏭️  Already in report_templates, skipping...")
        continue
    
    # Insert
    cursor.execute("""
    INSERT INTO historian_meta.report_templates (report_type, s_no, tag_id, enabled)
    VALUES ('DAILY', %s, %s, TRUE);
    """, (next_s_no, tag_id))
    
    print(f"   ✅ INSERTED into report_templates (s_no={next_s_no})")
    inserted += 1

conn.commit()

# Verify
cursor.execute("SELECT COUNT(*) FROM historian_meta.report_templates;")
after_count = cursor.fetchone()[0]

print(f"\n{'=' * 80}")
print("VERIFICATION")
print("=" * 80)
print(f"Before: {before_count} tags")
print(f"After:  {after_count} tags")
print(f"Inserted: {inserted} tags")

# Check view
cursor.execute("""
SELECT COUNT(*) FROM historian_meta.v_report_template_tags
WHERE plant = 'FTP-1' AND area = 'POTLINE';
""")
view_count = cursor.fetchone()[0]
print(f"\nv_report_template_tags (FTP-1/POTLINE): {view_count} tags")

if view_count > 0:
    print("\n✅ SUCCESS! Tags now visible in view")
    cursor.execute("""
    SELECT tag_id, display_label, group_name, parameter_unit
    FROM historian_meta.v_report_template_tags
    WHERE plant = 'FTP-1' AND area = 'POTLINE'
    ORDER BY tag_id;
    """)
    
    print("\nTags in view:")
    for tag_id, display_label, group_name, parameter_unit in cursor.fetchall():
        print(f"  - {tag_id}: {display_label} ({group_name}) [{parameter_unit}]")
else:
    print("\n⚠️ No tags in view yet")

cursor.close()
conn.close()

print("\n" + "=" * 80)
print("✅ STEP 1 COMPLETE - Manual insert done")
print("=" * 80)
