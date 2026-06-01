import json, psycopg2

with open('config.json', 'r') as f:
    config = json.load(f)

db = config['database']
conn = psycopg2.connect(host=db['host'], port=db['port'], database=db['database'], user=db['user'], password=db['password'])
cur = conn.cursor()

cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema='historian_meta' 
    AND table_name='plants_areas' 
    ORDER BY ordinal_position
""")

print("plants_areas columns:")
for col, dtype in cur.fetchall():
    print(f"  {col}: {dtype}")

cur.close()
conn.close()
