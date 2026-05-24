import psycopg2
from datetime import datetime

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="Automation_DB",
    user="cereveate",
    password="cereveate@222"
)

cursor = conn.cursor()

print("=" * 80)
print("STEP 3: TEST TRIGGER - Insert NEW tag with ALL columns properly filled")
print("=" * 80)

# Get column structure from tag_master
print("\n[Step 3a] Checking tag_master column structure...")
cursor.execute("""
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'historian_meta' 
  AND table_name = 'tag_master'
ORDER BY ordinal_position;
""")

print("\nColumns in tag_master:")
columns = []
for col_name, data_type, nullable, default in cursor.fetchall():
    columns.append(col_name)
    print(f"  {col_name:30} | {data_type:20} | nullable={nullable:3} | default={default}")

# Prepare test tag data (matching actual column names from tag_master)
test_tag = {
    'tag_id': 'TEST_TAG_001',
    'tag_name': 'TEST_TAG_001',  # Same as tag_id as you specified
    'description': 'Test Tag for Trigger Validation',
    'plant': 'FTP-1',
    'area': 'POTLINE',
    'equipment': 'TEST EQUIPMENT',
    'sub_equipment': 'TEST SUB EQUIPMENT',
    'components': 'TEST COMPONENT',
    'eng_unit': 'KPA',
    'data_type': 'double',
    'report_flag': True,  # THIS SHOULD TRIGGER auto-add
    'enabled': True,
    'alarm_high_high_threshold': 100.0,
    'alarm_high_threshold': 90.0,
    'alarm_low_threshold': 10.0,
    'alarm_low_low_threshold': 5.0,
    'plc_port': 502,
    'plc_protocol': 'Rockwell'
}

print("\n" + "=" * 80)
print("[Step 3b] Test tag data prepared:")
print("=" * 80)
for key, value in test_tag.items():
    print(f"  {key:30} = {value}")

# Check if test tag already exists
cursor.execute("SELECT COUNT(*) FROM historian_meta.tag_master WHERE tag_id = %s;", (test_tag['tag_id'],))
if cursor.fetchone()[0] > 0:
    print(f"\n⚠️ Tag {test_tag['tag_id']} already exists. Deleting first...")
    cursor.execute("DELETE FROM historian_meta.tag_master WHERE tag_id = %s;", (test_tag['tag_id'],))
    cursor.execute("DELETE FROM historian_meta.report_templates WHERE tag_id = %s;", (test_tag['tag_id'],))
    conn.commit()
    print("✅ Cleaned up existing test tag")

# Count before insert
cursor.execute("SELECT COUNT(*) FROM historian_meta.report_templates;")
before_count = cursor.fetchone()[0]
print(f"\n[Step 3c] report_templates count BEFORE insert: {before_count}")

# Insert the test tag
print("\n[Step 3d] Inserting test tag into tag_master...")
print("   ⚡ Trigger should auto-add to report_templates...")

cursor.execute("""
INSERT INTO historian_meta.tag_master (
    tag_id, tag_name, description, plant, area, equipment, sub_equipment, 
    components, eng_unit, data_type, report_flag, enabled,
    alarm_high_high_threshold, alarm_high_threshold, alarm_low_threshold, alarm_low_low_threshold,
    plc_port, plc_protocol
) VALUES (
    %(tag_id)s, %(tag_name)s, %(description)s, %(plant)s, %(area)s, 
    %(equipment)s, %(sub_equipment)s, %(components)s, %(eng_unit)s, 
    %(data_type)s, %(report_flag)s, %(enabled)s,
    %(alarm_high_high_threshold)s, %(alarm_high_threshold)s, %(alarm_low_threshold)s, %(alarm_low_low_threshold)s,
    %(plc_port)s, %(plc_protocol)s
);
""", test_tag)

conn.commit()
print("✅ Tag inserted into tag_master")

# Count after insert
cursor.execute("SELECT COUNT(*) FROM historian_meta.report_templates;")
after_count = cursor.fetchone()[0]
print(f"\n[Step 3e] report_templates count AFTER insert: {after_count}")

if after_count > before_count:
    print(f"✅ SUCCESS! Trigger added {after_count - before_count} row(s)")
else:
    print("❌ FAILED! Trigger did NOT add row")

# Verify in report_templates
print("\n[Step 3f] Checking if tag exists in report_templates...")
cursor.execute("""
SELECT report_type, s_no, tag_id, enabled, created_at
FROM historian_meta.report_templates
WHERE tag_id = %s;
""", (test_tag['tag_id'],))

result = cursor.fetchone()
if result:
    print("✅ Found in report_templates:")
    print(f"   report_type: {result[0]}")
    print(f"   s_no: {result[1]}")
    print(f"   tag_id: {result[2]}")
    print(f"   enabled: {result[3]}")
    print(f"   created_at: {result[4]}")
else:
    print("❌ NOT found in report_templates!")

# Verify in view
print("\n[Step 3g] Checking if tag appears in v_report_template_tags view...")
cursor.execute("""
SELECT tag_id, display_label, group_name, parameter_unit, plant, area
FROM historian_meta.v_report_template_tags
WHERE tag_id = %s;
""", (test_tag['tag_id'],))

view_result = cursor.fetchone()
if view_result:
    print("✅ Found in v_report_template_tags view:")
    print(f"   tag_id: {view_result[0]}")
    print(f"   display_label: {view_result[1]}")
    print(f"   group_name: {view_result[2]}")
    print(f"   parameter_unit: {view_result[3]}")
    print(f"   plant: {view_result[4]}")
    print(f"   area: {view_result[5]}")
else:
    print("❌ NOT found in view!")

# Count total FTP-1/POTLINE tags
cursor.execute("""
SELECT COUNT(*) FROM historian_meta.v_report_template_tags
WHERE plant = 'FTP-1' AND area = 'POTLINE';
""")
total = cursor.fetchone()[0]

print("\n" + "=" * 80)
print(f"✅ STEP 3 COMPLETE - Trigger test {'PASSED' if result and view_result else 'FAILED'}")
print("=" * 80)
print(f"Total FTP-1/POTLINE tags in view: {total} (should be 6)")
print("\nIf test passed, trigger is working correctly!")
print("You can now insert real tags and they will auto-populate.")

cursor.close()
conn.close()
