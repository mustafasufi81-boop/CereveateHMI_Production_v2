import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="Automation_DB",
    user="cereveate",
    password="cereveate@222"
)

cursor = conn.cursor()

# Update the BOILER tags to Area-2
cursor.execute("""
    UPDATE historian_meta.tag_master
    SET area = 'Area-2'
    WHERE tag_id LIKE 'BOILER%'
    RETURNING tag_id, plant, area
""")

updated = cursor.fetchall()
conn.commit()

print(f"Updated {len(updated)} BOILER tags to Area-2:")
for tag_id, plant, area in updated:
    print(f"  {tag_id:30} → Plant: {plant:15} Area: {area}")

# Verify unique plant/area combinations now
cursor.execute("""
    SELECT DISTINCT plant, area, COUNT(*) as tag_count
    FROM historian_meta.tag_master
    WHERE plant IS NOT NULL AND area IS NOT NULL
    GROUP BY plant, area
    ORDER BY plant, area
""")

combos = cursor.fetchall()
print(f"\nUnique Plant/Area combinations after update ({len(combos)}):")
for plant, area, count in combos:
    print(f"  {plant:15} | {area:15} | {count:4} tags")

conn.close()
