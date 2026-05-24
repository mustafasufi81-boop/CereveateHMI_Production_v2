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
print("CHECKING v_report_template_tags VIEW")
print("=" * 80)

# Check if view exists
cursor.execute("""
SELECT COUNT(*) 
FROM information_schema.views 
WHERE table_schema = 'historian_meta' 
  AND table_name = 'v_report_template_tags';
""")

if cursor.fetchone()[0] == 0:
    print("\n❌ View 'historian_meta.v_report_template_tags' DOES NOT EXIST!")
    print("   This is why fallback is being used.\n")
else:
    print("\n✅ View exists, checking contents...\n")
    
    # Check total rows in template
    cursor.execute("SELECT COUNT(*) FROM historian_meta.v_report_template_tags;")
    total = cursor.fetchone()[0]
    print(f"Total rows in template: {total}")
    
    if total > 0:
        # Check for FTP-1/POTLINE
        cursor.execute("""
        SELECT COUNT(*) 
        FROM historian_meta.v_report_template_tags 
        WHERE plant = 'FTP-1' AND area = 'POTLINE';
        """)
        ftp_count = cursor.fetchone()[0]
        print(f"FTP-1/POTLINE tags in template: {ftp_count}")
        
        # Show distinct plants/areas
        cursor.execute("""
        SELECT DISTINCT plant, area 
        FROM historian_meta.v_report_template_tags 
        ORDER BY plant, area;
        """)
        print("\nPlants/Areas in template:")
        for plant, area in cursor.fetchall():
            print(f"  - {plant} / {area}")
    else:
        print("⚠️ Template view is empty - fallback will always be used")

print("\n" + "=" * 80)
print("CHECKING tag_master (fallback source)")
print("=" * 80)

cursor.execute("""
SELECT COUNT(*) 
FROM historian_meta.tag_master 
WHERE plant = 'FTP-1' AND area = 'POTLINE';
""")
print(f"\nFTP-1/POTLINE tags in tag_master: {cursor.fetchone()[0]}")

cursor.execute("""
SELECT tag_id, sub_equipment, description, eng_unit 
FROM historian_meta.tag_master 
WHERE plant = 'FTP-1' AND area = 'POTLINE'
LIMIT 5;
""")

print("\nSample tags from tag_master:")
for tag_id, sub_eq, desc, unit in cursor.fetchall():
    print(f"  {tag_id}: sub_equipment='{sub_eq}', desc='{desc}', unit='{unit}'")

cursor.close()
conn.close()

print("\n" + "=" * 80)
print("RECOMMENDATION:")
print("If template view doesn't exist or is empty, the system will use fallback.")
print("This is NORMAL and expected. The Excel should still work correctly.")
print("=" * 80)
