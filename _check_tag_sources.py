"""
Check which tags are from PLC vs OPC DA
Show ProgID to identify the source
"""
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Automation_DB",
    user="cereveate",
    password="cereveate@222"
)
cur = conn.cursor()

print("="*70)
print("TAG SOURCE INVESTIGATION - PLC vs OPC DA")
print("="*70)

# Get TY1101D configuration
print("\n[1] TY1101D TAG CONFIGURATION:")
cur.execute("""
    SELECT 
        tag_name,
        item_id,
        server_prog_id,
        plc_id,
        description
    FROM historian_raw.tags
    WHERE tag_name ILIKE '%TY1101D%' OR item_id ILIKE '%TY1101D%'
""")

tags = cur.fetchall()
if tags:
    for row in tags:
        name, item_id, prog_id, plc_id, desc = row
        print(f"\n   Tag: {name}")
        print(f"   ItemID: {item_id}")
        print(f"   ProgID: {prog_id}")
        print(f"   PLC ID: {plc_id}")
        print(f"   Desc: {desc}")
        
        if plc_id and plc_id.strip():
            print(f"\n   🔵 SOURCE: PLC (ID={plc_id}) - DISCONNECTED SINCE 22:40")
        else:
            print(f"\n   🟢 SOURCE: OPC DA ({prog_id}) - STILL RUNNING")
else:
    print("   ❌ Tag not found in database")

# Check recent alarms to see which tags are raising
print("\n" + "="*70)
print("[2] RECENT ALARM TAGS (last 10 minutes):")
print("="*70)

cur.execute("""
    SELECT DISTINCT
        he.tag_id,
        t.server_prog_id,
        t.plc_id,
        COUNT(*) as event_count
    FROM historian_raw.historian_events he
    LEFT JOIN historian_raw.tags t ON he.tag_id = t.tag_name OR he.tag_id = t.item_id
    WHERE he.time > NOW() - INTERVAL '10 minutes'
    GROUP BY he.tag_id, t.server_prog_id, t.plc_id
    ORDER BY event_count DESC
    LIMIT 15
""")

recent = cur.fetchall()
print(f"\n{'Tag':<25} {'ProgID':<40} {'PLC':<10} {'Events':<8} {'Source'}")
print("-"*100)

for row in recent:
    tag, prog_id, plc_id, count = row
    prog_str = (prog_id or 'NULL')[:38]
    plc_str = (plc_id or '-')[:8]
    
    if plc_id and plc_id.strip():
        source = "🔴 PLC (DISCONNECTED)"
    else:
        source = "🟢 OPC DA (RUNNING)"
    
    print(f"{tag:<25} {prog_str:<40} {plc_str:<10} {count:<8} {source}")

# Show the exact tags that changed after 22:40
print("\n" + "="*70)
print("[3] TAGS WITH NEW ALARMS AFTER 22:40 (PLC disconnect time):")
print("="*70)

cur.execute("""
    SELECT DISTINCT
        he.tag_id,
        t.server_prog_id,
        t.plc_id,
        MIN(he.time) as first_event,
        COUNT(*) as event_count
    FROM historian_raw.historian_events he
    LEFT JOIN historian_raw.tags t ON he.tag_id = t.tag_name OR he.tag_id = t.item_id
    WHERE he.time > '2026-05-30 22:40:00'
    GROUP BY he.tag_id, t.server_prog_id, t.plc_id
    ORDER BY first_event DESC
    LIMIT 10
""")

post_disconnect = cur.fetchall()
for row in post_disconnect:
    tag, prog_id, plc_id, first_time, count = row
    
    print(f"\n   Tag: {tag}")
    print(f"   ProgID: {prog_id or 'NULL'}")
    print(f"   PLC ID: {plc_id or 'NULL'}")
    print(f"   First alarm: {first_time}")
    print(f"   Event count: {count}")
    
    if plc_id and plc_id.strip():
        print(f"   ❌ BUG: This is PLC tag but alarms raised after PLC disconnect!")
    else:
        print(f"   ✅ OK: This is OPC DA tag (still connected)")

conn.close()

print("\n" + "="*70)
print("SUMMARY:")
print("="*70)
print("""
If tags with plc_id are raising alarms after 22:40:
→ BUG: PLC pool cache is not marking IsStale correctly
→ Need to fix PlcTagValuesPoolService.IsStale check

If only OPC DA tags (ProgID like 'Matrikon.OPC.Simulation') are raising:
→ NORMAL: OPC DA is still connected, those alarms are legitimate
→ TY1101D issue is separate (check if it's PLC or OPC tag)
""")
