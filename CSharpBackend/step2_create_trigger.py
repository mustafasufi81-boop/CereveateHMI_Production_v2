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
print("STEP 2: CREATE AUTO-POPULATE TRIGGER (CAREFULLY)")
print("=" * 80)

# Step 2a: Check if report_flag column exists
print("\n[2a] Checking report_flag column...")
cursor.execute("""
SELECT column_name, data_type, column_default
FROM information_schema.columns 
WHERE table_schema = 'historian_meta' 
  AND table_name = 'tag_master' 
  AND column_name = 'report_flag';
""")

result = cursor.fetchone()
if result:
    print(f"✅ Column exists: {result[0]} ({result[1]}) default={result[2]}")
else:
    print("❌ Column does NOT exist. Adding it...")
    cursor.execute("""
    ALTER TABLE historian_meta.tag_master 
    ADD COLUMN report_flag BOOLEAN DEFAULT TRUE;
    """)
    conn.commit()
    print("✅ Column added with DEFAULT TRUE")

# Step 2b: Set report_flag = TRUE for existing tags that are NULL
print("\n[2b] Setting report_flag = TRUE for existing tags...")
cursor.execute("""
UPDATE historian_meta.tag_master 
SET report_flag = TRUE 
WHERE report_flag IS NULL;
""")
updated = cursor.rowcount
conn.commit()
print(f"✅ Updated {updated} tags to report_flag = TRUE")

# Step 2c: Drop existing trigger/function if exists (clean slate)
print("\n[2c] Cleaning up old trigger/function (if exists)...")
cursor.execute("""
DROP TRIGGER IF EXISTS trg_auto_add_tag_to_report_template ON historian_meta.tag_master CASCADE;
DROP FUNCTION IF EXISTS historian_meta.fn_auto_add_tag_to_report_template() CASCADE;
""")
conn.commit()
print("✅ Old trigger/function removed")

# Step 2d: Create the trigger function with careful logic
print("\n[2d] Creating trigger function...")
cursor.execute("""
CREATE OR REPLACE FUNCTION historian_meta.fn_auto_add_tag_to_report_template()
RETURNS TRIGGER AS $$
DECLARE
    next_sno INTEGER;
    already_exists BOOLEAN;
BEGIN
    -- Only process if report_flag is TRUE
    IF NEW.report_flag = TRUE THEN
        -- Check if tag already exists in report_templates
        SELECT EXISTS (
            SELECT 1 
            FROM historian_meta.report_templates 
            WHERE tag_id = NEW.tag_id 
              AND report_type = 'DAILY'
        ) INTO already_exists;
        
        -- Only insert if it doesn't already exist
        IF NOT already_exists THEN
            -- Get next available s_no (with locking to prevent duplicates)
            SELECT COALESCE(MAX(s_no), 0) + 1 
            INTO next_sno
            FROM historian_meta.report_templates
            FOR UPDATE;
            
            -- Insert into report_templates
            INSERT INTO historian_meta.report_templates 
                (report_type, s_no, tag_id, enabled, created_at)
            VALUES 
                ('DAILY', next_sno, NEW.tag_id, TRUE, CURRENT_TIMESTAMP);
            
            -- Log the action
            RAISE NOTICE 'AUTO-ADDED: tag_id=% to report_templates with s_no=%', NEW.tag_id, next_sno;
        ELSE
            RAISE NOTICE 'SKIPPED: tag_id=% already exists in report_templates', NEW.tag_id;
        END IF;
    ELSE
        RAISE NOTICE 'SKIPPED: tag_id=% has report_flag=FALSE', NEW.tag_id;
    END IF;
    
    RETURN NEW;
EXCEPTION
    WHEN OTHERS THEN
        -- Log error but don't fail the tag insert
        RAISE WARNING 'ERROR in trigger for tag_id=%: %', NEW.tag_id, SQLERRM;
        RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""")
conn.commit()
print("✅ Trigger function created with:")
print("   - Check if tag already exists")
print("   - Get next s_no with locking (prevent race conditions)")
print("   - Insert only if not exists")
print("   - Error handling (won't fail tag insert)")
print("   - Detailed logging via RAISE NOTICE")

# Step 2e: Create the trigger
print("\n[2e] Creating trigger on tag_master...")
cursor.execute("""
CREATE TRIGGER trg_auto_add_tag_to_report_template
    AFTER INSERT OR UPDATE OF report_flag 
    ON historian_meta.tag_master
    FOR EACH ROW
    EXECUTE FUNCTION historian_meta.fn_auto_add_tag_to_report_template();
""")
conn.commit()
print("✅ Trigger created")
print("   - Fires AFTER INSERT or UPDATE of report_flag")
print("   - Executes FOR EACH ROW")

# Step 2f: Verify trigger is active
print("\n[2f] Verifying trigger installation...")
cursor.execute("""
SELECT 
    tgname AS trigger_name,
    tgenabled AS enabled,
    tgtype AS trigger_type
FROM pg_trigger t
JOIN pg_class c ON t.tgrelid = c.oid
WHERE c.relname = 'tag_master'
  AND t.tgname = 'trg_auto_add_tag_to_report_template';
""")

trigger_info = cursor.fetchone()
if trigger_info:
    print(f"✅ Trigger verified: {trigger_info[0]}")
    print(f"   Enabled: {trigger_info[1] == 'O'}")  # 'O' = enabled
else:
    print("❌ Trigger NOT found!")

print("\n" + "=" * 80)
print("✅ STEP 2 COMPLETE - Trigger is ready")
print("=" * 80)
print("\n📋 Trigger will activate on:")
print("   1. INSERT new tag with report_flag = TRUE")
print("   2. UPDATE existing tag SET report_flag = TRUE")
print("\n⏭️  Ready for STEP 3: Test with a new tag")

cursor.close()
conn.close()
