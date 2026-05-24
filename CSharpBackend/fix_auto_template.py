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
print("ADDING report_flag COLUMN + AUTO-POPULATE MECHANISM")
print("=" * 80)

# Check if report_flag exists
cursor.execute("""
SELECT column_name 
FROM information_schema.columns 
WHERE table_schema = 'historian_meta' 
  AND table_name = 'tag_master' 
  AND column_name = 'report_flag';
""")

if cursor.fetchone():
    print("\n✅ report_flag column already exists")
else:
    print("\n[1] Adding report_flag column to tag_master...")
    cursor.execute("""
    ALTER TABLE historian_meta.tag_master 
    ADD COLUMN IF NOT EXISTS report_flag BOOLEAN DEFAULT TRUE;
    """)
    conn.commit()
    print("✅ Column added (default TRUE)")

# Set report_flag = TRUE for all existing tags
print("\n[2] Setting report_flag = TRUE for all existing tags...")
cursor.execute("""
UPDATE historian_meta.tag_master 
SET report_flag = TRUE 
WHERE report_flag IS NULL;
""")
conn.commit()
print(f"✅ Updated {cursor.rowcount} tags")

# Drop existing trigger if exists
print("\n[3] Creating auto-populate trigger...")
cursor.execute("""
DROP TRIGGER IF EXISTS trg_auto_add_tag_to_report_template ON historian_meta.tag_master;
DROP FUNCTION IF EXISTS historian_meta.fn_auto_add_tag_to_report_template();
""")

# Create function
cursor.execute("""
CREATE OR REPLACE FUNCTION historian_meta.fn_auto_add_tag_to_report_template()
RETURNS TRIGGER AS $$
DECLARE
    next_sno INTEGER;
BEGIN
    -- Only add if report_flag is TRUE and doesn't already exist
    IF NEW.report_flag = TRUE THEN
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
        END IF;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_auto_add_tag_to_report_template
AFTER INSERT OR UPDATE OF report_flag ON historian_meta.tag_master
FOR EACH ROW
EXECUTE FUNCTION historian_meta.fn_auto_add_tag_to_report_template();
""")
conn.commit()
print("✅ Trigger created")

# Sync existing tags
print("\n[4] Syncing existing tags with report_flag=TRUE...")
cursor.execute("""
INSERT INTO historian_meta.report_templates (report_type, s_no, tag_id, enabled)
SELECT 
    'DAILY' as report_type,
    ROW_NUMBER() OVER (ORDER BY tag_id) + (SELECT COALESCE(MAX(s_no), 0) FROM historian_meta.report_templates) as s_no,
    tag_id,
    TRUE as enabled
FROM historian_meta.tag_master
WHERE report_flag = TRUE
  AND tag_id NOT IN (SELECT tag_id FROM historian_meta.report_templates WHERE report_type = 'DAILY')
ON CONFLICT DO NOTHING;
""")
conn.commit()
print(f"✅ Added {cursor.rowcount} tags to report_templates")

# Verify FTP-1/POTLINE
cursor.execute("""
SELECT COUNT(*) FROM historian_meta.v_report_template_tags
WHERE plant = 'FTP-1' AND area = 'POTLINE';
""")
ftp_count = cursor.fetchone()[0]

print(f"\n{'=' * 80}")
print(f"✅ COMPLETE! FTP-1/POTLINE tags in template: {ftp_count}")
print("=" * 80)

print("\n📋 How it works now:")
print("  1. When you INSERT a new tag → report_flag defaults to TRUE")
print("  2. Trigger automatically adds it to report_templates")
print("  3. Tag appears in reports immediately")
print("  4. To exclude a tag from reports: UPDATE tag_master SET report_flag = FALSE")

cursor.close()
conn.close()
