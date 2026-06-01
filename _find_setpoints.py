import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Automation_DB",
    user="cereveate",
    password="cereveate@222"
)
cur = conn.cursor()

# Find the alarm setpoints table
cur.execute("""
    SELECT table_schema, table_name 
    FROM information_schema.tables 
    WHERE table_name LIKE '%setpoint%' OR table_name LIKE '%config%'
    ORDER BY table_schema, table_name
""")

tables = cur.fetchall()
print("FOUND TABLES:")
for schema, table in tables:
    print(f"  {schema}.{table}")

# Try common table name
if tables:
    schema, table = tables[0]
    print(f"\nCHECKING {schema}.{table} for TY1101D:")
    try:
        cur.execute(f"SELECT * FROM {schema}.{table} WHERE tag_id ILIKE '%TY1101D%' LIMIT 1")
        rows = cur.fetchall()
        if rows:
            # Get column names
            colnames = [desc[0] for desc in cur.description]
            print(f"\nColumns: {', '.join(colnames)}")
            print(f"\nFirst row:")
            for col, val in zip(colnames, rows[0]):
                print(f"  {col}: {val}")
    except Exception as e:
        print(f"  Error: {e}")

conn.close()
