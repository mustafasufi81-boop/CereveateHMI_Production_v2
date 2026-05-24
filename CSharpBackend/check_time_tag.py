import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

# Check Random.Time tag configuration
cur.execute("""
    SELECT tag_id, tag_name, data_type, deadband_value, enabled
    FROM historian_meta.tag_master
    WHERE tag_id = 'Random.Time';
""")

result = cur.fetchone()
if result:
    print(f"✅ Found Random.Time tag:")
    print(f"   tag_id: {result[0]}")
    print(f"   tag_name: {result[1]}")
    print(f"   data_type: {result[2]}")
    print(f"   deadband_value: {result[3]}")
    print(f"   enabled: {result[4]}")
    print(f"\n❌ PROBLEM: data_type is '{result[2]}' but should be 'String' for DateTime values!")
else:
    print("⚠️ Random.Time tag not found in tag_master")

cur.close()
conn.close()
