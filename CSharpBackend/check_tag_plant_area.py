import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="Automation_DB",
    user="cereveate",
    password="cereveate@222"
)

cursor = conn.cursor()

# Check how many tags have plant/area filled
cursor.execute("""
    SELECT 
        COUNT(*) as total_tags,
        COUNT(plant) as has_plant,
        COUNT(area) as has_area,
        COUNT(CASE WHEN plant IS NOT NULL AND area IS NOT NULL THEN 1 END) as has_both
    FROM historian_meta.tag_master
""")
counts = cursor.fetchone()
print("Tag Statistics:")
print(f"  Total tags: {counts[0]}")
print(f"  Tags with plant: {counts[1]}")
print(f"  Tags with area: {counts[2]}")
print(f"  Tags with both: {counts[3]}")
print()

# Show unique plant/area combinations
cursor.execute("""
    SELECT DISTINCT
        plant,
        area,
        server_progid,
        COUNT(*) as tag_count
    FROM historian_meta.tag_master
    WHERE plant IS NOT NULL AND area IS NOT NULL
    GROUP BY plant, area, server_progid
    ORDER BY plant, area, server_progid
""")
combos = cursor.fetchall()
print(f"Unique Plant/Area/Source combinations ({len(combos)}):")
for plant, area, source, count in combos:
    source_str = source if source else "NULL"
    print(f"  {plant:15} | {area:15} | {source_str:30} | {count:4} tags")
print()

# Show tags WITHOUT plant/area
cursor.execute("""
    SELECT tag_id, server_progid, enabled
    FROM historian_meta.tag_master
    WHERE plant IS NULL OR area IS NULL
    LIMIT 10
""")
missing = cursor.fetchall()
if missing:
    print(f"Tags WITHOUT plant/area (first 10):")
    for tag_id, source, enabled in missing:
        print(f"  {tag_id:30} | {source:30} | enabled={enabled}")

conn.close()
