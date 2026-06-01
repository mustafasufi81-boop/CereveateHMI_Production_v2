import json, psycopg2

with open('config.json', 'r') as f:
    config = json.load(f)

db = config['database']
conn = psycopg2.connect(host=db['host'], port=db['port'], database=db['database'], user=db['user'], password=db['password'])
cur = conn.cursor()

print("\n🔍 FINDING CORRECT TABLE STRUCTURE\n")

# Get historian_calc_values columns
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema = 'historian_raw' 
    AND table_name = 'historian_calc_values'
    ORDER BY ordinal_position
""")
print("historian_calc_values columns:")
for row in cur.fetchall():
    print(f"  - {row[0]}: {row[1]}")

# Check sample data
print("\nSample data (first 5 records):")
cur.execute("""
    SELECT * FROM historian_raw.historian_calc_values 
    ORDER BY time DESC 
    LIMIT 5
""")
rows = cur.fetchall()
if rows:
    # Get column names from cursor description
    cols = [desc[0] for desc in cur.description]
    print(f"  Columns: {cols}")
    for row in rows:
        print(f"  {row}")
else:
    print("  NO DATA")

# Check latest_value structure
print("\nhistorian_latest_value columns:")
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema = 'historian_raw' 
    AND table_name = 'historian_latest_value'
    ORDER BY ordinal_position
""")
for row in cur.fetchall():
    print(f"  - {row[0]}: {row[1]}")

# Check v_daily_hourly_agg source
print("\nv_daily_hourly_agg view definition:")
cur.execute("""
    SELECT pg_get_viewdef('historian_raw.v_daily_hourly_agg', true)
""")
viewdef = cur.fetchone()[0]
# Print first 800 chars to see the logic
print(viewdef[:800])

cur.close()
conn.close()
