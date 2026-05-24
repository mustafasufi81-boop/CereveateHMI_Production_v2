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
print("CREATING AUTO-POPULATE TRIGGER FOR report_templates")
print("=" * 80)

# Drop existing trigger if exists
print("\n[1] Dropping old trigger (if exists)...")
cursor.execute("""
DROP TRIGGER IF EXISTS trg_auto_add_tag_to_report_template ON historian_meta.tag_master;
DROP FUNCTION IF EXISTS historian_meta.fn_auto_add_tag_to_report_template();
""")
conn.commit()
print("✅ Old trigger removed")

# Create function
print("\n[2] Creating trigger function...")
cursor.execute("""
CREATE OR REPLACE FUNCTION historian_meta.fn_auto_add_tag_to_report_template()
RETURNS TRIGGER AS $$
DECLARE
    next_sno INTEGER;
BEGIN
    -- Only add if report_flag is TRUE and doesn't already exist in report_templates
    IF NEW.report_flag = TRUE THEN
        -- Check if already exists
        IF NOT EXISTS (
            SELECT 1 FROM historian_meta.report_templates 
            WHERE tag_id = NEW.tag_id AND report_type = 'DAILY'
        ) THEN
            -- Get next s_no
            SELECT COALESCE(MAX(s_no), 0) + 1 INTO next_sno
            FROM historian_meta.report_templates;
            
            -- Insert into report_templates
            INSERT INTO historian_meta.report_templates (report_type, s_no, tag_id, enabled)
            VALUES ('DAILY', next_sno, NEW.tag_id, TRUE);
            
            RAISE NOTICE 'Auto-added tag % to report_templates (s_no=%)', NEW.tag_id, next_sno;
        END IF;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""")
conn.commit()
print("✅ Function created")

# Create trigger
print("\n[3] Creating trigger on tag_master table...")
cursor.execute("""
CREATE TRIGGER trg_auto_add_tag_to_report_template
AFTER INSERT OR UPDATE OF report_flag ON historian_meta.tag_master
FOR EACH ROW
EXECUTE FUNCTION historian_meta.fn_auto_add_tag_to_report_template();
""")
conn.commit()
print("✅ Trigger created")

print("\n" + "=" * 80)
print("✅ AUTO-POPULATE MECHANISM INSTALLED!")
print("=" * 80)
print("\nHow it works:")
print("1. When a tag is inserted into tag_master with report_flag = TRUE")
print("2. OR when report_flag is updated to TRUE")
print("3. The trigger automatically adds it to report_templates table")
print("4. The tag will appear in v_report_template_tags view immediately")

# Now populate existing tags that have report_flag = TRUE but aren't in report_templates
print("\n" + "=" * 80)
print("POPULATING EXISTING TAGS (ONE-TIME SYNC)")
print("=" * 80)

cursor.execute("""
SELECT COUNT(*) FROM historian_meta.tag_master
WHERE report_flag = TRUE
  AND tag_id NOT IN (SELECT tag_id FROM historian_meta.report_templates WHERE report_type = 'DAILY');
""")

missing_count = cursor.fetchone()[0]
print(f"\nFound {missing_count} tags with report_flag=TRUE not in report_templates")

if missing_count > 0:
    cursor.execute("""
    INSERT INTO historian_meta.report_templates (report_type, s_no, tag_id, enabled)
    SELECT 
        'DAILY' as report_type,
        ROW_NUMBER() OVER (ORDER BY tag_id) + (SELECT COALESCE(MAX(s_no), 0) FROM historian_meta.report_templates) as s_no,
        tag_id,
        TRUE as enabled
    FROM historian_meta.tag_master
    WHERE report_flag = TRUE
      AND tag_id NOT IN (SELECT tag_id FROM historian_meta.report_templates WHERE report_type = 'DAILY');
    """)
    conn.commit()
    print(f"✅ Added {cursor.rowcount} tags to report_templates")
else:
    print("✅ All report_flag=TRUE tags already in report_templates")

# Check FTP-1/POTLINE specifically
cursor.execute("""
SELECT COUNT(*) FROM historian_meta.v_report_template_tags
WHERE plant = 'FTP-1' AND area = 'POTLINE';
""")
ftp_count = cursor.fetchone()[0]

print(f"\n{'=' * 80}")
print(f"FTP-1/POTLINE tags in v_report_template_tags: {ftp_count}")

if ftp_count == 0:
    print("\n⚠️ FTP-1/POTLINE tags still missing!")
    print("Checking if report_flag is set to TRUE for those tags...\n")
    
    cursor.execute("""
    SELECT tag_id, report_flag 
    FROM historian_meta.tag_master 
    WHERE plant = 'FTP-1' AND area = 'POTLINE'
    LIMIT 5;
    """)
    
    for tag_id, report_flag in cursor.fetchall():
        print(f"  {tag_id}: report_flag = {report_flag}")
    
    print("\nIf report_flag is FALSE or NULL, run this to enable:")
    print("  UPDATE historian_meta.tag_master")
    print("  SET report_flag = TRUE")
    print("  WHERE plant = 'FTP-1' AND area = 'POTLINE';")
else:
    print(f"✅ All good! Template query will work now.")

cursor.close()
conn.close()

print("=" * 80)
