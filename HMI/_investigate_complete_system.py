import json, psycopg2

with open('config.json', 'r') as f:
    config = json.load(f)

db = config['database']
conn = psycopg2.connect(host=db['host'], port=db['port'], database=db['database'], user=db['user'], password=db['password'])
cur = conn.cursor()

print("\n" + "="*100)
print("COMPLETE DATABASE INVESTIGATION - ALL TABLES AND LINKS")
print("="*100)

# 1. Check plants_areas structure
print("\n[1] PLANTS_AREAS TABLE STRUCTURE:")
print("-" * 100)
cur.execute("""
    SELECT column_name, data_type, is_nullable, column_default
    FROM information_schema.columns 
    WHERE table_schema='historian_meta' AND table_name='plants_areas'
    ORDER BY ordinal_position
""")
for col, dtype, nullable, default in cur.fetchall():
    print(f"  {col:<25} {dtype:<20} NULL: {nullable:<5} Default: {default or 'None'}")

# 2. Check tag_master relevant columns
print("\n[2] TAG_MASTER RELEVANT COLUMNS:")
print("-" * 100)
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema='historian_meta' AND table_name='tag_master'
    AND column_name IN ('tag_id', 'plant', 'area', 'server_progid', 'plc_ip_address', 'plc_port', 'plc_protocol', 'enabled')
    ORDER BY ordinal_position
""")
for col, dtype in cur.fetchall():
    print(f"  {col:<25} {dtype:<20}")

# 3. Check user_area_assignments
print("\n[3] USER_AREA_ASSIGNMENTS TABLE:")
print("-" * 100)
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema='historian_meta' AND table_name='user_area_assignments'
    ORDER BY ordinal_position
""")
cols = []
for col, dtype in cur.fetchall():
    cols.append(col)
    print(f"  {col:<25} {dtype:<20}")

# 4. Check current data links
print("\n[4] CURRENT DATA RELATIONSHIPS:")
print("-" * 100)

# Tags by plant/area/server_progid
cur.execute("""
    SELECT 
        server_progid,
        plant,
        area,
        COUNT(*) as tag_count
    FROM historian_meta.tag_master
    WHERE enabled = true AND server_progid IS NOT NULL
    GROUP BY server_progid, plant, area
    ORDER BY server_progid, plant, area
""")
print("\n  TAG_MASTER (server_progid/plant/area combinations):")
tag_combos = cur.fetchall()
for progid, plant, area, count in tag_combos:
    print(f"    {progid:<35} {plant:<15} {area:<15} {count:>5} tags")

# Plants_areas entries
cur.execute("""
    SELECT 
        server_progid,
        plant,
        area,
        is_active,
        id
    FROM historian_meta.plants_areas
    WHERE server_progid IS NOT NULL
    ORDER BY server_progid, plant, area
""")
print("\n  PLANTS_AREAS (configured entries):")
pa_entries = cur.fetchall()
for progid, plant, area, active, pa_id in pa_entries:
    print(f"    ID:{pa_id:<5} {progid:<35} {plant:<15} {area:<15} {'ACTIVE' if active else 'INACTIVE'}")

# User assignments
if 'area_id' in cols:
    cur.execute("""
        SELECT 
            ua.user_id,
            u.username,
            pa.server_progid,
            pa.plant,
            pa.area
        FROM historian_meta.user_area_assignments ua
        JOIN historian_meta.users u ON u.user_id = ua.user_id
        JOIN historian_meta.plants_areas pa ON pa.id = ua.area_id
        WHERE u.is_active = true
        ORDER BY u.username, pa.server_progid
    """)
    print("\n  USER_AREA_ASSIGNMENTS (who can see what):")
    for user_id, username, progid, plant, area in cur.fetchall():
        print(f"    {username:<20} → {progid:<35} {plant}/{area}")

# 5. Check foreign keys
print("\n[5] FOREIGN KEY RELATIONSHIPS:")
print("-" * 100)
cur.execute("""
    SELECT
        tc.table_schema,
        tc.table_name,
        kcu.column_name,
        ccu.table_schema AS foreign_table_schema,
        ccu.table_name AS foreign_table_name,
        ccu.column_name AS foreign_column_name
    FROM information_schema.table_constraints AS tc
    JOIN information_schema.key_column_usage AS kcu
        ON tc.constraint_name = kcu.constraint_name
        AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage AS ccu
        ON ccu.constraint_name = tc.constraint_name
        AND ccu.table_schema = tc.constraint_schema
    WHERE tc.constraint_type = 'FOREIGN KEY'
    AND tc.table_schema = 'historian_meta'
    AND (tc.table_name = 'plants_areas' OR tc.table_name = 'user_area_assignments' OR tc.table_name = 'tag_master')
    ORDER BY tc.table_name, kcu.column_name
""")
fks = cur.fetchall()
if fks:
    for schema, table, col, fk_schema, fk_table, fk_col in fks:
        print(f"  {table}.{col} → {fk_table}.{fk_col}")
else:
    print("  No foreign keys found (tables may use soft links)")

# 6. Identify mismatches
print("\n[6] MISMATCH ANALYSIS:")
print("-" * 100)

# Tags without plants_areas entry
cur.execute("""
    SELECT DISTINCT tm.server_progid, tm.plant, tm.area
    FROM historian_meta.tag_master tm
    WHERE tm.enabled = true
    AND tm.server_progid IS NOT NULL
    AND NOT EXISTS (
        SELECT 1 FROM historian_meta.plants_areas pa
        WHERE pa.server_progid = tm.server_progid
        AND pa.plant = tm.plant
        AND pa.area = tm.area
    )
""")
missing_pa = cur.fetchall()
if missing_pa:
    print("\n  ⚠️  Tags without plants_areas entry:")
    for progid, plant, area in missing_pa:
        print(f"    {progid} / {plant} / {area}")
else:
    print("\n  ✅ All tag combinations exist in plants_areas")

# Plants_areas without tags
cur.execute("""
    SELECT pa.id, pa.server_progid, pa.plant, pa.area, pa.is_active
    FROM historian_meta.plants_areas pa
    WHERE pa.server_progid IS NOT NULL
    AND NOT EXISTS (
        SELECT 1 FROM historian_meta.tag_master tm
        WHERE tm.server_progid = pa.server_progid
        AND tm.plant = pa.plant
        AND tm.area = pa.area
        AND tm.enabled = true
    )
""")
orphan_pa = cur.fetchall()
if orphan_pa:
    print("\n  ⚠️  Plants_areas entries without tags:")
    for pa_id, progid, plant, area, active in orphan_pa:
        print(f"    ID:{pa_id} {progid} / {plant} / {area} ({'ACTIVE' if active else 'INACTIVE'})")
else:
    print("\n  ✅ All plants_areas entries have corresponding tags")

print("\n" + "="*100)
print("SOLUTION REQUIRED:")
print("="*100)
print("""
Based on investigation, we need to:

1. CREATE/UPDATE sync mechanism between tag_master and plants_areas
   - When tag added with new server_progid/plant/area → auto-create plants_areas entry
   - When tag disabled/deleted → mark plants_areas as inactive if no more tags

2. FIX user_area_assignments to link correctly
   - Use area_id (FK to plants_areas.id) or
   - Use plant/area string matching

3. ENSURE report dropdown queries only ACTIVE plants_areas with tags

4. ADD "Sync from Tags" button functionality (already exists in UI)
   - Button should call sync function to update plants_areas from tag_master
""")
print("="*100 + "\n")

cur.close()
conn.close()
