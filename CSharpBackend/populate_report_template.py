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
print("ADDING FTP-1/POTLINE TAGS TO report_templates TABLE")
print("=" * 80)

# Get FTP-1/POTLINE tags that have data
cursor.execute("""
SELECT DISTINCT tm.tag_id, tm.tag_name, tm.equipment
FROM historian_meta.tag_master tm
WHERE tm.plant = 'FTP-1' AND tm.area = 'POTLINE'
  AND tm.tag_id IN (
    SELECT DISTINCT tag_id 
    FROM historian_raw.v_daily_hourly_agg 
    WHERE local_date = '2026-05-18'
  )
ORDER BY tm.tag_id;
""")

tags = cursor.fetchall()
print(f"\nFound {len(tags)} tags to add:\n")

for tag_id, tag_name, equipment in tags:
    print(f"  - {tag_id} ({tag_name})")

# Get next available s_no
cursor.execute("SELECT COALESCE(MAX(s_no), 0) + 1 FROM historian_meta.report_templates;")
next_s_no = cursor.fetchone()[0]

print(f"\nStarting s_no: {next_s_no}")
print("\nInserting into report_templates...")

inserted = 0
for i, (tag_id, tag_name, equipment) in enumerate(tags):
    s_no = next_s_no + i
    
    # Check if already exists
    cursor.execute("""
    SELECT COUNT(*) FROM historian_meta.report_templates 
    WHERE tag_id = %s AND report_type = 'DAILY';
    """, (tag_id,))
    
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO historian_meta.report_templates (report_type, s_no, tag_id, enabled)
        VALUES ('DAILY', %s, %s, TRUE);
        """, (s_no, tag_id))
        inserted += 1
        print(f"  ✅ Inserted: {tag_id} (s_no={s_no})")
    else:
        print(f"  ⏭️  Skipped (already exists): {tag_id}")

conn.commit()

print(f"\n{'=' * 80}")
print(f"✅ DONE! Inserted {inserted} new tags into report_templates")
print(f"{'=' * 80}")

# Verify the view now shows the tags
cursor.execute("""
SELECT COUNT(*) FROM historian_meta.v_report_template_tags
WHERE plant = 'FTP-1' AND area = 'POTLINE';
""")

count = cursor.fetchone()[0]
print(f"\nv_report_template_tags now has {count} tags for FTP-1/POTLINE")

if count > 0:
    print("\n✅ Template query will now work! Fallback won't be needed.")
else:
    print("\n⚠️ Still 0 tags - check if tag_master has plant/area set correctly")

cursor.close()
conn.close()
