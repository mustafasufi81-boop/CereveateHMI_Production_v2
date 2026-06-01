"""
SIMPLE TEST: Is C# PLC Pool Data Stale?

Directly calls http://localhost:5001/api/plc/values 
and checks age_ms and computedQuality for PY1105B

No database, no login - just raw C# PLC pool check
"""
import requests
from datetime import datetime

print("=" * 80)
print("CHECKING C# PLC POOL - IS IT STALE?")
print("=" * 80)

# Tags we care about
TAGS_OF_INTEREST = ["PY1105B", "PY1105A", "PY1102B", "FY1100", "AY1102"]

try:
    print("\nCalling C# API: http://localhost:5001/api/plc/values")
    response = requests.get("http://localhost:5001/api/plc/values", timeout=5)
    
    if response.status_code != 200:
        print(f"❌ Failed: HTTP {response.status_code}")
        print(response.text)
        exit(1)
    
    data = response.json()
    tags = data.get('tags', [])
    
    print(f"\nTotal tags in C# PLC pool: {len(tags)}")
    print("\n" + "=" * 80)
    print(f"{'Tag':<15} {'Value':<10} {'Age (ms)':<12} {'Quality':<15} {'Status'}")
    print("=" * 80)
    
    stale_count = 0
    for tag in tags:
        tag_name = tag.get('tagName', 'Unknown')
        
        # Skip if not in our interest list
        if tag_name not in TAGS_OF_INTEREST:
            continue
            
        value = tag.get('value', 0)
        age_ms = tag.get('age_ms') or tag.get('ageMs') or 0
        quality = tag.get('computedQuality') or tag.get('quality', 'Unknown')
        timestamp = tag.get('timestamp', '')
        
        # Determine if stale
        is_stale = age_ms > 10000  # Stale if older than 10 seconds
        status = "🔴 STALE" if is_stale else "✅ FRESH"
        
        if is_stale:
            stale_count += 1
        
        print(f"{tag_name:<15} {value:<10.3f} {age_ms:<12} {quality:<15} {status}")
        if timestamp:
            print(f"{'':15} Timestamp: {timestamp}")
    
    print("=" * 80)
    
    if stale_count > 0:
        print(f"\n❌ PROBLEM FOUND: {stale_count} tag(s) are STALE (age > 10 seconds)")
        print("\nThis means PlcDataLoggingService (EtherNet/IP worker) is NOT refreshing the pool!")
    else:
        print(f"\n✅ ALL TAGS FRESH (age < 10 seconds)")
        print("\nPlcDataLoggingService is working correctly.")
    
    # Also check PLC worker connection status
    print("\n" + "=" * 80)
    print("CHECKING PLC WORKER CONNECTION STATUS")
    print("=" * 80)
    
    response2 = requests.get("http://localhost:5001/api/plc/connections", timeout=5)
    conn_data = response2.json()
    
    for conn in conn_data.get('connections', []):
        plc_id = conn.get('plcId', 'Unknown')
        is_connected = conn.get('isConnected', False)
        state = conn.get('state', 'Unknown')
        tag_count = conn.get('tagCount', 0)
        
        print(f"\nPLC: {plc_id}")
        print(f"  Connected: {is_connected}")
        print(f"  State: {state}")
        print(f"  Tag Count: {tag_count}")
        
        if not is_connected:
            print(f"  ❌ NOT CONNECTED - This is why pool is stale!")

except requests.exceptions.RequestException as e:
    print(f"\n❌ Connection Error: {e}")
    print("\nIs the C# backend running? (OpcDaWebBrowser.exe on port 5001)")
except Exception as e:
    print(f"\n❌ Error: {e}")

print("\n" + "=" * 80)
