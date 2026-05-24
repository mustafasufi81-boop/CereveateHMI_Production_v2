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
print("FIXING TRIGGER - Recreate with proper AFTER INSERT trigger")
print("=" * 80)

# Drop and recreate trigger (trigger might not fire on INSERT with UPDATE OF syntax)
print("\n[1] Dropping existing trigger...")
cursor.execute("""
DROP TRIGGER IF EXISTS trg_auto_add_tag_to_report_template ON historian_meta.tag_master CASCADE;
""")
conn.commit()
print("✅ Dropped")

# Create trigger that fires on BOTH INSERT and UPDATE
print("\n[2] Creating trigger (fires on INSERT and UPDATE)...")
cursor.execute("""
CREATE TRIGGER trg_auto_add_tag_to_report_template
    AFTER INSERT OR UPDATE
    ON historian_meta.tag_master
    FOR EACH ROW
    EXECUTE FUNCTION historian_meta.fn_auto_add_tag_to_report_template();
""")
conn.commit()
print("✅ Trigger recreated (now fires on ALL inserts and updates)")

# Verify
cursor.execute("""
SELECT 
    tgname AS trigger_name,
    tgenabled AS enabled,
    pg_get_triggerdef(oid) as trigger_def
FROM pg_trigger
WHERE tgname = 'trg_auto_add_tag_to_report_template';
""")

result = cursor.fetchone()
if result:
    print(f"\n✅ Trigger verified: {result[0]}")
    print(f"   Enabled: {result[1] == 'O'}")
    print(f"\n   Definition:")
    print(f"   {result[2]}")
else:
    print("❌ Trigger not found!")

# Clean up test tag to test fresh insert
print("\n[3] Cleaning up test tag to test fresh insert...")
cursor.execute("DELETE FROM historian_meta.tag_master WHERE tag_id = 'TEST_TAG_002';")
cursor.execute("DELETE FROM historian_meta.report_templates WHERE tag_id = 'TEST_TAG_002';")
conn.commit()

# Test with new tag
print("\n[4] Testing trigger with fresh INSERT...")
cursor.execute("""
INSERT INTO historian_meta.tag_master (
    tag_id, tag_name, plant, area, equipment, data_type, report_flag
) VALUES (
    'TEST_TAG_002', 'TEST_TAG_002', 'FTP-1', 'POTLINE', 'TEST', 'double', TRUE
);
""")
conn.commit()
print("✅ Inserted TEST_TAG_002")

# Check if trigger added it to report_templates
cursor.execute("SELECT COUNT(*) FROM historian_meta.report_templates WHERE tag_id = 'TEST_TAG_002';")
count = cursor.fetchone()[0]

print(f"\n[5] Checking report_templates...")
print(f"   Count for TEST_TAG_002: {count}")

if count > 0:
    print("\n✅✅✅ SUCCESS! Trigger is NOW working correctly!")
    cursor.execute("""
    SELECT report_type, s_no, tag_id, enabled
    FROM historian_meta.report_templates
    WHERE tag_id = 'TEST_TAG_002';
    """)
    row = cursor.fetchone()
    print(f"   {row}")
else:
    print("\n❌ STILL NOT WORKING")

cursor.close()
conn.close()

print("\n" + "=" * 80)
print("TRIGGER FIX COMPLETE")
print("=" * 80)
