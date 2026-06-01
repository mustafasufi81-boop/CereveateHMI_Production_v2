import json, psycopg2
from datetime import date, timedelta

with open('config.json') as f:
    config = json.load(f)

conn = psycopg2.connect(**config['database'])
cur = conn.cursor()

# Get correct column names
cur.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_schema = 'historian_raw' 
    AND table_name = 'historian_calc_values'
    ORDER BY ordinal_position
""")
cols = [r[0] for r in cur.fetchall()]
print(f"\nhistorian_calc_values columns: {cols}\n")

# Check recent data with correct columns
cur.execute(f"""
    SELECT * FROM historian_raw.historian_calc_values
    ORDER BY {cols[1]} DESC LIMIT 3
""")
print("Recent data:")
for r in cur.fetchall():
    print(f"  {r}")

cur.close()
conn.close()
