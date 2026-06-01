import json, psycopg2

with open('config.json', 'r') as f:
    config = json.load(f)

db = config['database']
conn = psycopg2.connect(host=db['host'], port=db['port'], database=db['database'], user=db['user'], password=db['password'])
cur = conn.cursor()

print("\n" + "="*80)
print("FIXING PLANTS_AREAS TABLE - Removing Invalid Sources")
print("="*80)

# Mark inactive entries that have server_progid not in tag_master
cur.execute("""
    UPDATE historian_meta.plants_areas
    SET is_active = false
    WHERE server_progid IS NOT NULL
    AND server_progid NOT IN (
        SELECT DISTINCT server_progid 
        FROM historian_meta.tag_master 
        WHERE server_progid IS NOT NULL 
        AND enabled = true
    )
    RETURNING plant, area, server_progid
""")

deactivated = cur.fetchall()
if deactivated:
    print("\n✅ Deactivated invalid plants_areas entries:")
    for plant, area, progid in deactivated:
        print(f"   - {plant}/{area} → {progid}")
else:
    print("\n✅ No invalid entries found")

conn.commit()

# Show current active sources
print("\n" + "="*80)
print("ACTIVE REPORT SOURCES (After Fix)")
print("="*80)

cur.execute("""
    SELECT DISTINCT server_progid, COUNT(*) as area_count
    FROM historian_meta.plants_areas
    WHERE is_active = true
    AND server_progid IS NOT NULL
    GROUP BY server_progid
    ORDER BY server_progid
""")

print(f"\n{'Source (server_progid)':<35} {'Areas':<10} {'Tags in DB'}")
print("-" * 60)

for progid, area_count in cur.fetchall():
    # Get tag count
    cur.execute("""
        SELECT COUNT(*) 
        FROM historian_meta.tag_master 
        WHERE server_progid = %s 
        AND enabled = true
    """, (progid,))
    tag_count = cur.fetchone()[0]
    
    print(f"{progid:<35} {area_count:<10} {tag_count}")

print("\n" + "="*80)
print("✅ Report sources are now aligned with tag_master!")
print("="*80 + "\n")

cur.close()
conn.close()
