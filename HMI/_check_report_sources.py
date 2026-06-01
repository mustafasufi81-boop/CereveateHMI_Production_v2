import json, psycopg2

with open('config.json', 'r') as f:
    config = json.load(f)

db = config['database']
conn = psycopg2.connect(host=db['host'], port=db['port'], database=db['database'], user=db['user'], password=db['password'])
cur = conn.cursor()

print("\n" + "="*100)
print("PLANTS_AREAS TABLE (Report Source Configuration)")
print("="*100)

cur.execute("""
    SELECT plant, area, plant_code, area_code, server_progid, display_name, is_active 
    FROM historian_meta.plants_areas 
    ORDER BY plant, area
""")

print(f"\n{'Plant':<15} {'Area':<15} {'PlantCode':<12} {'AreaCode':<10} {'ServerProgID':<30} {'DisplayName':<25} {'Active'}")
print("-" * 120)

for plant, area, plant_code, area_code, server_progid, display_name, is_active in cur.fetchall():
    print(f"{plant:<15} {area:<15} {plant_code or 'NULL':<12} {area_code or 'NULL':<10} {server_progid or 'NULL':<30} {display_name or 'NULL':<25} {is_active}")

# Now check tag_master to see what server_progids exist there
print("\n" + "="*100)
print("TAG_MASTER SERVER_PROGIDS")
print("="*100)

cur.execute("""
    SELECT DISTINCT server_progid, COUNT(*) as tag_count
    FROM historian_meta.tag_master
    WHERE enabled = true
    GROUP BY server_progid
    ORDER BY tag_count DESC
""")

print(f"\n{'ServerProgID':<40} {'Tag Count'}")
print("-" * 50)
for progid, count in cur.fetchall():
    print(f"{progid or '(NULL)':<40} {count}")

# Check mismatch
print("\n" + "="*100)
print("MISMATCH ANALYSIS")
print("="*100)

cur.execute("""
    SELECT DISTINCT tm.server_progid
    FROM historian_meta.tag_master tm
    WHERE tm.enabled = true
    AND tm.server_progid IS NOT NULL
    AND NOT EXISTS (
        SELECT 1 FROM historian_meta.plants_areas pa
        WHERE pa.server_progid = tm.server_progid
        AND pa.is_active = true
    )
""")

missing = cur.fetchall()
if missing:
    print("\n⚠️  SERVER_PROGIDS in tag_master but NOT in plants_areas:")
    for (progid,) in missing:
        print(f"   - {progid}")
else:
    print("\n✅ All server_progids from tag_master exist in plants_areas")

cur.close()
conn.close()

print("\n" + "="*100)
print("SOLUTION:")
print("="*100)
print("""
The report dropdown shows sources from historian_meta.plants_areas.server_progid
This MUST match the server_progid values in historian_meta.tag_master

To fix:
1. Update plants_areas to include ALL server_progids from tag_master
2. Or update tag_master to use server_progids that exist in plants_areas
3. Ensure plant/area columns in tag_master match plants_areas entries
""")
print("="*100 + "\n")
