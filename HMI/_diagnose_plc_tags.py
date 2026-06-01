import json, psycopg2, requests

with open('config.json', 'r') as f:
    config = json.load(f)

db = config['database']
conn = psycopg2.connect(host=db['host'], port=db['port'], database=db['database'], user=db['user'], password=db['password'])
cur = conn.cursor()

print("\n" + "="*80)
print("PLC TAG CONFIGURATION DIAGNOSIS")
print("="*80)

# 1. Check tags in database
print("\n[1] TAGS IN DATABASE:")
print("-"*80)
cur.execute("""
    SELECT 
        tag_id,
        plant,
        area,
        enabled,
        opc_item_id
    FROM historian_meta.tag_master
    WHERE enabled = true
    ORDER BY plant, area, tag_id
""")
tags = cur.fetchall()
print(f"Total enabled tags: {len(tags)}")

# Group by plant/area
from collections import defaultdict
by_plant = defaultdict(lambda: defaultdict(list))
for tag_id, plant, area, enabled, opc_item in tags:
    by_plant[plant][area].append((tag_id, opc_item))

print("\nBreakdown by Plant/Area:")
for plant, areas in sorted(by_plant.items()):
    for area, tag_list in sorted(areas.items()):
        print(f"  {plant}/{area}: {len(tag_list)} tags")
        for tag_id, opc_item in tag_list[:5]:
            print(f"    - {tag_id} → {opc_item}")
        if len(tag_list) > 5:
            print(f"    ... and {len(tag_list)-5} more")

# 2. Check PLC connections in database
print("\n[2] PLC CONNECTIONS IN DATABASE:")
print("-"*80)
cur.execute("""
    SELECT 
        connection_name,
        protocol,
        ip_address,
        port,
        enabled,
        plant,
        area
    FROM historian_meta.plc_connections
    WHERE enabled = true
""")
conns = cur.fetchall()
print(f"Total enabled connections: {len(conns)}")
for conn_name, protocol, ip, port, enabled, plant, area in conns:
    print(f"  {conn_name}: {protocol}://{ip}:{port} ({plant}/{area})")

# 3. Check C# backend API status
print("\n[3] C# BACKEND PLC GATEWAY STATUS:")
print("-"*80)
try:
    resp = requests.get('http://localhost:5001/api/plc/connections', timeout=5)
    if resp.status_code == 200:
        data = resp.json()
        print(f"API Response: {len(data)} connections")
        for conn in data:
            status = conn.get('status', {})
            print(f"\n  Connection: {conn.get('connectionName')}")
            print(f"    State: {status.get('state')}")
            print(f"    Protocol: {status.get('protocol')}")
            print(f"    Address: {status.get('ipAddress')}:{status.get('port')}")
            print(f"    Items: {status.get('itemCount', 0)}")
            print(f"    Plant/Area: {conn.get('plant')}/{conn.get('area')}")
    else:
        print(f"❌ API error: {resp.status_code}")
except Exception as e:
    print(f"❌ Cannot connect to C# backend: {e}")

# 4. Check what tags are being written to historian
print("\n[4] RECENT DATA COLLECTION:")
print("-"*80)
cur.execute("""
    SELECT 
        metric_name,
        COUNT(*) as records,
        MAX(time) as last_update
    FROM historian_raw.historian_calc_values
    WHERE time >= NOW() - interval '10 minutes'
    GROUP BY metric_name
    ORDER BY last_update DESC
""")
recent = cur.fetchall()
if recent:
    print(f"Tags with data in last 10 minutes: {len(recent)}")
    for metric, count, last_time in recent[:10]:
        print(f"  {metric}: {count} records, last: {last_time}")
else:
    print("❌ NO DATA in last 10 minutes!")

# 5. Check appsettings.json configuration
print("\n[5] C# BACKEND CONFIG:")
print("-"*80)
try:
    with open('../CSharpBackend/appsettings.json', 'r') as f:
        appsettings = json.load(f)
    
    plc_config = appsettings.get('PlcGateway', {})
    print(f"PlcGateway section found: {bool(plc_config)}")
    
    if 'Connections' in plc_config:
        connections = plc_config['Connections']
        print(f"Hardcoded connections in appsettings.json: {len(connections)}")
        for conn in connections:
            print(f"  {conn.get('ConnectionName')}: {conn.get('Protocol')}://{conn.get('IpAddress')}:{conn.get('Port')}")
            items = conn.get('Items', [])
            print(f"    Items: {len(items)}")
            for item in items[:5]:
                print(f"      - {item.get('TagName')} → {item.get('OpcItemId')}")
            if len(items) > 5:
                print(f"      ... and {len(items)-5} more")
    else:
        print("❌ No 'Connections' section in appsettings.json")
        
    # Check if using DB or hardcoded config
    use_db = plc_config.get('UseDatabase', False)
    print(f"\nUseDatabase setting: {use_db}")
    if not use_db:
        print("⚠️  WARNING: Backend is using HARDCODED appsettings.json, NOT database!")
        print("   This is why only 5 tags are connected!")
        
except Exception as e:
    print(f"❌ Cannot read appsettings.json: {e}")

print("\n" + "="*80)
print("DIAGNOSIS SUMMARY:")
print("="*80)
print(f"\n✅ Database has {len(tags)} enabled tags")
print(f"✅ Database has {len(conns)} enabled PLC connections")

if len(recent) < len(tags) / 2:
    print(f"\n⚠️  PROBLEM: Only {len(recent)} tags collecting data")
    print("   Likely cause: C# backend using appsettings.json instead of database")
    print("\n   SOLUTION:")
    print("   1. Check appsettings.json → PlcGateway → UseDatabase = true")
    print("   2. Restart C# backend")
    print("   3. Backend will load all tags from database")

print("\n" + "="*80 + "\n")

cur.close()
conn.close()
