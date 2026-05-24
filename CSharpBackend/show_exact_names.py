"""
Show exact tag names from API vs Database
"""
import requests
import psycopg2

# Get from API
response = requests.get('http://localhost:5001/api/opc/values', timeout=5)
api_data = response.json()

print("\n" + "="*80)
print("EXACT PLC TAG NAMES FROM API (Welding related):")
print("="*80)
for tag in api_data['tags']:
    tag_id = tag['tagId']
    if any(x in tag_id for x in ['Weld', 'weld', 'Pipe', 'Joint', 'WPS', 'Welder', 'Sim', 'Arc', 'Power']):
        print(f"  '{tag_id}'")

# Get from database
conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)
cur = conn.cursor()

print("\n" + "="*80)
print("DATABASE TAG NAMES (Welding related):")
print("="*80)
cur.execute("""
    SELECT tag_id
    FROM historian_meta.tag_master
    WHERE tag_id LIKE '%Weld%' OR tag_id LIKE '%Pipe%' OR tag_id LIKE '%Joint%' 
       OR tag_id LIKE '%WPS%' OR tag_id LIKE '%Welder%' OR tag_id LIKE '%Sim%'
       OR tag_id LIKE '%Arc%' OR tag_id LIKE '%Power%'
    ORDER BY tag_id
""")

for row in cur.fetchall():
    print(f"  '{row[0]}'")

cur.close()
conn.close()
