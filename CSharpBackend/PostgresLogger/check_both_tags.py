import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)
cur = conn.cursor()

# Check both tags
tags_to_check = ['SHAFT_VIB._IP_REAR-X', 'BEARING_VIB_HP_FRONT-Y']

print("\n=== DATA COUNT PER TAG ===\n")
for tag in tags_to_check:
    cur.execute(f"SELECT COUNT(*) FROM sensor_data WHERE tag_code = '{tag}'")
    count = cur.fetchone()[0]
    
    if count > 0:
        print(f"✅ {tag}: {count:,} records")
        
        cur.execute(f"""
            SELECT timestamp, plant, asset, value, quality_code
            FROM sensor_data 
            WHERE tag_code = '{tag}'
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            print(f"   Latest: {row[0]} | Plant: {row[1]} | Asset: {row[2]} | Value: {row[3]}")
    else:
        print(f"❌ {tag}: No data imported yet")

print()

# Check file imports
cur.execute("SELECT file_path, status, records_imported FROM file_imports ORDER BY id DESC LIMIT 2")
imports = cur.fetchall()
if imports:
    print("=== RECENT IMPORTS ===")
    for imp in imports:
        print(f"  {imp[0]}: {imp[1]} - {imp[2]} records")
else:
    print("⚠️  No file imports logged (file not processed yet)")

# Check total tags with data
cur.execute("SELECT COUNT(DISTINCT tag_code) FROM sensor_data WHERE tag_code IS NOT NULL")
total_tags = cur.fetchone()[0]
print(f"\n📊 Total unique tags with data: {total_tags}\n")

cur.close()
conn.close()
