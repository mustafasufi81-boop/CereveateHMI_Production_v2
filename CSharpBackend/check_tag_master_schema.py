import psycopg2

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    dbname='Cereveate',
    user='cereveate',
    password='Industrial@2024'
)

cur = conn.cursor()

# Get column names and types
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema='historian_meta' 
    AND table_name='tag_master' 
    ORDER BY ordinal_position
""")

print("📋 historian_meta.tag_master schema:")
print("-" * 50)
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

# Get sample data
print("\n📊 Sample tags (first 3):")
print("-" * 50)
cur.execute("""
    SELECT tag_id, tag_name, description, plant, area, equipment, data_type, eng_unit, enabled
    FROM historian_meta.tag_master
    WHERE enabled = true
    LIMIT 3
""")

for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]} | plant={row[3]} | area={row[4]} | enabled={row[8]}")

cur.close()
conn.close()
