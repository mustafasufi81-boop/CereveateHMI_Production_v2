import json, psycopg2

with open('config.json', 'r') as f:
    config = json.load(f)

db = config['database']
conn = psycopg2.connect(host=db['host'], port=db['port'], database=db['database'], user=db['user'], password=db['password'])
cur = conn.cursor()

print("\n" + "="*80)
print("TAG_MASTER DATABASE ANALYSIS")
print("="*80)

# Check columns
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema='historian_meta' AND table_name='tag_master'
    ORDER BY ordinal_position
""")
print("\n[1] TAG_MASTER COLUMNS:")
for col, dtype in cur.fetchall():
    print(f"  - {col}: {dtype}")

# Count total
cur.execute("SELECT COUNT(*) FROM historian_meta.tag_master WHERE enabled=true")
total = cur.fetchone()[0]
print(f"\n[2] TOTAL ENABLED TAGS: {total}")

# Group by server_progid
cur.execute("""
    SELECT server_progid, COUNT(*) as cnt
    FROM historian_meta.tag_master 
    WHERE enabled=true
    GROUP BY server_progid
    ORDER BY cnt DESC
""")
print("\n[3] GROUPED BY SERVER_PROGID:")
for progid, cnt in cur.fetchall():
    print(f"  {progid or '(NULL)'}: {cnt} tags")

# Check if NULL server_progid is the problem
cur.execute("""
    SELECT COUNT(*) 
    FROM historian_meta.tag_master 
    WHERE enabled=true AND server_progid IS NULL
""")
null_count = cur.fetchone()[0]
if null_count > 0:
    print(f"\n⚠️  WARNING: {null_count} tags have NULL server_progid!")
    print("   These tags WILL NOT be loaded by C# backend!")

# Check if plc_ip_address is missing
cur.execute("""
    SELECT COUNT(*) 
    FROM historian_meta.tag_master 
    WHERE enabled=true AND (plc_ip_address IS NULL OR plc_ip_address = '')
""")
no_ip = cur.fetchone()[0]
if no_ip > 0:
    print(f"\n⚠️  WARNING: {no_ip} tags have NULL/empty plc_ip_address!")
    print("   These tags WILL NOT be loaded by C# backend!")

# Show sample tags
cur.execute("""
    SELECT tag_id, tag_name, server_progid, plc_protocol, plc_ip_address, plc_port
    FROM historian_meta.tag_master
    WHERE enabled=true
    ORDER BY server_progid, tag_id
    LIMIT 10
""")
print("\n[4] SAMPLE TAGS (first 10):")
for tag_id, tag_name, progid, protocol, ip, port in cur.fetchall():
    print(f"  {tag_id}: {progid or '(NULL)'} → {protocol}://{ip}:{port}")

print("\n" + "="*80)
print("DIAGNOSIS:")
print("="*80)

# Final diagnosis
cur.execute("""
    SELECT COUNT(*) 
    FROM historian_meta.tag_master 
    WHERE enabled=true 
    AND server_progid IS NOT NULL 
    AND plc_ip_address IS NOT NULL
""")
valid_tags = cur.fetchone()[0]

print(f"\n✅ Tags that SHOULD load: {valid_tags}")
print(f"❌ Tags that WON'T load: {total - valid_tags}")

if valid_tags == 0:
    print("\n🔴 CRITICAL PROBLEM:")
    print("   NO tags have both server_progid AND plc_ip_address!")
    print("   C# backend cannot load ANY tags from database!")
    print("\n   SOLUTION: Update tag_master to fill in:")
    print("   - server_progid (e.g., 'Rockwel_PLC_001')")
    print("   - plc_ip_address (e.g., '192.168.0.20')")
    print("   - plc_port (e.g., 44818)")
    print("   - plc_protocol (e.g., 'Rockwell')")
elif valid_tags < total:
    print(f"\n⚠️  {total - valid_tags} tags are missing server_progid or plc_ip_address")

print("\n" + "="*80 + "\n")

cur.close()
conn.close()
