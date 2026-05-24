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
print("FIXING TRIGGER - Checking function code")
print("=" * 80)

# Get the function source
cursor.execute("""
SELECT pg_get_functiondef(oid)
FROM pg_proc
WHERE proname = 'fn_auto_add_tag_to_report_template';
""")

func_def = cursor.fetchone()
if func_def:
    print("\nCurrent function definition:")
    print("=" * 80)
    print(func_def[0])
    print("=" * 80)

# Test the function manually
print("\n\nTesting trigger function manually...")
cursor.execute("""
DO $$
DECLARE
    test_tag_id TEXT := 'TEST_TAG_001';
    next_sno INTEGER;
    already_exists BOOLEAN;
BEGIN
    RAISE NOTICE 'Starting manual test...';
    
    -- Check if exists
    SELECT EXISTS (
        SELECT 1 FROM historian_meta.report_templates 
        WHERE tag_id = test_tag_id AND report_type = 'DAILY'
    ) INTO already_exists;
    
    RAISE NOTICE 'already_exists = %', already_exists;
    
    IF NOT already_exists THEN
        -- Get next s_no
        SELECT COALESCE(MAX(s_no), 0) + 1 INTO next_sno
        FROM historian_meta.report_templates;
        
        RAISE NOTICE 'next_sno = %', next_sno;
        
        -- Try insert
        INSERT INTO historian_meta.report_templates 
            (report_type, s_no, tag_id, enabled, created_at)
        VALUES 
            ('DAILY', next_sno, test_tag_id, TRUE, CURRENT_TIMESTAMP);
            
        RAISE NOTICE 'Insert successful!';
    ELSE
        RAISE NOTICE 'Tag already exists, skipping';
    END IF;
END $$;
""")
conn.commit()

# Check if manual insert worked
cursor.execute("SELECT COUNT(*) FROM historian_meta.report_templates WHERE tag_id = 'TEST_TAG_001';")
count = cursor.fetchone()[0]

print(f"\n\nAfter manual test: count = {count}")

if count > 0:
    print("✅ Manual insert worked! The trigger logic is correct.")
    print("   Problem might be: trigger not firing or permissions")
else:
    print("❌ Manual insert also failed!")

cursor.close()
conn.close()
