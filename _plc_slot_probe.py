"""
PLC Slot Probe & Data Inspector
================================
Standalone tool to:
  1. Register ROCKWELL_002 (IP 192.168.0.20, port 44818, slot 2)
     into the C# backend via POST /api/plc/add
  2. Wait for it to connect (~10s)
  3. Read and display all tag values from slot 2
  4. Let you change slot number to probe any other slot

Usage:
  python _plc_slot_probe.py                  -> use defaults from screenshot
  python _plc_slot_probe.py --slot 0         -> probe slot 0
  python _plc_slot_probe.py --slot 3         -> probe slot 3
  python _plc_slot_probe.py --ip 192.168.0.X -> probe different IP
  python _plc_slot_probe.py --list           -> just list current PLCs
"""

import sys
import time
import json
import urllib.request
import urllib.error
import argparse

BASE = "http://127.0.0.1:5001"

def call(method, path, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()), e.code
        except Exception:
            return {"error": str(e)}, e.code
    except Exception as e:
        return {"error": str(e)}, 0

def sep(title=""):
    w = 72
    if title:
        pad = (w - len(title) - 2) // 2
        print("=" * pad + f" {title} " + "=" * (w - pad - len(title) - 2))
    else:
        print("=" * w)

def status_icon(v):
    if v is None: return "?"
    if isinstance(v, bool): return "✓" if v else "✗"
    return str(v)

# ─────────────────────────────────────────────────────────────────────────────
# 1. List current PLCs
# ─────────────────────────────────────────────────────────────────────────────
def list_plcs():
    sep("CURRENT PLCs IN SYSTEM")
    data, code = call("GET", "/api/plc/connections")
    if code != 200:
        print(f"  ❌ Cannot reach backend: HTTP {code}  — is OpcDaWebBrowser running?")
        return []
    conns = data.get("connections", [])
    if not conns:
        print("  (no PLCs configured)")
        return []
    for c in conns:
        icon = "🟢" if c.get("isConnected") else "🔴"
        print(f"  {icon}  {c['plcId']:<22} {c.get('protocol',''):<12} "
              f"{c.get('ipAddress',''):<16} port={c.get('port',0)}  "
              f"slot={c.get('slot',0)}  tags={c.get('tagCount',0)}")
    return conns

# ─────────────────────────────────────────────────────────────────────────────
# 2. Add (or update) ROCKWELL_002
# ─────────────────────────────────────────────────────────────────────────────
def add_plc(plc_id, ip, port, slot):
    sep(f"ADDING / UPDATING {plc_id}")
    payload = {
        "plcId":       plc_id,
        "displayName": plc_id,
        "protocol":    "Rockwell",
        "ipAddress":   ip,
        "port":        port,
        "slot":        slot,
        "pollingIntervalMs": 1000,
        "enabled": True,
        "etherNetIpOptions": {
            "path":    f"1,{ip},{slot}",
            "plcType": "ControlLogix"
        }
    }
    print(f"  POST /api/plc/add")
    print(f"  Payload: ip={ip}  port={port}  slot={slot}")
    data, code = call("POST", "/api/plc/add", payload)
    if code in (200, 201):
        print(f"  ✅ Registered — HTTP {code}")
        print(f"     message: {data.get('message','')}")
    elif code == 409:
        print(f"  ℹ️  Already exists (HTTP 409) — will probe existing config")
    else:
        print(f"  ⚠️  HTTP {code}: {data}")
    return code

# ─────────────────────────────────────────────────────────────────────────────
# 3. Wait for PLC to connect
# ─────────────────────────────────────────────────────────────────────────────
def wait_for_connect(plc_id, timeout=25):
    sep(f"WAITING FOR {plc_id} TO CONNECT")
    start = time.time()
    while (elapsed := time.time() - start) < timeout:
        data, _ = call("GET", "/api/plc/connections")
        for c in data.get("connections", []):
            if c.get("plcId") == plc_id:
                icon = "🟢" if c.get("isConnected") else "⏳"
                print(f"  {icon}  [{elapsed:5.1f}s]  connected={c.get('isConnected')}  "
                      f"tags={c.get('tagCount',0)}  error={c.get('lastError') or 'none'}")
                if c.get("isConnected") and c.get("tagCount", 0) > 0:
                    print(f"  ✅ Connected with {c['tagCount']} tags!\n")
                    return True
        time.sleep(2)
    print(f"  ❌ Timed out after {timeout}s — PLC may be offline or unreachable")
    return False

