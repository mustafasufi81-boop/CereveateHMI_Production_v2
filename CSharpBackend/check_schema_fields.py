"""Check tag_master schema to see available fields for sub_equipment and description"""
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    dbname='Automation_DB',
    user='cereveate',
    password='cereveate@222'
)
cur = conn.cursor()

# Check columns in tag_master
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema = 'historian_meta' 
    AND table_name = 'tag_master'
    ORDER BY ordinal_position
""")
print("=== tag_master columns ===")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

# Check sample data for TY1101A
cur.execute("""
    SELECT tag_id, tag_name, equipment, sub_equipment, components, 
           description, eng_unit, data_type, plant, area
    FROM historian_meta.tag_master
    WHERE tag_id = 'TY1101A'
""")
print("\n=== Sample data for TY1101A ===")
row = cur.fetchone()
if row:
    print(f"  tag_id: {row[0]}")
    print(f"  tag_name: {row[1]}")
    print(f"  equipment: {row[2]}")
    print(f"  sub_equipment: {row[3]}")
    print(f"  components: {row[4]}")
    print(f"  description: {row[5]}")
    print(f"  eng_unit: {row[6]}")
    print(f"  data_type: {row[7]}")
    print(f"  plant: {row[8]}")
    print(f"  area: {row[9]}")

# Check v_report_template_tags view
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema = 'historian_meta' 
    AND table_name = 'v_report_template_tags'
    ORDER BY ordinal_position
""")
print("\n=== v_report_template_tags columns ===")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

conn.close()
