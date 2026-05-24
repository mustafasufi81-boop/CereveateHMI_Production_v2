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
print("DEBUGGING: Why didn't the trigger fire?")
print("=" * 80)

# Check the test tag
print("\n[1] Checking TEST_TAG_001 in tag_master...")
cursor.execute("""
SELECT tag_id, tag_name, report_flag, plant, area
FROM historian_meta.tag_master
WHERE tag_id = 'TEST_TAG_001';
""")

result = cursor.fetchone()
if result:
    print(f"✅ Found: tag_id={result[0]}, report_flag={result[2]}, plant={result[3]}, area={result[4]}")
else:
    print("❌ NOT found!")

# Check trigger exists
print("\n[2] Verifying trigger exists...")
cursor.execute("""
SELECT tgname, tgenabled, tgtype
FROM pg_trigger t
JOIN pg_class c ON t.tgrelid = c.oid
WHERE c.relname = 'tag_master'
  AND tgname = 'trg_auto_add_tag_to_report_template';
""")

trigger = cursor.fetchone()
if trigger:
    print(f"✅ Trigger exists: {trigger[0]}, enabled={trigger[1]=='O'}")
else:
    print("❌ Trigger NOT found!")

# Manual trigger test - update report_flag to force trigger
print("\n[3] Manually firing trigger by updating report_flag...")
cursor.execute("""
UPDATE historian_meta.tag_master
SET report_flag = FALSE
WHERE tag_id = 'TEST_TAG_001';
""")
conn.commit()

cursor.execute("""
UPDATE historian_meta.tag_master
SET report_flag = TRUE
WHERE tag_id = 'TEST_TAG_001';
""")
conn.commit()
print("✅ Updated report_flag FALSE → TRUE")

# Check if it's now in report_templates
cursor.execute("""
SELECT COUNT(*) FROM historian_meta.report_templates
WHERE tag_id = 'TEST_TAG_001';
""")

count = cursor.fetchone()[0]
print(f"\n[4] Checking report_templates after manual trigger...")
print(f"   Count: {count}")

if count > 0:
    print("✅ SUCCESS! Trigger worked on UPDATE")
    cursor.execute("""
    SELECT report_type, s_no, tag_id, enabled
    FROM historian_meta.report_templates
    WHERE tag_id = 'TEST_TAG_001';
    """)
    row = cursor.fetchone()
    print(f"   report_type={row[0]}, s_no={row[1]}, tag_id={row[2]}, enabled={row[3]}")
else:
    print("❌ STILL NOT WORKING - trigger has a bug")

cursor.close()
conn.close()

print("\n" + "=" * 80)
print("DIAGNOSIS COMPLETE")
print("=" * 80)
