import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="Automation_DB",
    user="cereveate",
    password="cereveate@222"
)

# Enable notice/warning output
conn.set_session(autocommit=True)
import psycopg2.extensions
psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)

cursor = conn.cursor()

print("=" * 80)
print("FINAL FIX - Simplify trigger and add logging")
print("=" * 80)

# Recreate function with better error handling and logging
print("\n[1] Creating simplified trigger function with logging...")
cursor.execute("""
DROP FUNCTION IF EXISTS historian_meta.fn_auto_add_tag_to_report_template() CASCADE;

CREATE OR REPLACE FUNCTION historian_meta.fn_auto_add_tag_to_report_template()
RETURNS TRIGGER AS $$
DECLARE
    next_sno INTEGER;
BEGIN
    RAISE NOTICE 'TRIGGER FIRED for tag_id=%', NEW.tag_id;
    RAISE NOTICE 'report_flag=%', NEW.report_flag;
    
    -- Check report_flag
    IF NEW.report_flag IS NULL THEN
        RAISE NOTICE 'report_flag is NULL, skipping';
        RETURN NEW;
    END IF;
    
    IF NEW.report_flag != TRUE THEN
        RAISE NOTICE 'report_flag is FALSE, skipping';
        RETURN NEW;
    END IF;
    
    -- Check if already exists
    IF EXISTS (SELECT 1 FROM historian_meta.report_templates WHERE tag_id = NEW.tag_id AND report_type = 'DAILY') THEN
        RAISE NOTICE 'Tag already in report_templates, skipping';
        RETURN NEW;
    END IF;
    
    -- Get next s_no
    SELECT COALESCE(MAX(s_no), 0) + 1 INTO next_sno
    FROM historian_meta.report_templates;
    
    RAISE NOTICE 'Inserting with s_no=%', next_sno;
    
    -- Insert
    INSERT INTO historian_meta.report_templates (report_type, s_no, tag_id, enabled, created_at)
    VALUES ('DAILY', next_sno, NEW.tag_id, TRUE, CURRENT_TIMESTAMP);
    
    RAISE NOTICE 'SUCCESS! Inserted tag_id=% with s_no=%', NEW.tag_id, next_sno;
    
    RETURN NEW;
EXCEPTION
    WHEN OTHERS THEN
        RAISE WARNING 'ERROR: % - %', SQLSTATE, SQLERRM;
        RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""")
print("✅ Function created with detailed logging")

# Recreate trigger
cursor.execute("""
DROP TRIGGER IF EXISTS trg_auto_add_tag_to_report_template ON historian_meta.tag_master;

CREATE TRIGGER trg_auto_add_tag_to_report_template
    AFTER INSERT OR UPDATE
    ON historian_meta.tag_master
    FOR EACH ROW
    EXECUTE FUNCTION historian_meta.fn_auto_add_tag_to_report_template();
""")
print("✅ Trigger recreated")

# Test with notices visible
print("\n[2] Testing with TEST_TAG_003 (notices should appear)...")
cursor.execute("DELETE FROM historian_meta.tag_master WHERE tag_id = 'TEST_TAG_003';")
cursor.execute("DELETE FROM historian_meta.report_templates WHERE tag_id = 'TEST_TAG_003';")

cursor.execute("""
INSERT INTO historian_meta.tag_master (
    tag_id, tag_name, plant, area, equipment, data_type, report_flag
) VALUES (
    'TEST_TAG_003', 'TEST_TAG_003', 'FTP-1', 'POTLINE', 'TEST', 'double', TRUE
);
""")

# Check result
cursor.execute("SELECT COUNT(*) FROM historian_meta.report_templates WHERE tag_id = 'TEST_TAG_003';")
count = cursor.fetchone()[0]

print(f"\n[3] Result: count = {count}")

if count > 0:
    print("\n✅✅✅ TRIGGER WORKING!")
else:
    print("\n❌ Still not working - check PostgreSQL logs for NOTICE/WARNING messages")

cursor.close()
conn.close()
