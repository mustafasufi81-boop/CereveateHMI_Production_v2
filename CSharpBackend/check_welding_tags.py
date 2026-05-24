import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

# Get all welding-related tags
cur.execute("""
    SELECT tag_id, tag_name, data_type, eng_unit, enabled
    FROM historian_meta.tag_master
    WHERE tag_id IN (
        'Welding_Current_A', 'Welding_Voltage_V', 'Arc', 'Power', 
        'Pipe_Id', 'Joint_Id', 'Welder_id', 'WPS_ID', 'sim_step'
    )
    ORDER BY tag_id
""")

print("\n" + "="*80)
print("WELDING TAGS IN DATABASE")
print("="*80)

tags_found = []
for row in cur.fetchall():
    tag_id, tag_name, data_type, eng_unit, enabled = row
    tags_found.append(tag_id)
    status = "✅ ENABLED" if enabled else "❌ DISABLED"
    print(f"{status} | {tag_id:25s} | {data_type:10s} | {eng_unit:5s} | {tag_name}")

print("\n" + "="*80)
print("COMPARISON WITH IMAGE")
print("="*80)

expected_tags = [
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

for tag in expected_tags:
    if tag in tags_found:
        print(f"✅ {tag:25s} - IN DATABASE")
    else:
        print(f"❌ {tag:25s} - MISSING FROM DATABASE")

print("\n" + "="*80)
print(f"Total tags expected: {len(expected_tags)}")
print(f"Total tags found: {len(tags_found)}")
print("="*80)

cur.close()
conn.close()
