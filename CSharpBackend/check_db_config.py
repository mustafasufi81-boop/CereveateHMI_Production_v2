"""
Check database configuration for welding tags
"""
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

print("\n" + "="*120)
print("DATABASE CONFIGURATION CHECK FOR WELDING TAGS")
print("="*120)

cur.execute("""
    SELECT tag_id, tag_name, data_type, enabled, 
           plc_ip_address, plc_port, plc_protocol, plc_slot, 
           server_progid, plc_polling_interval_ms
    FROM historian_meta.tag_master
    WHERE tag_id LIKE '%Weld%' OR tag_id LIKE '%Pipe%' OR tag_id LIKE '%Joint%' 
       OR tag_id LIKE '%WPS%' OR tag_id LIKE '%Welder%' OR tag_id LIKE '%Sim%'
       OR tag_id = 'Arc' OR tag_id = 'Power'
    ORDER BY tag_id
""")

print(f"\n{'Tag ID':<25} {'Enabled':<8} {'Type':<10} {'IP:Port':<20} {'Slot':<6} {'Server':<20} {'Poll(ms)':<10}")
print("-" * 120)

rows = cur.fetchall()
for row in rows:
    tag_id, tag_name, dtype, enabled, ip, port, proto, slot, server, poll = row
    status = "✅" if enabled else "❌"
    ip_port = f"{ip}:{port}" if ip else "N/A"
    slot_str = str(slot) if slot is not None else "NULL"
    print(f"{tag_id:<25} {status:<8} {dtype:<10} {ip_port:<20} {slot_str:<6} {server:<20} {poll or 'N/A':<10}")

print("\n" + "="*120)
print("CONFIGURATION ISSUES CHECK:")
print("="*120)

issues = []

for row in rows:
    tag_id, tag_name, dtype, enabled, ip, port, proto, slot, server, poll = row
    
    if not enabled:
        issues.append(f"❌ {tag_id}: Disabled")
    
    if not ip:
        issues.append(f"❌ {tag_id}: Missing PLC IP address")
    
    if not server:
        issues.append(f"❌ {tag_id}: Missing server_progid")
    
    if slot is None:
        issues.append(f"⚠️  {tag_id}: plc_slot is NULL (should be 0 or 1)")

if issues:
    for issue in issues:
        print(issue)
else:
    print("✅ No configuration issues found!")

cur.close()
conn.close()

print("\n" + "="*120)
