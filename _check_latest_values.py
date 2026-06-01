import psycopg2

conn = psycopg2.connect(
    host="localhost", port=5432, 
    database="Automation_DB", user="cereveate", password="cereveate@222"
)
cur = conn.cursor()

print("=" * 80)
print("CHECKING LATEST VALUES TABLE")
print("=" * 80)

# Get columns
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns 
    WHERE table_schema = 'historian_raw' 
    AND table_name = 'historian_latest_value'
    ORDER BY ordinal_position
""")
columns = cur.fetchall()
print(f"\nColumns in historian_raw.historian_latest_value:")
for col_name, data_type in columns:
    print(f"  - {col_name} ({data_type})")

# Get latest values
if columns:
    col_list = ', '.join([c[0] for c in columns[:8]])  # First 8 columns
    cur.execute(f"""
        SELECT {col_list}
        FROM historian_raw.historian_latest_value 
        LIMIT 5
    """)
    rows = cur.fetchall()
    print(f"\nSample data (first 5 tags):")
    for row in rows:
        print(f"  {row}")

cur.close()
conn.close()
print("\n" + "=" * 80)
