import psycopg2

conn = psycopg2.connect(
    host="localhost", port=5432, 
    database="Automation_DB", user="cereveate", password="cereveate@222"
)
cur = conn.cursor()

print("=" * 80)
print("CHECKING HISTORIAN DATA STRUCTURE")
print("=" * 80)

# Check if historian_raw schema exists
cur.execute("""
    SELECT schema_name 
    FROM information_schema.schemata 
    WHERE schema_name LIKE 'historian%'
""")
schemas = cur.fetchall()
print(f"\n[1] Available historian schemas: {[s[0] for s in schemas]}")

# Check tables in historian_raw
if schemas:
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'historian_raw'
    """)
    tables = cur.fetchall()
    print(f"\n[2] Tables in historian_raw: {[t[0] for t in tables]}")
    
    # Get columns for historian_timeseries
    if tables:
        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns 
            WHERE table_schema = 'historian_raw' 
            AND table_name = 'historian_timeseries'
            ORDER BY ordinal_position
        """)
        columns = cur.fetchall()
        print(f"\n[3] Columns in historian_raw.historian_timeseries:")
        for col_name, data_type in columns:
            print(f"  - {col_name} ({data_type})")
        
        # Get recent data
        if columns:
            col_names = [c[0] for c in columns]
            cur.execute(f"""
                SELECT {', '.join(col_names[:5])}
                FROM historian_raw.historian_timeseries 
                ORDER BY time DESC 
                LIMIT 3
            """)
            rows = cur.fetchall()
            print(f"\n[4] Recent data (last 3 rows):")
            for row in rows:
                print(f"  {row}")

cur.close()
conn.close()
print("\n" + "=" * 80)
