import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Automation_DB",
    user="cereveate",
    password="cereveate@222"
)
cur = conn.cursor()

print("=" * 70)
print("TAG SOURCE ANALYSIS - TY1101D")
print("=" * 70)

# Get TY1101D info
cur.execute("""
    SELECT 
        tag_id,
        tag_name,
        server_progid,
        plc_ip_address,
        description
    FROM historian_meta.tag_master
    WHERE tag_id ILIKE '%TY1101D%'
""")

row = cur.fetchone()
if row:
    tag_id, tag_name, progid, plc_ip, desc = row
    print(f"\nTag ID: {tag_id}")
    print(f"Tag Name: {tag_name}")
    print(f"ProgID: {progid}")
    print(f"PLC IP: {plc_ip}")
    print(f"Description: {desc}")
    
    if plc_ip and str(plc_ip).strip():
        print(f"\n🔴 SOURCE: PLC (IP={plc_ip})")
        print("   This tag should NOT raise alarms after PLC disconnect at 22:40!")
    else:
        print(f"\n🟢 SOURCE: OPC DA")
        print("   Normal behavior - OPC DA still connected")

# Check all tags that raised alarms after 22:40
print("\n" + "=" * 70)
print("ALL TAGS WITH ALARMS AFTER 22:40 - SOURCE BREAKDOWN")
print("=" * 70)

cur.execute("""
    SELECT 
        he.tag_id,
        tm.plc_ip_address,
        tm.server_progid,
        COUNT(*) as event_count
    FROM historian_raw.historian_events he
    LEFT JOIN historian_meta.tag_master tm ON he.tag_id = tm.tag_id
    WHERE he.time > '2026-05-30 22:40:00'
    GROUP BY he.tag_id, tm.plc_ip_address, tm.server_progid
    ORDER BY event_count DESC
    LIMIT 30
""")

plc_count = 0
opc_count = 0

print(f"\n{'Tag':<25} {'Source':<15} {'ProgID/PLC':<40} {'Events':<8}")
print("-" * 90)

for tag, plc_ip, progid, count in cur.fetchall():
    if plc_ip and str(plc_ip).strip():
        source = "🔴 PLC"
        source_detail = f"PLC={plc_ip}"
        plc_count += count
    else:
        source = "🟢 OPC DA"
        source_detail = (progid or "NULL")[:38]
        opc_count += count
    
    print(f"{tag:<25} {source:<15} {source_detail:<40} {count:<8}")

print("\n" + "=" * 70)
print("SUMMARY:")
print("=" * 70)
print(f"PLC tags (should be FROZEN):  {plc_count} alarm events")
print(f"OPC DA tags (can fluctuate):  {opc_count} alarm events")

if plc_count > 0:
    print(f"\n❌ BUG: {plc_count} alarm events from PLC tags after disconnect!")
    print("   AlarmEvaluationService is not checking quality correctly")
else:
    print(f"\n✅ OK: All alarms are from OPC DA (still connected)")

conn.close()
