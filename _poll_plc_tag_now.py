"""
POLL THE PLC TAG NOW - See exactly what value/quality TY1101D returns
This answers: "if PLC tag is polled after disconnection what value it gets?"
"""
import requests
import json
from datetime import datetime

print("=" * 70)
print("LIVE PLC TAG POLL - TY1101D (PLC 192.168.0.20)")
print(f"Current time: {datetime.now().strftime('%H:%M:%S')}")
print("=" * 70)

# 1. Check PLC connection status
print("\n[1] PLC CONNECTION STATUS:")
try:
    resp = requests.get("http://localhost:5001/api/plc/connections", timeout=5)
    if resp.ok:
        data = resp.json()
        connections = data if isinstance(data, list) else data.get('connections', [data])
        for conn in connections:
            plc_id = conn.get('plcId', 'unknown')
            connected = conn.get('isConnected', conn.get('connected'))
            mode = conn.get('mode', 'N/A')
            tag_count = conn.get('tagCount', 0)
            last_update = conn.get('lastUpdateTime', conn.get('lastUpdate', 'N/A'))
            last_error = conn.get('lastError', 'none')
            frozen_ms = conn.get('frozenForMs', 0)
            
            print(f"   PLC ID: {plc_id}")
            print(f"   Connected: {connected}")
            print(f"   Mode: {mode}")
            print(f"   Tag count: {tag_count}")
            print(f"   Frozen for: {frozen_ms} ms")
            print(f"   Last update: {last_update}")
            print(f"   Last error: {last_error}")
    else:
        print(f"   HTTP {resp.status_code}: {resp.text[:200]}")
except Exception as e:
    print(f"   ERROR: {e}")

# 2. Poll TY1101D value directly from PLC pool
print("\n[2] TY1101D LIVE VALUE FROM PLC POOL:")
try:
    resp = requests.get("http://localhost:5001/api/plc/values?tags=TY1101D", timeout=5)
    if resp.ok:
        data = resp.json()
        values = data if isinstance(data, list) else data.get('values', data.get('tags', []))
        if values:
            for v in values:
                print(f"   Tag: {v.get('tagName', v.get('address'))}")
                print(f"   Value: {v.get('value')}")
                print(f"   Quality: {v.get('quality')}")
                print(f"   Timestamp: {v.get('timestamp')}")
                print(f"   CachedAt: {v.get('cachedAt')}")
        else:
            print(f"   No values returned. Raw: {json.dumps(data)[:300]}")
    else:
        print(f"   HTTP {resp.status_code}: {resp.text[:200]}")
except Exception as e:
    print(f"   ERROR: {e}")

# 3. Get ALL PLC values to see if they're changing
print("\n[3] SAMPLE OF PLC TAG VALUES (to check if changing):")
try:
    resp = requests.get("http://localhost:5001/api/plc/values", timeout=5)
    if resp.ok:
        data = resp.json()
        values = data if isinstance(data, list) else data.get('values', data.get('tags', []))
        print(f"   Total PLC tags in pool: {len(values)}")
        
        # Show first 5 with quality
        for v in values[:5]:
            name = v.get('tagName', v.get('address', '?'))
            val = v.get('value')
            qual = v.get('quality')
            print(f"   • {name:<20} = {val:<15} quality={qual}")
        
        # Count quality distribution
        quality_counts = {}
        for v in values:
            q = str(v.get('quality', 'unknown'))
            quality_counts[q] = quality_counts.get(q, 0) + 1
        
        print(f"\n   QUALITY DISTRIBUTION:")
        for q, count in sorted(quality_counts.items()):
            print(f"   • {q}: {count} tags")
    else:
        print(f"   HTTP {resp.status_code}")
except Exception as e:
    print(f"   ERROR: {e}")

print("\n" + "=" * 70)
print("DIAGNOSIS:")
print("=" * 70)
print("""
KEY QUESTIONS ANSWERED:
1. Is PLC marked Connected or Disconnected?
   → If Connected=True but PLC is physically off → driver returning stale reads
   → If Connected=False → MarkPlcDisconnected worked, quality should be Uncertain

2. What quality does TY1101D show?
   → Good = BUG (driver returning cached value as if fresh)
   → Uncertain/Bad = CORRECT (disconnect detected)

3. Are values changing?
   → If quality=Good AND values changing → PLC still responding (not truly disconnected)
   → If quality=Uncertain AND values frozen → CORRECT behavior
""")
