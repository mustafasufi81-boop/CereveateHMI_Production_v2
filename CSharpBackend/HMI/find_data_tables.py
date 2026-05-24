import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)
cur = conn.cursor()

print("=== All tables in database ===\n")
cur.execute("""
    SELECT table_schema, table_name, 
           (SELECT COUNT(*) FROM information_schema.columns 
            WHERE c.table_schema = columns.table_schema 
            AND c.table_name = columns.table_name) as column_count
    FROM information_schema.tables c
    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
    ORDER BY table_schema, table_name
""")

for row in cur.fetchall():
    print(f"{row[0]}.{row[1]} ({row[2]} columns)")

print("\n=== Checking for data in each table ===\n")

# Check historian_raw.historian_timeseries
try:
    cur.execute("SELECT COUNT(*) FROM historian_raw.historian_timeseries")
    count = cur.fetchone()[0]
    print(f"historian_raw.historian_timeseries: {count:,} rows")
    if count > 0:
        cur.execute("SELECT * FROM historian_raw.historian_timeseries LIMIT 1")
        print(f"  Sample: {cur.fetchone()}\n")
except Exception as e:
    print(f"historian_raw.historian_timeseries: {e}\n")

# Check for other potential data tables
potential_tables = [
    'historian_data.timeseries',
    'historian_data.tag_values',
    'public.sensor_data',
    'public.tag_data',
    'historian_raw.tag_data',
    'historian_meta.tag_data'
]

for table in potential_tables:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        if count > 0:
            print(f"{table}: {count:,} rows")
            cur.execute(f"SELECT * FROM {table} LIMIT 1")
            print(f"  Sample: {cur.fetchone()}\n")
    except:
        pass

print("\n=== All schemas in database ===\n")
cur.execute("""
    SELECT schema_name 
    FROM information_schema.schemata 
    WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
    ORDER BY schema_name
""")
schemas = [row[0] for row in cur.fetchall()]
print("Schemas:", schemas)

for schema in schemas:
    print(f"\n=== Tables in {schema} schema ===")
    cur.execute(f"""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = '{schema}'
        ORDER BY table_name
    """)
    tables = [row[0] for row in cur.fetchall()]
    for table in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {schema}.{table}")
            count = cur.fetchone()[0]
            print(f"  {table}: {count:,} rows")
        except Exception as e:
            print(f"  {table}: Error - {e}")

cur.close()
conn.close()