# ─────────────────────────────────────────────────────────────────────────────
# 4. Dump tag values
# ─────────────────────────────────────────────────────────────────────────────
def read_tags(plc_id):
    sep(f"TAG VALUES FROM {plc_id}")
    data, code = call("GET", f"/api/plc/values/{plc_id}")
    if code != 200:
        print(f"  ❌ HTTP {code}: {data}")
        # fall back to global pool
        print("  → trying /api/plc/values (all PLCs)...")
        data, code = call("GET", "/api/plc/values")
        if code != 200:
            print(f"  ❌ Also failed: HTTP {code}")
            return
        tags = [t for t in data.get("tags", []) if t.get("plcId") == plc_id]
        if not tags:
            print(f"  ⚠️  No tags found for {plc_id} in global pool")
            return
    else:
        tags = data.get("tags", [])

    if not tags:
        print("  (no tags — PLC may not have responded yet)")
        return

    # group by data type
    by_type: dict = {}
    for t in tags:
        dt = t.get("dataType") or t.get("type") or "Unknown"
        by_type.setdefault(dt, []).append(t)

    print(f"  Total tags: {len(tags)}")
    print()

    for dtype, items in sorted(by_type.items()):
        print(f"  ── {dtype} ({len(items)} tags) ──")
        for t in items:
            name  = t.get("tagId") or t.get("address") or t.get("name") or "?"
            val   = t.get("value")
            qual  = t.get("quality") or t.get("dataQuality") or ""
            stamp = (t.get("timestamp") or "")[:19]
            print(f"    {name:<38} = {str(val):<14}  q={qual:<5}  {stamp}")
        print()

    return tags

# ─────────────────────────────────────────────────────────────────────────────
# 5. Slot comparison helper
# ─────────────────────────────────────────────────────────────────────────────
def probe_slot(plc_id, ip, port, slot):
    """Re-configure the PLC to use a different slot and re-read tags."""
    sep(f"RE-PROBING {plc_id} ON SLOT {slot}")
    # update via PUT or re-add
    payload = {
        "plcId":       plc_id,
        "displayName": plc_id,
        "protocol":    "Rockwell",
        "ipAddress":   ip,
        "port":        port,
        "slot":        slot,
        "pollingIntervalMs": 1000,
        "enabled": True,
        "etherNetIpOptions": {"path": f"1,{ip},{slot}", "plcType": "ControlLogix"}
    }
    # Try PUT update first, fall back to remove+add
    data, code = call("PUT", f"/api/plc/{plc_id}", payload)
    if code not in (200, 204):
        call("DELETE", f"/api/plc/{plc_id}")
        time.sleep(1)
        call("POST", "/api/plc/add", payload)
    print(f"  Reconfigured to slot {slot}, waiting 10s for reconnect...")
    time.sleep(10)
    read_tags(plc_id)

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="PLC Slot Probe & Data Inspector")
    parser.add_argument("--ip",    default="192.168.0.20", help="PLC IP address")
    parser.add_argument("--port",  type=int, default=44818, help="PLC port (default 44818)")
    parser.add_argument("--slot",  type=int, default=2,    help="Backplane slot (default 2)")
    parser.add_argument("--id",    default="ROCKWELL_002", help="PLC ID to register")
    parser.add_argument("--list",  action="store_true",    help="Just list current PLCs and exit")
    parser.add_argument("--probe", type=int, default=None, metavar="SLOT",
                        help="Re-probe an already-registered PLC on a different slot")
    args = parser.parse_args()

    sep("PLC SLOT PROBE TOOL")
    print(f"  Backend : {BASE}")
    print(f"  Target  : {args.id}  {args.ip}:{args.port}  slot={args.slot}")
    sep()

    # 0. Check backend alive
    _, code = call("GET", "/api/plc/health")
    if code != 200:
        print(f"\n❌ Backend not reachable at {BASE} (HTTP {code})")
        print("   Run: cd CSharpBackend\\bin\\Release\\net8.0\\win-x86\\publish ; .\\OpcDaWebBrowser.exe")
        sys.exit(1)
    print("  ✅ Backend alive\n")

    # 1. List existing PLCs
    list_plcs()
    print()

    if args.list:
        sys.exit(0)

    if args.probe is not None:
        probe_slot(args.id, args.ip, args.port, args.probe)
        sys.exit(0)

    # 2. Register new PLC
    code = add_plc(args.id, args.ip, args.port, args.slot)
    print()

    # 3. Wait for connection
    connected = wait_for_connect(args.id, timeout=25)
    print()

    # 4. Read tag values
    tags = read_tags(args.id)
    print()

    # 5. Summary
    sep("SUMMARY")
    if tags:
        print(f"  ✅ {args.id}  slot={args.slot}  →  {len(tags)} tags read successfully")
        print()
        print("  Re-run with different slot:    python _plc_slot_probe.py --slot 0")
        print("  Re-run with different IP:      python _plc_slot_probe.py --ip 192.168.0.X --slot 2")
        print("  Just list PLCs:                python _plc_slot_probe.py --list")
        print("  Probe existing on new slot:    python _plc_slot_probe.py --probe 0")
    else:
        if not connected:
            print(f"  ⚠️  PLC {args.id} is OFFLINE or unreachable at {args.ip}:{args.port}")
            print()
            print("  Things to check:")
            print("    • Is the PLC powered on and on the network?")
            print("    • ping 192.168.0.20 from this PC")
            print("    • Is slot 2 correct? Try: python _plc_slot_probe.py --slot 0")
            print("    • Try Studio 5000 / RSLinx to verify slot number")
        else:
            print(f"  ⚠️  Connected but no tags yet — try: python _plc_slot_probe.py --id {args.id}")
    sep()

if __name__ == "__main__":
    main()
