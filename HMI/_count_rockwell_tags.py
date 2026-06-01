import json, psycopg2

with open('config.json', 'r') as f:
    config = json.load(f)

db = config['database']
conn = psycopg2.connect(host=db['host'], port=db['port'], database=db['database'], user=db['user'], password=db['password'])
cur = conn.cursor()

# Count tags for Rockwel_PLC_001
cur.execute("""
    SELECT COUNT(*) 
    FROM historian_meta.tag_master 
    WHERE server_progid='Rockwel_PLC_001' AND enabled=true
""")
print(f"Tags in DB for Rockwel_PLC_001: {cur.fetchone()[0]}")

# Sample 10 tags
cur.execute("""
    SELECT tag_id, tag_name 
    FROM historian_meta.tag_master 
    WHERE server_progid='Rockwel_PLC_001' AND enabled=true
    LIMIT 10
""")
print("\nFirst 10 tags:")
for tag_id, tag_name in cur.fetchall():
    print(f"  - {tag_id}: {tag_name}")

cur.close()
conn.close()
