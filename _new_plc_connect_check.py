"""
_new_plc_connect_check.py
=========================
Script to configure a NEW PLC in the backend and inspect the data it returns.

USAGE:
  1. Edit the NEW_PLC block below with the real IP / protocol / slot.
  2. Run:  python _new_plc_connect_check.py
  3. The script will:
       (a) Show all currently configured PLCs.
       (b) ADD the new PLC via the REST API (if not already present).
       (c) Wait for the first poll to complete (~10 s).
       (d) Fetch and display every tag value returned by the new PLC.
       (e) Print a summary: tag count, data types, value ranges, quality.

Supported protocols: Rockwell | Siemens | Modbus | ModbusTCP
"""

import json, time, sys
import urllib.request, urllib.error

BASE = "http://127.0.0.1:5001"

# ─────────────────────────────────────────────────────────
#  ▶  EDIT THIS BLOCK FOR THE NEW PLC
# ─────────────────────────────────────────────────────────
NEW_PLC = {
    "plcId":      "New_PLC_002",          # unique ID — change if needed
    "name":       "New_PLC_002",
    "protocol":   "Rockwell",             # Rockwell | Siemens | Modbus | ModbusTCP
    "ipAddress":  "192.168.0.30",         # ← PUT REAL IP HERE
    "port":       44818,                  # Rockwell=44818, Siemens=102, Modbus=502
    "slot":       0,                      # Rockwell CPU slot (0 for most CompactLogix)
    "enabled":    True,
}
# ─────────────────────────────────────────────────────────


def get(path):
    try:
        with urllib.request.urlopen(f"{BASE}{path}", timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "msg": e.read().decode()}
    except Exception as e:
        return {"error": str(e)}


def post(path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "msg": e.read().decode()}
    except Exception as e:
        return {"error": str(e)}


def sep(title=""):
    print("\n" + "─" * 60)
    if title:
        print(f"  {title}")
        print("─" * 60)


# ── 1. Show current PLCs ───────────────────────────────────
sep("STEP 1 — Current PLC connections")
conns = get("/api/plc/connections")
if "error" in conns:
    print(f"  ✗ Cannot reach backend: {conns}")
    sys.exit(1)

print(f"  Total PLCs: {conns.get('totalCount', 0)}   Connected: {conns.get('connectedCount', 0)}")
for c in conns.get("connections", []):
    status = "✓ CONNECTED" if c["isConnected"] else "✗ OFFLINE"
    print(f"  [{status}]  {c['plcId']}  |  {c['protocol']}  |  {c['ipAddress']}:{c['port']}  |  tags={c['tagCount']}")


# ── 2. Check if new PLC already exists ────────────────────
sep("STEP 2 — Adding new PLC")
existing_ids = [c["plcId"] for c in conns.get("connections", [])]

if NEW_PLC["plcId"] in existing_ids:
    print(f"  ℹ  {NEW_PLC['plcId']} already configured — skipping add.")
else:
    print(f"  Adding {NEW_PLC['plcId']}  ({NEW_PLC['protocol']} @ {NEW_PLC['ipAddress']}:{NEW_PLC['port']}) ...")
    result = post("/api/plc/add", NEW_PLC)
    if "error" in result:
        print(f"  ✗ Add failed: {result}")
        sys.exit(1)
    print(f"  ✓ Add response: {json.dumps(result, indent=4)}")


# ── 3. Wait for first poll ─────────────────────────────────
sep("STEP 3 — Waiting for first poll (~15 s)")
WAIT = 15
for i in range(WAIT, 0, -1):
    print(f"\r  Waiting {i:2d}s ...  ", end="", flush=True)
    time.sleep(1)
print("\r  Done waiting.          ")


# ── 4. Re-check connection status ─────────────────────────
sep("STEP 4 — Connection status after poll")
conns2 = get("/api/plc/connections")
new_conn = next(
    (c for c in conns2.get("connections", []) if c["plcId"] == NEW_PLC["plcId"]),
    None
)

if not new_conn:
    print("  ✗ New PLC not found in connections list.")
    sys.exit(1)

connected  = new_conn["isConnected"]
tag_count  = new_conn["tagCount"]
err_count  = new_conn["errorCount"]
last_error = new_conn.get("lastError")
print(f"  plcId     : {new_conn['plcId']}")
print(f"  protocol  : {new_conn['protocol']}")
print(f"  address   : {new_conn['ipAddress']}:{new_conn['port']}")
print(f"  connected : {'✓ YES' if connected else '✗ NO'}")
print(f"  tagCount  : {tag_count}")
print(f"  errorCount: {err_count}")
print(f"  lastError : {last_error or '(none)'}")
print(f"  pollCount : {new_conn.get('pollCount', 0)}")


# ── 5. Fetch tag values ────────────────────────────────────
sep("STEP 5 — Fetching tag values from new PLC")
values_resp = get(f"/api/plc/values/{NEW_PLC['plcId']}")

if "error" in values_resp:
    print(f"  ✗ Could not fetch values: {values_resp}")
elif not connected:
    print("  ⚠  PLC is OFFLINE — no live values available.")
    print(f"  Last error: {last_error}")
else:
    tags = values_resp.get("tags", values_resp.get("values", {}))
    if isinstance(tags, dict):
        tags_list = [{"tagId": k, **v} for k, v in tags.items()]
    elif isinstance(tags, list):
        tags_list = tags
    else:
        tags_list = []

    print(f"  Received {len(tags_list)} tags\n")

    if tags_list:
        # Header
        print(f"  {'TAG ID':<35} {'VALUE':>12}  {'QUALITY':<10}  TIMESTAMP")
        print(f"  {'─'*35} {'─'*12}  {'─'*10}  {'─'*24}")

        type_counts: dict[str, int] = {}
        bad_quality = []

        for t in sorted(tags_list, key=lambda x: x.get("tagId", "")):
            tag_id   = t.get("tagId", t.get("tag_id", "?"))
            value    = t.get("value", "?")
            quality  = t.get("quality", "?")
            ts       = t.get("timestamp", "")[:19] if t.get("timestamp") else ""
            dtype    = type(value).__name__
            type_counts[dtype] = type_counts.get(dtype, 0) + 1
            if str(quality).upper() not in ("GOOD", "TRUE", "1"):
                bad_quality.append(tag_id)
            print(f"  {tag_id:<35} {str(value):>12}  {str(quality):<10}  {ts}")

        # Summary
        sep("SUMMARY")
        print(f"  Total tags      : {len(tags_list)}")
        print(f"  Data types      : {dict(type_counts)}")
        print(f"  Bad quality tags: {len(bad_quality)}")
        if bad_quality:
            for b in bad_quality[:20]:
                print(f"    - {b}")
            if len(bad_quality) > 20:
                print(f"    ... and {len(bad_quality)-20} more")
    else:
        print("  (no tags in response)")
        print(f"  Raw response: {json.dumps(values_resp, indent=2)[:800]}")


sep("DONE")
print("  New PLC configured and checked.\n")
