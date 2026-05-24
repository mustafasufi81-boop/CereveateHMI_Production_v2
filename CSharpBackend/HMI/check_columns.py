import psycopg2

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)

cursor = conn.cursor()

# Get column names
cursor.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema = 'historian_meta' 
    AND table_name = 'tag_master'
    ORDER BY ordinal_position
""")

print("Columns in historian_meta.tag_master:")
for col in cursor.fetchall():
    print(f"  - {col[0]} ({col[1]})")

# Try the actual query
print("\nTrying the API query...")
try:
    cursor.execute("""
        SELECT tag_id, tag_name, data_type, eng_unit, 
               description, plant, area, equipment
        FROM historian_meta.tag_master
        WHERE enabled = true
        LIMIT 5
    """)
    rows = cursor.fetchall()
    print(f"Query returned {len(rows)} rows")
    for row in rows:
        print(f"  Row: {row}")
except Exception as e:
    print(f"ERROR: {e}")

cursor.close()
conn.close()
