"""
Quick diagnostic: Check current OPC connection and tag monitoring state
"""
import requests
import json

API_BASE = "http://localhost:5001"

print("\n" + "="*80)
print("🔍 OPC CONNECTION & TAG MONITORING STATUS")
print("="*80)

# 1. Check OPC Status
print("\n1️⃣  OPC Connection Status:")
try:
    response = requests.get(f"{API_BASE}/api/opc/status", timeout=2)
    if response.status_code == 200:
        status = response.json()
        print(f"   ✅ API Reachable")
        print(f"   Connected: {status.get('connected')}")
        print(f"   Server: {status.get('serverName')}")
        print(f"   Tag Count: {status.get('tagCount')}")
        print(f"   Last Update: {status.get('lastUpdate')}")
        
        if not status.get('connected'):
            print(f"\n   ⚠️  OPC server is NOT connected!")
            print(f"   💡 Open web UI and connect to an OPC server first")
        elif status.get('tagCount') == 0:
            print(f"\n   ⚠️  Connected but NO tags are being monitored!")
            print(f"   💡 You need to add tags to monitor via the web UI")
    else:
        print(f"   ❌ Status check failed: {response.status_code}")
except Exception as e:
    print(f"   ❌ Cannot reach OPC service: {e}")
    print(f"   💡 Make sure C# service is running: dotnet run")
    exit(1)

# 2. Check Tag Values Pool
print("\n2️⃣  Tag Values Pool:")
try:
    response = requests.get(f"{API_BASE}/api/opc/values", timeout=2)
    if response.status_code == 200:
        data = response.json()
        tags = data.get('tags', [])
        
        print(f"   ✅ Pool accessible")
        print(f"   Tag Count: {data.get('count', len(tags))}")
        print(f"   Last Update: {data.get('lastUpdate')}")
        
        if len(tags) > 0:
            print(f"\n   📋 Currently monitored tags:")
            for i, tag in enumerate(tags[:10]):
                tag_id = tag.get('tagId') or tag.get('TagId')
                value = tag.get('value') or tag.get('Value')
                quality = tag.get('quality') or tag.get('Quality')
                print(f"      {i+1}. {tag_id}: {value} ({quality})")
            
            if len(tags) > 10:
                print(f"      ... and {len(tags) - 10} more tags")
                
            print(f"\n   ✅ READY TO TEST! You have {len(tags)} tags to monitor")
            print(f"   🚀 Run: python test_500ms_opc_polling.py")
        else:
            print(f"\n   ⚠️  Pool is EMPTY - no tags are being monitored")
            print(f"\n   💡 HOW TO ADD TAGS:")
            print(f"      1. Open web browser: http://localhost:5001")
            print(f"      2. Navigate to tag browser")
            print(f"      3. Click 'Browse Tags' button")
            print(f"      4. Select tags and click 'Add to Monitor'")
            print(f"      5. Come back and run this script again")
    else:
        print(f"   ❌ Cannot access pool: {response.status_code}")
except Exception as e:
    print(f"   ❌ Error checking pool: {e}")

# 3. Check Historian Tag Mappings (if any)
print("\n3️⃣  Historian Tag Mappings (Database):")
try:
    import psycopg2
    conn = psycopg2.connect(
        host="localhost",
        database="Cereveate",
        user="cereveate",
        password="cereveate@222"
    )
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM historian_meta.tag_master WHERE enabled = true")
    count = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    
    print(f"   ✅ Database accessible")
    print(f"   Enabled mappings: {count}")
    
    if count > 0:
        print(f"   ℹ️  Historian is configured to write {count} tags to database")
    else:
        print(f"   ℹ️  No historian mappings configured (optional for polling test)")
        
except Exception as e:
    print(f"   ⚠️  Database check skipped: {e}")

# Summary
print("\n" + "="*80)
print("📊 SUMMARY")
print("="*80)

try:
    status_response = requests.get(f"{API_BASE}/api/opc/status", timeout=2)
    values_response = requests.get(f"{API_BASE}/api/opc/values", timeout=2)
    
    if status_response.status_code == 200 and values_response.status_code == 200:
        status = status_response.json()
        values = values_response.json()
        tag_count = len(values.get('tags', []))
        
        if status.get('connected') and tag_count > 0:
            print(f"✅ READY TO TEST POLLING!")
            print(f"   - OPC Connected: {status.get('serverName')}")
            print(f"   - Tags Monitored: {tag_count}")
            print(f"\n🚀 Next step: python test_500ms_opc_polling.py")
        elif status.get('connected'):
            print(f"⚠️  PARTIALLY READY")
            print(f"   - OPC Connected: YES")
            print(f"   - Tags Monitored: NO")
            print(f"\n💡 Add tags via web UI: http://localhost:5001")
        else:
            print(f"❌ NOT READY")
            print(f"   - OPC Connected: NO")
            print(f"\n💡 Connect to OPC server via web UI first")
            
except Exception as e:
    print(f"❌ Cannot determine status: {e}")

print("="*80 + "\n")
