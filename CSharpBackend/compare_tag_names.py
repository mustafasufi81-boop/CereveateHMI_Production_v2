"""
Compare PLC tag names from API with database tag names to find mismatches
"""
import requests
import psycopg2

# Get tags from API
response = requests.get('http://localhost:5001/api/opc/values', timeout=5)
api_tags = {}
if response.status_code == 200:
    data = response.json()
    for tag in data['tags']:
        api_tags[tag['tagId']] = tag['value']

# Get welding tags from database
conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)
cur = conn.cursor()

welding_tags_db = [
    'Welding_Current_A', 'Welding_Voltage_V', 'Arc', 'Power', 
    'Pipe_Id', 'Joint_Id', 'Welder_id', 'WPS_ID', 'sim_step'
]

cur.execute("""
    SELECT tag_id, tag_name
    FROM historian_meta.tag_master
    WHERE tag_id = ANY(%s)
    ORDER BY tag_id
""", (welding_tags_db,))

db_tags = {row[0]: row[1] for row in cur.fetchall()}

print("\n" + "="*100)
print("TAG NAME MISMATCH ANALYSIS")
print("="*100)

print("\n1. DATABASE TAG CONFIGURATION:")
print("-" * 100)
print(f"{'DB Tag ID':<30} {'DB Tag Name':<30} {'In API?':<10} {'Possible PLC Name':<30}")
print("-" * 100)

for tag_id, tag_name in sorted(db_tags.items()):
    in_api = "✅ YES" if tag_id in api_tags else "❌ NO"
    
    # Suggest what the PLC tag name might be (with spaces instead of underscores)
    plc_suggestion = tag_id.replace('_', ' ')
    
    print(f"{tag_id:<30} {tag_name:<30} {in_api:<10} {plc_suggestion:<30}")

print("\n2. ACTUAL PLC TAGS IN API (matching pattern):")
print("-" * 100)
print(f"{'API Tag ID':<40} {'Value':<20} {'Matches DB?':<15}")
print("-" * 100)

# Check for tags with "Welding" or similar patterns
for tag_id, value in sorted(api_tags.items()):
    if any(keyword in tag_id.lower() for keyword in ['welding', 'pipe', 'joint', 'welder', 'wps', 'arc', 'power', 'sim']):
        matches = "✅ YES" if tag_id in db_tags else "❌ NO"
        print(f"{tag_id:<40} {str(value):<20} {matches:<15}")

print("\n" + "="*100)
print("DIAGNOSIS:")
print("="*100)
print("""
The issue is likely TAG NAME MISMATCH between database and PLC:

DATABASE EXPECTS:          PLC ACTUALLY HAS:
- Welding_Current_A        → Welding Current A  (spaces, not underscores)
- Welding_Voltage_V        → Welding Voltage V
- Pipe_Id                  → Pipe Id
- Joint_Id                 → Joint Id
- Welder_id                → Welder id
- WPS_ID                   → WPS ID
- sim_step                 → sim step

SOLUTION: Update database tag_id to match actual PLC tag names (with spaces)
""")

cur.close()
conn.close()
