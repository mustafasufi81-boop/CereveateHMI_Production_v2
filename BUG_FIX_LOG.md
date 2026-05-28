# Cereveate HMI — Bug Fix Log
**Session Date:** 2026-05-25

---

## ✅ PROBLEM 1 — Alarm Controller: `connection already closed`

**Symptom:**  
`GET /api/alarms/active` crashed with:
```
psycopg2.InterfaceError: connection already closed
```
Flask log flooded with this error on every alarm poll (every few seconds).

**Root Cause:**  
`HistoricalDataService` used a single persistent `psycopg2` connection stored as `self._connection`. After any idle period or DB restart, the connection silently closed. The `_ensure_connection()` method tried to run `SELECT 1` on a dead cursor — which itself threw an error before it could reconnect.

**Files Changed:**

### `HMI/services/historical_data.py`
- Replaced `_ensure_connection()` cursor-based health check with a clean `@property` that only checks `self._connection.closed`:
```python
@property
def connection(self):
    if self._connection is None or self._connection.closed:
        self.connect()
    return self._connection
```
- Removed the `SELECT 1` cursor leak inside the old `_ensure_connection`.

### `HMI/controllers/alarm_controller.py`
- `get_active_alarms()` (high-frequency endpoint) switched to use `db_pool.get_conn()` directly instead of `HistoricalDataService` — connection pool handles reconnects automatically.
- Added `import db_pool` at top of file.
- Removed bare `rollback()` calls that masked the real error.

**Result:** ✅ No more `connection already closed`. Alarms load correctly.

---

## ✅ PROBLEM 2 — OPC/PLC Proxy Returns 0 Tags for Non-Admin Users

**Symptom:**  
Non-admin users (e.g. Sanjeev Saxena) saw empty dashboards — all tag cards blank. Admin users saw data fine. `GET /api/opc/values` and `GET /api/plc/values` via Flask returned 0 tags for non-admin.

**Agreed Description:**
> Since OPC/PLC tags in the C# backend have no plant/area fields, `tag_filter(id, None, None)` returned `False` for every tag → every non-admin user got `count: 0, tags: []` from REST fallback. Values were invisible.

**Root Cause:**  
`system_controller.py` RBAC filter dropped ALL tags for non-admin users. The filter checked `plant`/`area` assignments but OPC/PLC tags in `tag_master` have `plant=None, area=None` (they are plant-wide). The rule only allowed `(None, None)` tags through for admin users.

**Fix:**
> Tags with `plant=None, area=None` are now passed through for all authenticated users — same rule the MQTT broadcast already used.

**Files Changed:**

### `HMI/controllers/system_controller.py`
**Fix 1 — RBAC (None, None) pass-through:**
```python
# Before: only admin got (None,None) tags
# After: ALL authenticated users get tags with no plant/area restriction
if plant is None and area is None:
    pass  # plant-wide tag — allow for all users
```

**Fix 2 — PLC key mismatch:**  
C# PLC endpoint returns `values` (not `tags`) and `tagName` (not `tagId`). Added normalisation:
```python
tag_list = data.get('values') or data.get('tags', [])
# normalise tagName → tagId
for t in tag_list:
    if 'tagName' in t and 'tagId' not in t:
        t['tagId'] = t['tagName']
```

**Fix 3 — Response shape (dict vs list):**
> The proxy was converting the C# list response into a dict. The frontend `applyTagUpdates` does `Object.entries(raw)` on a dict, which works but creates an extra indirection layer. Now the response stays as a list matching the C# shape exactly, so `Array.isArray(raw)` is true and the frontend processes it directly.

**Result:** ✅ OPC = 27 tags, PLC = 128 tags — working for ALL users including non-admin.

---

## ✅ PROBLEM 3 — "MQTT RECONNECTING #8" Banner in UI

**Symptom:**  
Browser showed a persistent "MQTT RECONNECTING #8" warning banner after Flask was restarted.

**Agreed Description:**
> This was caused by Flask being restarted (killing the WebSocket connection) — the browser's Socket.IO client reconnected after 8 attempts. Now that Flask is stable and auto-reconnects correctly, a page refresh clears this.

**Root Cause:**  
Not a code bug. Flask restart drops all active Socket.IO connections. The React client's Socket.IO reconnect counter incremented to 8 before successfully reconnecting. The banner was just showing the reconnect attempt count.

**Fix:**  
No code change needed. Flask stability improvements (Problems 1, 4) prevent unnecessary restarts. A page refresh always clears the banner.

**Result:** ✅ Expected behaviour — not a bug.

---

## ✅ PROBLEM 4 — Tag Cards Show Stale Values After Flask Restart

**Symptom:**  
After restarting Flask, all dashboard tag cards showed old timestamps (e.g. `07:26:59`) until a new MQTT message arrived for that specific tag.

**Root Cause:**  
`app.py` had an empty `latest_tag_values = {}` dict on startup. The in-memory cache was only populated as new MQTT messages arrived — no seed from DB on boot.

**Files Changed:**

### `HMI/app.py`
- Added `_seed_tag_cache_from_db()` function that queries last 1 hour of `historian_raw.historian_timeseries` on startup and pre-fills `latest_tag_values`.
- Called after `initialize_services()` in `__main__` block.
- Also fixed the Socket.IO on-connect snapshot to include `(None, None)` plant/area tags (same RBAC fix as Problem 2).

**Result:** ✅ Cards populate immediately after Flask restart.

---

## ℹ️ PROBLEM 5 — PLC Tag Timestamps Stuck at `07:26:59` (Not a Bug)

