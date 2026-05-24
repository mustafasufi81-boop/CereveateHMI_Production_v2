"""
Compare EXACT tag names: Database vs API
"""
import psycopg2
import requests

# Get DATABASE tag names
conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)
cur = conn.cursor()

cur.execute("""
    SELECT tag_id
    FROM historian_meta.tag_master
    WHERE server_progid = 'Rockwel_PLC_001'
    AND enabled = true
    ORDER BY tag_id
""")

db_tags = [row[0] for row in cur.fetchall()]

# Get API tag names
response = requests.get('http://localhost:5001/api/opc/values', timeout=5)
api_data = response.json()
api_tags = [tag['tagId'] for tag in api_data['tags']]

print("\n" + "="*100)
print("DATABASE TAGS (from screenshot):")
print("="*100)
db_welding = [t for t in db_tags if any(x in t for x in ['Weld', 'Pipe', 'Joint', 'WPS', 'Welder', 'Arc', 'Power', 'Sim'])]
for tag in sorted(db_welding):
    in_api = "✅ IN API" if tag in api_tags else "❌ NOT IN API"
    print(f"  {tag:<30} {in_api}")

print("\n" + "="*100)
print("API TAGS (from PLC):")
print("="*100)
api_welding = [t for t in api_tags if any(x in t for x in ['Weld', 'Pipe', 'Joint', 'WPS', 'Welder', 'Arc', 'Power', 'Sim'])]
for tag in sorted(api_welding):
    in_db = "✅ IN DB" if tag in db_tags else "❌ NOT IN DB"
    print(f"  {tag:<30} {in_db}")

print("\n" + "="*100)
print("MISMATCH ANALYSIS:")
print("="*100)

# Find tags that need to be renamed
print("\nTags in DB but NOT in API (need to be renamed):")
for db_tag in db_welding:
    if db_tag not in api_tags:
        # Find similar tag in API
        for api_tag in api_welding:
            if api_tag.replace(' ', '_').replace('ID', 'Id').replace('id', 'id').lower() == db_tag.replace(' ', '_').lower():
                print(f"  {db_tag:<30} → {api_tag}")
                break

print("\nTags in API but NOT in DB (database missing these):")
for api_tag in api_welding:
    if api_tag not in db_tags:
        print(f"  {api_tag}")

cur.close()
conn.close()
