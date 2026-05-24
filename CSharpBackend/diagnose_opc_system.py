"""
Comprehensive OPC System Diagnostic
Checks all components: Config, Database, OPC Connection, Pool, Services
"""
import requests
import json
import psycopg2

API_BASE = "http://localhost:5001"

print("\n" + "="*90)
print("🔍 COMPREHENSIVE OPC SYSTEM DIAGNOSTIC")
print("="*90)

# 1. Check logging-config.json
print("\n1️⃣  Logging Configuration (logging-config.json):")
try:
    with open('logging-config.json', 'r') as f:
        config = json.load(f)
        print(f"   ✅ Config file found")
        print(f"   IsEnabled: {config.get('IsEnabled')}")
        print(f"   ServerProgId: {config.get('ServerProgId')}")
        print(f"   ServerHost: {config.get('ServerHost')}")
        print(f"   Selected Tags (Parquet): {len(config.get('SelectedTags', []))}")
        print(f"   Logging Interval: {config.get('LoggingIntervalMs')}ms")
        print(f"   OPC Polling Interval: {config.get('PerformanceIntervals', {}).get('OpcPollingIntervalMs')}ms")
except Exception as e:
    print(f"   ❌ Cannot read config: {e}")

# 2. Check Database Mappings
print("\n2️⃣  Database Tag Mappings (historian_meta.tag_master):")
try:
    conn = psycopg2.connect(
        host="localhost",
        database="Cereveate",
        user="cereveate",
        password="cereveate@222"
    )
    cursor = conn.cursor()
    
    # Count enabled tags
    cursor.execute("SELECT COUNT(*) FROM historian_meta.tag_master WHERE enabled = true")
    enabled_count = cursor.fetchone()[0]
    
    # Get sample tags
    cursor.execute("""
        SELECT tag_id, tag_name, db_logging_interval_ms 
        FROM historian_meta.tag_master 
        WHERE enabled = true 
        ORDER BY tag_id 
        LIMIT 5
    """)
    sample_tags = cursor.fetchall()
    
    # Check for Saw-toothed tag
    cursor.execute("""
        SELECT tag_id, tag_name, enabled 
        FROM historian_meta.tag_master 
        WHERE tag_id LIKE '%Saw-toothed%'
    """)
    saw_tag = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    print(f"   ✅ Database accessible")
    print(f"   Enabled Mappings: {enabled_count}")
    
    if sample_tags:
        print(f"\n   📋 Sample mapped tags:")
        for tag in sample_tags:
            print(f"      - {tag[0]} (interval: {tag[2]}ms)")
    
    if saw_tag:
        print(f"\n   🎯 Target Tag Found:")
        print(f"      Tag ID: {saw_tag[0]}")
        print(f"      Tag Name: {saw_tag[1]}")
        print(f"      Enabled: {saw_tag[2]}")
    else:
        print(f"\n   ⚠️  'Saw-toothed Waves.Int2' NOT in database mappings!")
        print(f"      You need to add it to historian_meta.tag_master table")
        
except Exception as e:
    print(f"   ❌ Database error: {e}")

# 3. Check OPC Connection Status
print("\n3️⃣  OPC Connection Status:")
try:
    response = requests.get(f"{API_BASE}/api/opc/status", timeout=2)
    if response.status_code == 200:
        status = response.json()
        print(f"   ✅ API Reachable")
        print(f"   Connected: {status.get('connected')}")
        print(f"   Server: {status.get('serverName')}")
        print(f"   Tag Count in Pool: {status.get('tagCount')}")
        print(f"   Last Update: {status.get('lastUpdate')}")
    else:
        print(f"   ❌ Status check failed: {response.status_code}")
except Exception as e:
    print(f"   ❌ Cannot reach OPC service: {e}")

