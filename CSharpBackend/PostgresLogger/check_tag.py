import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)
cur = conn.cursor()

# Check if second tag exists in catalog
cur.execute("SELECT tag_id FROM tag_catalog ORDER BY tag_id")
tags = cur.fetchall()

print("\n=== ALL TAGS IN CATALOG ===")
for tag in tags:
    print(f"  {tag[0]}")

print(f"\nTotal: {len(tags)} tags")

# Check for BEARING specifically
cur.execute("SELECT tag_id FROM tag_catalog WHERE tag_id ILIKE '%bearing%'")
bearing_tags = cur.fetchall()
print(f"\n=== BEARING TAGS ===")
if bearing_tags:
    for tag in bearing_tags:
        print(f"  {tag[0]}")
else:
    print("  ❌ No BEARING tags found in catalog!")

# Check file imports
cur.execute("SELECT file_path, status, records_imported, error_message FROM file_imports ORDER BY import_time DESC LIMIT 5")
imports = cur.fetchall()
print("\n=== RECENT FILE IMPORTS ===")
for imp in imports:
    print(f"  File: {imp[0]}")
    print(f"    Status: {imp[1]}, Records: {imp[2]}")
    if imp[3]:
        print(f"    Error: {imp[3]}")

cur.close()
conn.close()
