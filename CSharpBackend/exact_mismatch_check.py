"""
Check exact mismatch between PLC tags in API and database tag_master
"""
import requests
import psycopg2

# Get PLC tags from API
response = requests.get('http://localhost:5001/api/opc/values', timeout=5)
api_data = response.json()
api_tags = {tag['tagId']: tag for tag in api_data['tags']}

# Get database tags
conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)
cur = conn.cursor()

welding_tags = ['Welding_Current_A', 'Welding_Voltage_V', 'Pipe_Id', 'Joint_Id', 
                'Welder_id', 'WPS_ID', 'sim_step', 'Arc', 'Power']

cur.execute("""
    SELECT tag_id, tag_name, enabled
    FROM historian_meta.tag_master
    WHERE tag_id = ANY(%s)
    ORDER BY tag_id
""", (welding_tags,))

print("\n" + "="*100)
print("EXACT COMPARISON: DATABASE vs API (LIVE PLC DATA)")
print("="*100)
print(f"{'DB tag_id':<25} {'In API?':<10} {'API Value':<20} {'DB Enabled':<12} {'ISSUE':<30}")
print("-" * 100)

for row in cur.fetchall():
    db_tag_id, db_tag_name, enabled = row
    
    if db_tag_id in api_tags:
        api_value = str(api_tags[db_tag_id]['value'])[:15]
        in_api = "✅ YES"
        issue = "OK - Will write to DB"
    else:
        api_value = "NOT FOUND"
        in_api = "❌ NO"
        issue = "MISMATCH - Won't write!"
    
    enabled_str = "✅ YES" if enabled else "❌ NO"
    print(f"{db_tag_id:<25} {in_api:<10} {api_value:<20} {enabled_str:<12} {issue:<30}")

print("\n" + "="*100)
print("TAGS IN API BUT NOT IN DATABASE:")
print("="*100)

api_welding = [t for t in api_tags.keys() if any(x in t for x in ['Weld', 'Pipe', 'Joint', 'WPS', 'Welder', 'sim', 'Arc', 'Power'])]
for api_tag in sorted(api_welding):
    if api_tag not in welding_tags:
        print(f"❌ {api_tag:<30} = {str(api_tags[api_tag]['value']):<15} (NOT IN DATABASE)")

cur.close()
conn.close()

print("\n" + "="*100)
print("SOLUTION:")
print("="*100)
print("Update database tag_id to match EXACT API tag names")
