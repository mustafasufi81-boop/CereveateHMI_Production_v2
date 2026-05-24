import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="Automation_DB",
    user="cereveate",
    password="cereveate@222"
)

cursor = conn.cursor()

# Get view columns
cursor.execute("""
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_schema = 'historian_meta' 
AND table_name = 'v_report_template_tags'
ORDER BY ordinal_position;
""")

print("v_report_template_tags columns:")
for col, dtype in cursor.fetchall():
    print(f"  {col} ({dtype})")

# Check actual data
print("\nActual data query:")
cursor.execute("""
SELECT * FROM historian_meta.v_report_template_tags 
WHERE tag_id IN ('PY1103A', 'PY1103B', 'PY1101A', 'PY1101B', 'TY1101A')
LIMIT 1;
""")

if cursor.rowcount > 0:
    print(f"Found {cursor.rowcount} row(s)")
    print(cursor.fetchone())
else:
    print("No data found")

cursor.close()
conn.close()