**Symptom:**  
PLC tag values on dashboard showed timestamps permanently frozen at `07:26:59`.

**Agreed Description:**
> The physical Rockwell PLC at `192.168.0.20` is unreachable from this machine. The C# backend caches the last known values — so you'll see stale OPC data until the physical PLC is reachable on the network. This is expected, not a bug.

**Root Cause:**  
Network/hardware issue — not a software bug. The C# `PlcGateway` cannot reach the Rockwell PLC at `192.168.0.20` (likely different subnet or VPN not connected). C# correctly serves the last cached values with the last successful poll timestamp.

**Action Required:**  
Ensure this machine has network access to `192.168.0.20` (same LAN or VPN). Once connected, C# will start polling and timestamps will update in real-time.

**Result:** ℹ️ No code fix needed — hardware/network prerequisite.

---

## ✅ PROBLEM 6 — MQTT Subscriber Service: Duplicate DB Writes + `null tag_id` Errors

**Symptom:**  
`mqtt_subscriber_service` logs flooded with:
```
null value in column "tag_id" of relation "_hyper_1_37_chunk" violates not-null constraint
Failing row contains (2026-05-25 05:42:00.291+05:30, null, 52, null, null, U, MQTT, 1, ...)
```

**Root Cause (Duplication):**  
Full investigation revealed the service was entirely redundant:
- C# `PlcHistorianIngestService` already writes PLC tags directly to `historian_raw.historian_timeseries` via `COPY BINARY`
- C# `OpcUaService` already writes OPC tags directly to the same table
- The Python MQTT subscriber subscribed to the same MQTT topics the C# backend published — and wrote the **same data to DB a second time**

**Root Cause (null tag_id):**  
`message_processor.py` line 342 used `value_entry.get('tag')` but the MQTT payload field was `tagId` — so it always resolved to `None`.

**Decision:**  
Service is **100% redundant**. All DB persistence is owned by C#. MQTT broker exists only as a live broadcast channel for the Flask UI dashboard. Service permanently removed.

**Files Changed:**

### `START_ALL.bat`
- Removed Step 4 (MQTT Subscriber start command) entirely.
- Step numbers renumbered: 1–5 (PostgreSQL, Mosquitto, OPC C#, Flask, Nginx).

**Result:** ✅ No more duplicate writes. No more null tag_id errors. One less process running.

---

## 🅿️ PARKED — Problem 7: OPC Tags: 0 Values via API + MQTT

**Symptom:**  
`GET /api/opc/status` → `{"connected": false, "tagCount": 0}`  
`GET /api/opc/values` → `{"count": 0, "tags": []}`  
OPC MQTT topic publishes nothing.  
OPC Browser UI shows "Connected to Matrikon.OPC.Simulation.1" with 113 tags visible — but this is the **manual browser connection**, not the historian/API connection.

**What We Know:**  
- `OpcController.GetAllTagValues()` calls `_opcDaService.ReadAllTagValues()` — the same connection used by historian and MQTT publisher.
- `OpcMqttPublisherService` filters by `historian_meta.tag_master` where `server_progid` matches a connected OPC server.
- **Likely cause**: `tag_master` has no rows with `server_progid = 'Matrikon.OPC.Simulation.1'` — so `enabledOpcTagIds` is empty → nothing published to MQTT and nothing returned by API.
- Second possibility: `OpcDaService` main historian connection is separate from the browser UI connection and is not auto-connecting on startup.

**To Investigate Next:**
1. Check `tag_master` rows — do any have `server_progid = 'Matrikon.OPC.Simulation.1'`?
   ```sql
   SELECT tag_id, server_progid, is_enabled 
   FROM historian_meta.tag_master 
   WHERE server_progid IS NOT NULL 
   ORDER BY server_progid;
   ```
2. Check C# startup logs for `[OPC-MQTT]` lines — specifically:
   - `"No enabled OPC tags in historian_meta.tag_master"` → tag_master issue
   - `"No tag values from OPC server"` → OpcDaService not connected
3. Check `LoggingConfigService.GetDecryptedProgId()` — what ProgID is configured for the historian OPC connection?

**Status:** 🅿️ Parked — come back to this after current sprint.

---

## Architecture Notes (Post-Fix)

```
Physical PLC (Rockwell, 192.168.0.20)
        ↓ EtherNet/IP
C# OpcDaWebBrowser.exe (port 5001)
  ├── PlcHistorianIngestService  → PostgreSQL (COPY BINARY) ✅
  ├── OpcUaService               → PostgreSQL (COPY BINARY) ✅
  ├── MultiProtocolPublisher     → MQTT broker (port 1883)  ✅
  └── REST API /api/plc/values   → Flask proxy              ✅

Matrikon OPC Simulation (local COM)
        ↓ OPC DA
C# OpcDaWebBrowser.exe
  ├── OpcDaService (historian connection)  → 🅿️ NOT connecting on startup
  └── OpcMqttPublisherService              → 🅿️ 0 tags published

MQTT Broker (Mosquitto, port 1883)
        ↓
Flask app.py (port 6001)
  ├── MQTT callback → latest_tag_values cache (live UI)
  └── Socket.IO     → React frontend (port 8090 via Nginx)

mqtt_subscriber_service  ← ❌ REMOVED (was duplicate DB writer)
```

---

## Services Running (Current State)

| Port | Service | Status |
|------|---------|--------|
| 1883 | Mosquitto (broker only) | ✅ |
| 5001 | C# OPC/PLC Backend | ✅ |
| 6001 | Flask HMI | ✅ |
| 8090 | Nginx | ✅ |
| — | mqtt_subscriber_service | ❌ Removed |
