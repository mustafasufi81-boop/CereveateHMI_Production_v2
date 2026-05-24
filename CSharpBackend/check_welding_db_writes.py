import psycopg2
from datetime import datetime, timedelta

conn = psycopg2.connect(
    host='localhost',
    database='Cereveate',
    user='cereveate',
    password='cereveate@222'
)

cur = conn.cursor()

print("\n" + "="*80)
print("CHECKING WELDING DATA IN DATABASE")
print("="*80)

# Check welding tags in last 5 minutes
welding_tags = ['Welding_Current_A', 'Welding_Voltage_V', 'Arc', 'Power', 'Pipe_Id', 'Joint_Id', 'Welder_id', 'WPS_ID', 'sim_step']

print("\n1. Welding tags in historian_timeseries (last 5 minutes):")
cur.execute("""
    SELECT tag_id, COUNT(*), MAX(opc_timestamp) as last_write 
    FROM historian_raw.historian_timeseries 
    WHERE tag_id = ANY(%s)
      AND opc_timestamp > NOW() - INTERVAL '5 minutes'
    GROUP BY tag_id 
    ORDER BY tag_id
""", (welding_tags,))

rows = cur.fetchall()
if rows:
    for r in rows:
        print(f"   {r[0]:25s} | Records: {r[1]:6d} | Last: {r[2]}")
else:
    print("   ❌ NO WELDING DATA IN DATABASE (last 5 minutes)")

# Check if tags are in tag_master and enabled
print("\n2. Welding tags in tag_master:")
cur.execute("""
    SELECT tag_id, enabled, server_progid, plc_ip_address, data_type
    FROM historian_meta.tag_master 
    WHERE tag_id = ANY(%s)
    ORDER BY tag_id
""", (welding_tags,))

rows = cur.fetchall()
if rows:
    for r in rows:
        tag_id, enabled, progid, ip, dtype = r
        status = "✅ ENABLED" if enabled else "❌ DISABLED"
        print(f"   {status} | {tag_id:25s} | Server: {progid:20s} | IP: {ip} | Type: {dtype}")
else:
    print("   ❌ NO WELDING TAGS IN TAG_MASTER")

# Check recent writes for ANY tags (to see if historian is working)
print("\n3. Recent historian writes (all tags, last 1 minute):")
cur.execute("""
    SELECT tag_id, COUNT(*), MAX(opc_timestamp) 
    FROM historian_raw.historian_timeseries 
    WHERE opc_timestamp > NOW() - INTERVAL '1 minute'
    GROUP BY tag_id 
    ORDER BY COUNT(*) DESC
    LIMIT 10
""")

rows = cur.fetchall()
if rows:
    print(f"   Total unique tags with recent writes: {len(rows)}")
    for r in rows[:5]:
        print(f"   {r[0]:30s} | Records: {r[1]:4d} | Last: {r[2]}")
else:
    print("   ❌ NO RECENT WRITES AT ALL - HISTORIAN SERVICE NOT WORKING!")

cur.close()
conn.close()

print("\n" + "="*80)
print("DIAGNOSIS:")
print("="*80)
print("""
If NO welding data in section 1:
→ Welding tags are NOT being written to historian database

If section 2 shows tags disabled or missing progid/IP:
→ Tag configuration issue

If section 3 shows NO recent writes:
→ Historian ingest service is NOT running or broken
""")
print("="*80)
