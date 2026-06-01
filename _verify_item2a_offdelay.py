"""Verify Item 2A — RTN off-delay (5s settling).

Watch ~70s of fresh history for PY1105B and report:
  - total RAISE / RTN count
  - any RTN that happened < 5s after its level's most recent RAISE (these would
    indicate the off-delay was NOT applied)
  - per-level RAISE->RTN dwell times
"""
import time, requests
from datetime import datetime, timezone

BASE = "http://127.0.0.1:5001"
TAG = "PY1105B"
WATCH_SECS = 70

print(f"Watching {TAG} for {WATCH_SECS}s ...")
t0 = time.time()
while time.time() - t0 < WATCH_SECS:
    time.sleep(2)
    print(".", end="", flush=True)
print()

r = requests.get(f"{BASE}/api/alarms/history?limit=200", timeout=10)
events = [e for e in r.json().get("events", []) if e.get("tag_id") == TAG]
events.sort(key=lambda e: e["time"])  # oldest first

# Keep only events that happened during/just before the watch window
cutoff = datetime.now(timezone.utc).timestamp() - (WATCH_SECS + 10)
def ts(s):
    return datetime.fromisoformat(s.replace("Z","+00:00")).timestamp()
events = [e for e in events if ts(e["time"]) >= cutoff]

raises = [e for e in events if e["event_type"] == "RAISE"]
rtns   = [e for e in events if e["event_type"] == "RTN"]
print(f"\n{TAG}: events in window = {len(events)}  (RAISE={len(raises)}  RTN={len(rtns)})")

# For each RTN, find the most recent RAISE of the same level before it
violations = 0
dwells = []
for rtn in rtns:
    lvl = rtn["alarm_level"]
    rtn_t = ts(rtn["time"])
    prior_raises = [e for e in raises if e["alarm_level"] == lvl and ts(e["time"]) < rtn_t]
    if not prior_raises:
        continue
    last_raise = max(prior_raises, key=lambda e: ts(e["time"]))
    dwell = rtn_t - ts(last_raise["time"])
    dwells.append((lvl, dwell))
    if dwell < 5.0:
        violations += 1
        print(f"  ⚠ FAST RTN: {lvl}  raise@{last_raise['time']}  rtn@{rtn['time']}  dwell={dwell:.1f}s")

if dwells:
    print(f"\nDwell times (RAISE→RTN) by level:")
    for lvl, d in dwells:
        flag = "  ⚠<5s" if d < 5 else "  ✓"
        print(f"   {lvl:<10} {d:6.1f}s{flag}")

print(f"\nResult: {violations} RTN(s) fired in <5s after RAISE "
      f"({'OK — off-delay enforced' if violations==0 else 'FAIL — off-delay NOT enforced'})")