# 4. Check Tag Pool Content
print("\n4️⃣  Tag Values Pool:")
try:
    response = requests.get(f"{API_BASE}/api/opc/values", timeout=2)
    if response.status_code == 200:
        data = response.json()
        tags = data.get('tags', [])
        
        print(f"   ✅ Pool accessible")
        print(f"   Total Tags: {len(tags)}")
        print(f"   Last Update: {data.get('lastUpdate')}")
        
        if len(tags) > 0:
            print(f"\n   📋 Tags currently in pool:")
            for i, tag in enumerate(tags[:10]):
                tag_id = tag.get('tagId') or tag.get('TagId')
                value = tag.get('value') or tag.get('Value')
                print(f"      {i+1}. {tag_id}: {value}")
            
            if len(tags) > 10:
                print(f"      ... and {len(tags) - 10} more")
            
            # Check if Saw-toothed is in pool
            saw_in_pool = any('Saw-toothed' in (tag.get('tagId', '') or tag.get('TagId', '')) for tag in tags)
            if saw_in_pool:
                print(f"\n   ✅ 'Saw-toothed Waves.Int2' IS IN POOL!")
            else:
                print(f"\n   ⚠️  'Saw-toothed Waves.Int2' NOT in pool")
        else:
            print(f"\n   ⚠️  Pool is EMPTY - no tags being monitored")
            print(f"\n   💡 Possible reasons:")
            print(f"      1. DataLoggingService not running")
            print(f"      2. OPC connection not established")
            print(f"      3. No tags in SelectedTags OR database mappings")
            print(f"      4. C# service just started (wait a few seconds)")
    else:
        print(f"   ❌ Cannot access pool: {response.status_code}")
except Exception as e:
    print(f"   ❌ Pool check error: {e}")

# 5. Summary and Recommendations
print("\n" + "="*90)
print("📊 DIAGNOSTIC SUMMARY")
print("="*90)

try:
    # Gather all status
    with open('logging-config.json', 'r') as f:
        config = json.load(f)
    
    conn = psycopg2.connect(
        host="localhost",
        database="Cereveate",
        user="cereveate",
        password="cereveate@222"
    )
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM historian_meta.tag_master WHERE enabled = true")
    db_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM historian_meta.tag_master WHERE tag_id LIKE '%Saw-toothed%' AND enabled = true")
    saw_count = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    
    opc_response = requests.get(f"{API_BASE}/api/opc/status", timeout=2)
    pool_response = requests.get(f"{API_BASE}/api/opc/values", timeout=2)
    
    opc_status = opc_response.json() if opc_response.status_code == 200 else {}
    pool_data = pool_response.json() if pool_response.status_code == 200 else {}
    pool_tags = len(pool_data.get('tags', []))
    
    config_enabled = config.get('IsEnabled', False)
    config_has_server = bool(config.get('ServerProgId'))
    opc_connected = opc_status.get('connected', False)
    
    print(f"Config Enabled:        {config_enabled}")
    print(f"Server Configured:     {config_has_server} ({config.get('ServerProgId')})")
    print(f"OPC Connected:         {opc_connected}")
    print(f"DB Mappings:           {db_count}")
    print(f"Saw-toothed in DB:     {'YES' if saw_count > 0 else 'NO'}")
    print(f"Tags in Pool:          {pool_tags}")
    
    # Determine issue
    if pool_tags > 0:
        saw_in_pool = any('Saw-toothed' in (t.get('tagId', '') or t.get('TagId', '')) 
                         for t in pool_data.get('tags', []))
        if saw_in_pool:
            print(f"\n✅ SYSTEM READY!")
            print(f"   Run: python test_single_tag_polling.py")
        else:
            print(f"\n⚠️  Pool has tags but not 'Saw-toothed Waves.Int2'")
            if saw_count == 0:
                print(f"\n💡 SOLUTION: Add tag to database:")
                print(f"   INSERT INTO historian_meta.tag_master")
                print(f"   (tag_id, tag_name, data_type, enabled)")
                print(f"   VALUES ('Saw-toothed Waves.Int2', 'Saw-toothed Int2', 'Int16', true);")
            else:
                print(f"\n💡 Tag is in DB but not in pool - restart C# service")
    else:
        print(f"\n❌ POOL IS EMPTY")
        if not config_enabled:
            print(f"\n💡 SOLUTION: Enable logging in logging-config.json:")
            print(f"   Set 'IsEnabled': true")
        elif not config_has_server:
            print(f"\n💡 SOLUTION: Set server in logging-config.json:")
            print(f"   'ServerProgId': 'Matrikon.OPC.Simulation.1'")
        elif not opc_connected:
            print(f"\n💡 SOLUTION: OPC not connected - check C# service logs")
        elif db_count == 0 and len(config.get('SelectedTags', [])) == 0:
            print(f"\n💡 SOLUTION: Add tags either:")
            print(f"   A) Add to SelectedTags in logging-config.json, OR")
            print(f"   B) Add to historian_meta.tag_master table")
        else:
            print(f"\n💡 SOLUTION: Restart C# service (dotnet run)")
            print(f"   Wait 5-10 seconds for DataLoggingService to initialize")
            
except Exception as e:
    print(f"❌ Summary failed: {e}")

print("="*90 + "\n")
