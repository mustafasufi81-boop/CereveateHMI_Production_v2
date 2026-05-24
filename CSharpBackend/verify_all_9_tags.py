import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

# Check all 9 tags from the image
all_tags = [
    'Welding_Current_A',
    'Welding_Voltage_V',
    'Arc',
    'Power',
    'Pipe_Id',
    'Joint_Id',
    'Welder_id',
    'WPS_ID',
    'sim_step'
]

print("\n" + "="*60)
print("CHECKING ALL 9 WELDING TAGS FROM IMAGE")
print("="*60)

found = []
missing = []

for tag in all_tags:
    cur.execute("""
        SELECT tag_id, enabled, data_type 
        FROM historian_meta.tag_master 
        WHERE tag_id = %s
    """, (tag,))
    
    result = cur.fetchone()
    if result:
        tag_id, enabled, data_type = result
        status = "✅ ENABLED" if enabled else "❌ DISABLED"
        print(f"{status} | {tag_id:25s} | {data_type}")
        found.append(tag)
    else:
        print(f"❌ MISSING | {tag:25s}")
        missing.append(tag)

print("\n" + "="*60)
print(f"Found: {len(found)}/9")
print(f"Missing: {len(missing)}/9")

if missing:
    print("\n⚠️  MISSING TAGS:")
    for tag in missing:
        print(f"  - {tag}")

print("="*60)

cur.close()
conn.close()
