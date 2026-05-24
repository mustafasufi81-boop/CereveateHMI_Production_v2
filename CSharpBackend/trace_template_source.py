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
print("TRACING v_report_template_tags VIEW SOURCE")
print("=" * 80)

# Get the view definition
cursor.execute("""
SELECT definition 
FROM pg_views 
WHERE schemaname = 'historian_meta' 
  AND viewname = 'v_report_template_tags';
""")

view_def = cursor.fetchone()
if view_def:
    print("\n📋 VIEW DEFINITION:")
    print("-" * 80)
    print(view_def[0])
    print("-" * 80)
else:
    print("\n❌ View definition not found!")

# Find all tables in historian_meta schema
print("\n\n📊 TABLES IN historian_meta SCHEMA:")
print("-" * 80)
cursor.execute("""
SELECT table_name, 
       (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = 'historian_meta' AND table_name = t.table_name) as column_count
FROM information_schema.tables t
WHERE table_schema = 'historian_meta' 
  AND table_type = 'BASE TABLE'
ORDER BY table_name;
""")

tables = cursor.fetchall()
for table_name, col_count in tables:
    cursor.execute(f"SELECT COUNT(*) FROM historian_meta.{table_name};")
    row_count = cursor.fetchone()[0]
    print(f"  {table_name:40} | Columns: {col_count:3} | Rows: {row_count:6}")

# Check if there's a report_template table
print("\n\n🔍 SEARCHING FOR REPORT TEMPLATE TABLES:")
print("-" * 80)
cursor.execute("""
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'historian_meta' 
  AND table_name LIKE '%template%'
ORDER BY table_name;
""")

template_tables = cursor.fetchall()
if template_tables:
    for (table_name,) in template_tables:
        cursor.execute(f"""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_schema = 'historian_meta' 
          AND table_name = '{table_name}'
        ORDER BY ordinal_position;
        """)
        print(f"\n📄 Table: historian_meta.{table_name}")
        for col_name, data_type in cursor.fetchall():
            print(f"     - {col_name} ({data_type})")
        
        cursor.execute(f"SELECT COUNT(*) FROM historian_meta.{table_name};")
        count = cursor.fetchone()[0]
        print(f"     Total rows: {count}")
        
        if count > 0:
            cursor.execute(f"SELECT * FROM historian_meta.{table_name} LIMIT 3;")
            print(f"     Sample rows:")
            for row in cursor.fetchall():
                print(f"       {row}")
else:
    print("  ❌ No tables with 'template' in name found!")

cursor.close()
conn.close()

print("\n" + "=" * 80)
print("CONCLUSION:")
print("The view pulls data from an underlying table. You need to INSERT rows into")
print("that table to populate the report template for FTP-1/POTLINE tags.")
print("=" * 80)
