# PLC Communication Architecture — Design, Gaps & Production Hardening Plan
**CereveateHMI Production**
**Date: 2026-05-26**
**Status: PRE-PRODUCTION — Physical PLC not yet connected. Document-only phase.**

---

## 1. Full System Architecture (Current State)

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                        PHYSICAL LAYER  (not yet wired)                           │
│   Rockwell ControlLogix @ 192.168.0.20:44818  (Rockwel_PLC_001)                 │
│   + Future: Siemens S7, Modbus TCP, ABB, Mitsubishi, Omron                       │
└─────────────────────────────────┬────────────────────────────────────────────────┘
                                  │ EtherNet/IP CIP (libplctag)
                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                    C# BACKEND  (OpcDaWebBrowser.exe  :5001)                      │
│                                                                                   │
│  PlcGatewayHostedService                                                         │
│    └─ PlcConfigLoaderService  ──► historian_meta.tag_master  (primary)           │
│                                ──► appsettings.json          (fallback)          │
│    └─ PlcGatewayManager                                                          │
│         └─ PlcWorker [per PLC] — Task.Run, CancellationTokenSource              │
│              ├─ IPlcDriver (RockwellDriver / SiemensS7Driver / ...)              │
│              ├─ PlcScanRateScheduler  (per-tag scan rates + deadband)            │
│              └─ Writes ──► PlcTagValuesPoolService (ConcurrentDictionary)        │
│                                                                                   │
│  PlcTagValuesPoolService  (UNIFIED SHARED CACHE)                                 │
│    ├─ REST API: GET /api/plc/values, /values/{plcId}, /connections, /health     │
│    └─ PlcMqttPublisherService ──► MQTT topic: {PlcId}/tags/bulk                 │
│                                                                                   │
│  OpcDaService  (separate — OPC DA via COM/STA Dispatcher)                       │
│    └─ OpcMqttPublisherService ──► MQTT topic: opc/{serverProgId}/tags/bulk      │
└─────────────┬───────────────────────────────────────────────────────────────────┘
              │ MQTT (Mosquitto :1883)
              ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                    PYTHON HMI  (Flask-SocketIO / Gevent  :6001)                  │
│                                                                                   │
│  MQTT Subscriber ──► on_mqtt_message()                                           │
│    └─ Transport Arbitration: MQTT > SignalR > REST_FALLBACK                      │
│    └─ RBAC filter (plant/area + PLC-tags always visible to authenticated users)  │
│    └─ latest_tag_values{}  (in-memory, per tag_id)                               │
│                                                                                   │
│  REST Fallback Greenlet                                                          │
│    └─ polls GET /api/plc/values (C# :5001) when MQTT+SignalR dead               │
│    └─ 30s grace, exponential backoff, single-flight, write-guard                │
│                                                                                   │
│  Socket.IO broadcast ──► Browser                                                 │
│  /api/opc-plc-status ──► proxies /api/health/opc + /api/plc/connections         │
└─────────────┬────────────────────────────────────────────────────────────────────┘
              │ Socket.IO + REST
              ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│              REACT HMI  (Vite / TypeScript  :6001/dist)                          │
│   useOpcPlcStatus hook (10s poll) → banner: ⚠ PLC X: NOT CONNECTED             │
│   Transport badge: MQTT LIVE / REST FALLBACK                                     │
│   AlarmPanel, TrendChart, AssetBrowser — all RBAC-gated                         │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Multi-PLC Data Flow — End to End

This section documents exactly how data flows from **N physical PLCs** to the browser. Every step is the same regardless of the number of PLCs — 1 or 20.

### 2.1 Startup Config Load (once per process start)

```
PlcGatewayHostedService.LoadAndStartPlcsAsync()
    │
    └─► PlcConfigLoaderService.LoadAllEnabledPlcsAsync()
            │
            ├─► [PRIMARY]  historian_meta.tag_master  (DB query)
            │     SELECT server_progid, plc_protocol, plc_ip_address, plc_port,
            │            plc_type, plc_path, plc_timeout_ms, plc_polling_interval_ms
            │     WHERE plc_ip_address IS NOT NULL AND enabled = true
            │     → returns List<PlcConfigEntry>  (one entry per distinct PlcId)
            │
            └─► [FALLBACK]  appsettings.json  (PlcGateway:Connections[])
                  → currently: Rockwel_PLC_001 @ 192.168.0.20:44818, 5 tags

    For EACH PlcConfigEntry:
        PlcGatewayManager.AddPlcAsync(config, tags)
            ├─► PlcDriverFactory.CreateDriver(protocol)    → isolated driver instance
            ├─► driver.InitializeAsync(config, tags)
            └─► new PlcWorker(plcId, driver, sharedPool, sampleBuffer, tags)
                    └─► worker.StartAsync()  →  Task.Run(PollingLoopAsync)
```

**Result after startup with 3 PLCs configured:**
```
PlcGatewayManager._workers:
  "Rockwel_PLC_001"  →  PlcWorker  (RockwellDriver,  Task running)
  "Siemens_PLC_002"  →  PlcWorker  (SiemensS7Driver, Task running)
  "Modbus_PLC_003"   →  PlcWorker  (ModbusTcpDriver, Task running)
```
All 3 workers poll **in parallel**. No shared locks. No dependency between workers.

---

### 2.2 Per-PLC Polling Loop (continuous, every `pollingIntervalMs`)

```
PlcWorker.PollingLoopAsync()  [each PLC runs its own independent copy]

  TICK:
    ┌─ Is driver connected?
    │    NO → ConnectWithRetryAsync() → backoff 30s→60s→120s (independent per PLC)
    │    YES ↓
    ├─ PlcScanRateScheduler.GetTagsDueForScan()
    │    → returns only tags whose per-tag scan_rate_ms has elapsed
    │    → 0 tags due? → skip PLC read entirely (no network traffic)
    ├─ driver.ReadTagsAsync(tagsDue)        ← EtherNet/IP CIP / S7Comm / Modbus
    │    → returns PlcReadResult { TagValues: List<PlcTagValue> }
    ├─ PlcTagValuesPoolService.UpdateFromPlc(plcId, tagValues, timestamp)
    │    → writes to ConcurrentDictionary key = "{plcId}::{address}"
    │    → marks _connectionStatus[plcId].IsConnected = true
    └─ PlcSampleBufferService.AddSamples(plcId, tagValues)
         → feeds MQTT publisher (next step)
```

**Key isolation guarantee:** `Siemens_PLC_002` going offline does not delay `Rockwel_PLC_001`'s next tick by even 1 millisecond.

---

### 2.3 MQTT Publishing (C# → Mosquitto)

```
PlcGateway MQTT publisher (appsettings.json: PlcGateway.Mqtt.Enabled=true)
    │
    ├─ BrokerHost: localhost:1883
    ├─ PublishMode: Bulk
    └─ Topic pattern:  {PlcId}/tags/bulk     ← ONE topic per PLC

Example topics with 3 PLCs:
    "Rockwel_PLC_001/tags/bulk"
    "Siemens_PLC_002/tags/bulk"
    "Modbus_PLC_003/tags/bulk"

Payload (same shape for every PLC):
{
  "gateway_id": "Rockwel_PLC_001",
  "timestamp": "2026-05-26T08:41:00.000Z",
  "tags": [
    { "tag_id": "TY1101A", "value_num": 73.2, "quality": "Good", "time": "..." },
    { "tag_id": "PY1101A", "value_num": 4.15, "quality": "Good", "time": "..." }
  ]
}
```

MQTT topic auto-registration: `PlcConfigLoaderService.EnsureMqttTopicsRegisteredAsync()` inserts each `plcId` into `historian_raw.mqtt_topic_config` (ON CONFLICT DO NOTHING) — adding a new PLC to DB automatically creates its subscription without any manual step.

---

### 2.4 Python HMI — MQTT Receive → Browser (same path for every PLC)

```
MQTTClientService  (subscribes to wildcard — all topics)
    │
    └─► on_mqtt_message(topic, filtered_tags, raw_data)
            │
            ├─ Transport liveness stamp:
            │    _transport_state["last_mqtt_msg_at"] = time.monotonic()
            │    _update_active_source()   →  MQTT > SignalR > REST
            │
            ├─ Cache update (ALL PLCs share same dict, keyed by tag_id):
            │    latest_tag_values[tag_id] = {
            │        'value_num', 'quality', 'timestamp',
            │        'source': 'MQTT',
            │        'topic': topic,           ← carries plcId implicitly
            │        'plcId': tag.get('plcId'),
            │        'age_ms': _compute_age_ms(ts_val),
            │    }
            │
            ├─ RBAC filter (per connected Socket.IO session):
            │    PLC tags (no plant/area in tag_meta) → visible to ALL authenticated users
            │    OPC tags (have plant/area) → filtered by user's allowed area set
            │
            └─ socketio.emit('mqtt_tag_update', {
                    'topic': topic,              ← "Rockwel_PLC_001/tags/bulk"
                    'tags': user_tags,           ← RBAC-filtered tag list
                    'gateway_id': "Rockwel_PLC_001",
                    'timestamp': mqtt_ts
               }, room=sid)

One emit per connected browser session per MQTT message.
With 3 PLCs publishing at 1s each: 3 emits/second per session.
```

**Critical: `on_mqtt_message` is called for EVERY topic.** No PLC-specific routing code exists or is needed. `topic` is passed through to the browser unchanged — the browser can distinguish PLC sources by `topic` or `gateway_id`.

---

### 2.5 REST Fallback Path (when MQTT dead — same for all PLCs)

```
_rest_fallback_poller()  [gevent greenlet]
    │
    ├─ Activates ONLY when: MQTT dead AND SignalR dead AND 30s grace elapsed
    ├─ Polls GET http://localhost:5001/api/plc/values  (ALL PLCs in one response)
    │    → PlcTagValuesPoolService returns all tags from all connected PLCs
    ├─ Merges into latest_tag_values (same dict — same path as MQTT)
    └─ Broadcasts via socketio.emit('mqtt_tag_update')

REST fallback is PLC-count-agnostic: one call returns all PLCs' current values.
```

---

### 2.6 Connection Status Banner (React ← Python ← C#)

```
useOpcPlcStatus hook  (polls every 10s)
    │
    └─► GET /api/opc-plc-status   (Python proxy)
             │
             └─► GET /api/plc/connections  (C# — returns ALL PLCs)
                   {
                     "connections": [
                       { "plcId": "Rockwel_PLC_001", "isConnected": false, ... },
                       { "plcId": "Siemens_PLC_002", "isConnected": true,  ... },
                       { "plcId": "Modbus_PLC_003",  "isConnected": true,  ... }
                     ]
                   }

Python normalises → { plcs: [ {id, name, connected, lastError}, ... ] }

React:
  plcs.filter(p => !p.connected).map(p =>
    <span>⚠ PLC {p.name}: NOT CONNECTED</span>   ← one badge per disconnected PLC
  )
```

With 3 PLCs and 2 disconnected, **2 separate orange badges** appear in the top bar simultaneously.

---

### 2.7 Adding a New PLC — Zero Code Changes Required

```
Step 1: Insert into historian_meta.tag_master (or add to appsettings.json):
        plc_id='Siemens_PLC_002', plc_ip_address='192.168.0.30',
        plc_protocol='SiemensS7', plc_port=102, enabled=true

Step 2: PlcGatewayHostedService config refresh fires (every 5 min)
        OR restart OpcDaWebBrowser.exe

Step 3 (automatic): PlcConfigLoaderService loads new config
Step 4 (automatic): PlcGatewayManager.AddPlcAsync() creates new isolated worker
Step 5 (automatic): MQTT topic "Siemens_PLC_002/tags/bulk" auto-registered in DB
Step 6 (automatic): Python HMI on_mqtt_message() receives new topic → cache + broadcast
Step 7 (automatic): /api/plc/connections returns 2 PLCs → React banner handles both
```

No Python code change. No React code change. No config file edit beyond the DB insert.

---

## 3. PLC Gateway — What Is Built & Working

### 2.1 Worker Isolation ✅
Each PLC runs in a completely isolated `PlcWorker` (one `Task.Run` per PLC, own `CancellationTokenSource`). Failure of one PLC cannot crash, block or affect any other PLC's polling loop. `PlcGatewayManager` holds all workers in a `ConcurrentDictionary<string, PlcWorker>`.

### 2.2 Multi-Protocol Driver Layer ✅
`IPlcDriver` interface is implemented for 7 protocols:

| Driver | Protocol | Library | Status |
|--------|----------|---------|--------|
| `RockwellDriver` | EtherNet/IP CIP | libplctag | **Current target** |
| `SiemensS7Driver` | S7Comm | S7.Net | Ready |
| `ModbusTcpDriver` | Modbus TCP | NModbus | Ready |
| `AbbDriver` | Modbus TCP (ABB profile) | NModbus | Ready |
| `MitsubishiDriver` | Modbus TCP (Mitsubishi profile) | NModbus | Ready |
| `OmronDriver` | FINS/TCP | Native | Ready |

### 2.3 Config Loading — Dual Source ✅
Priority: **`historian_meta.tag_master` (DB) → `appsettings.json` (fallback)**

DB query selects `server_progid, plc_protocol, plc_ip_address, plc_port, plc_type, plc_path, plc_timeout_ms, plc_polling_interval_ms` from `tag_master` where `plc_ip_address IS NOT NULL AND enabled = true`.

`appsettings.json` currently has `Rockwel_PLC_001 @ 192.168.0.20:44818` with 5 tags (TY1101A, PY1101A, PY1101B, PY1103A, PY1103B) as the working fallback.

Config refresh happens every 5 minutes at runtime — new PLCs added to DB are picked up without restart.

MQTT topic auto-registration: whenever a PLC is loaded, `PlcConfigLoaderService` inserts its `plcId` into `historian_raw.mqtt_topic_config` (ON CONFLICT DO NOTHING) — zero manual steps to subscribe a new PLC.

### 2.4 Reconnect + Backoff ✅
`PlcWorker.PollingLoopAsync()` implements:
- First offline → immediate connect attempt
- Failed → 30s wait, then 60s, then 120s (doubles, capped at 120s)
- One-time offline log (no log flood every second)
- On recovery → resets backoff, logs `back ONLINE`, resumes normal polling
- `RockwellDriver` has its own per-driver backoff layer on top

### 2.5 Per-Tag Scan Rate Scheduler ✅
`PlcScanRateScheduler` tracks which tags are due per tick. Each tag can have its own `scan_rate_ms`. Only due tags are read in a batch — prevents PLC overload. Tags not due in a tick are skipped entirely (no wasted CIP request).

### 2.6 Shared Cache (PlcTagValuesPoolService) ✅
`ConcurrentDictionary<string, PlcTagValueCacheEntry>` — key = `"{PlcId}::{Address}"`. Lock-free reads. Tracks per-PLC `isConnected` status separately in `_connectionStatus` dict. Consumers: REST API, HistorianIngestService, ParquetLoggingService.

### 2.7 MQTT Publishing ✅
`PlcGateway` config block in `appsettings.json` enables MQTT publishing to `localhost:1883`. Topic pattern: `{PlcId}/tags/bulk`. The Python HMI subscribes to this topic and broadcasts via Socket.IO to the browser.

### 2.8 REST API Endpoints ✅
```
GET /api/plc/values               All tags, all PLCs
GET /api/plc/values/{plcId}       Tags for one PLC
GET /api/plc/connections          ← Used by /api/opc-plc-status proxy (FIXED)
GET /api/plc/tag/{plcId}/{name}   Single tag live value
GET /api/plc/stats                Pool statistics
GET /api/plc/health               Health check
```

---

## 3. Current Gaps — Detailed Analysis

### GAP 1 — No PLC State Machine (CRITICAL)
**What exists:** `PlcWorker._state` is a `PlcWorkerState` enum (`Created / Starting / Running / Connecting / Disconnected / Stopped`). The transitions are ad-hoc, checked inline in the polling loop.

**What is missing:**
- No formal `Faulted` state
- No circuit breaker — if a PLC fails 100 times in a row, the worker keeps trying at 120s intervals forever with no escalation
- No `Cooldown` state with a minimum recovery window
- `PlcTagValuesPoolService.MarkPlcDisconnected()` is called on failure but there is no downstream action beyond logging

**Risk:** A permanently unreachable PLC with a bad IP will cycle forever without any alert, health escalation, or operator notification beyond log lines.

**Fix required:**
```
Disconnected → Connecting → Running
                          ↘ Faulted (≥5 consecutive failures in ≤2 min) 
                               └─ Cooldown (5 min) → Connecting (retry once)
                                       └─ Faulted again → extend cooldown (10 min, 20 min ...)
```

---

### GAP 2 — No Per-Tag Age/Freshness in PLC Cache (HIGH)
**What exists:** `PlcTagValueCacheEntry` has `Timestamp` and `CachedAt` fields but `age_ms` is never computed or returned in any API response.

**What is missing:**
- `/api/plc/values` response does not include `age_ms`
- The Python HMI `latest_tag_values` dict does not carry `age_ms` for PLC tags
- The browser has no way to know a PLC tag value is 45 seconds stale vs 1 second fresh
- No `quality: STALE` flag when value age exceeds threshold

**Risk:** Browser shows a value from 2 minutes ago with full confidence styling. Operator makes a decision on stale data.

**Fix required:**
- Add `age_ms = (UtcNow - CachedAt).TotalMilliseconds` to every `/api/plc/values` response item
- Add `quality: "STALE"` when `age_ms > stale_threshold_ms` (suggest: 10,000ms for PLC data)
- Mirror the OPC `_compute_age_ms()` helper already built in `app.py` — apply it to PLC MQTT path too

---

### GAP 3 — No Per-PLC Health Endpoint Aggregation (HIGH)
**What exists:** `/api/plc/connections` returns a list of PLC connection objects with `isConnected` and `lastError`. `/api/plc/health` exists but only returns pool-level statistics.

**What is missing:**
- No single endpoint that returns: per-PLC `state`, `consecutiveFailures`, `lastSuccessTime`, `totalPolls`, `successfulPolls`, `tagCount`, `avgReadTimeMs`
- The Python proxy `/api/opc-plc-status` only uses `isConnected` and `lastError` — deep diagnostic data is lost
- No equivalent of the OPC `/api/health/dispatcher` for the PLC layer

**Fix required:** Add `GET /api/plc/diagnostics` that mirrors `GET /api/health/dispatcher` — per-worker stats exposed as JSON.

---

### GAP 4 — `PlcTagValuesPoolService` Has No Maximum Age Eviction (HIGH)
**What exists:** The pool is a `ConcurrentDictionary` that is only written when a PLC successfully reads. Disconnected PLC tags stay in the cache forever with their last known value.

**What is missing:**
- If a PLC goes offline at 09:00, at 17:00 the API still returns that PLC's tags with `Timestamp = 09:00` and no warning
- No `max_age_ms` eviction policy (e.g. remove entries older than 5 minutes)
- No `LastGoodValue` policy: "serve stale but mark it clearly"

**Risk:** Downstream consumers (HistorianIngestService, REST clients) see silently stale data with correct-looking structure.

**Fix required:**
```csharp
// In GetAllTagValues() and GetPlcValues():
var ageSec = (DateTime.UtcNow - entry.CachedAt).TotalSeconds;
if (ageSec > MaxAgeSeconds)  // e.g. 300s
    entry = entry with { Quality = PlcTagQuality.Stale };
```

---

### GAP 5 — No Transport Heartbeat for PLC MQTT Path (HIGH)
**What exists:** The OPC MQTT path has full transport arbitration: `MQTT > SignalR > REST_FALLBACK` with liveness timers, hysteresis, and source arbitration in `app.py`.

**What is missing:** The PLC MQTT path goes through the same `on_mqtt_message()` handler BUT:
- `tag_meta_mqtt` (the plant/area cache) has `(None, None)` for PLC tags — treated as globally visible
- There is no separate liveness timer for PLC-sourced MQTT messages vs OPC-sourced messages
- If the PLC worker stops publishing (PLC offline) the Python HMI has no way to distinguish "PLC offline → no messages" from "MQTT broker dead → no messages for anyone"
- The REST fallback polls `/api/plc/values` for tag values but there is no per-source freshness tracking

**Fix required:**
- Track `last_plc_mqtt_msg_at` separately from `last_opc_mqtt_msg_at`
- When PLC MQTT silent for >10s AND `GET /api/plc/connections` shows `isConnected=false` → mark PLC tags as STALE in broadcast
- Expose per-source transport state in `/api/system-status`

---

### GAP 6 — No PLC Tag Mapping to `tag_master` (MEDIUM)
**What exists:** `PlcConfigLoaderService.LoadFromDatabaseAsync()` reads PLC configs from `historian_meta.tag_master` WHERE `plc_ip_address IS NOT NULL`. The `TagId` from tag_master is used as the PLC tag address.

**What is missing:**
- Tags configured in `appsettings.json` fallback (the current active path) are NOT in `tag_master`
- The 5 tags in `appsettings.json` (`TY1101A`, `PY1101A`, etc.) only exist as JSON — they are not in the DB
- `tag_meta_mqtt` lookup (used for RBAC area filtering) returns `(None, None)` for these tags
- HistorianIngestService uses `MappingCacheService` which reads from `tag_master` — PLC tags in JSON only are never historized

**Fix required (when PLC is connected):**
```sql
-- Insert each PLC tag into tag_master:
INSERT INTO historian_meta.tag_master 
  (tag_id, tag_name, server_progid, plc_protocol, plc_ip_address, plc_port, 
   plc_type, plc_path, plant_id, area_id, enabled)
VALUES
  ('TY1101A', 'Temperature TY1101A', 'Rockwel_PLC_001', 'Rockwell', 
   '192.168.0.20', 44818, 'ControlLogix', '1,0', 'PlantA', 'Area1', true);
```

---

### GAP 7 — `PlcGatewayHostedService` Has a Test Hardcode (LOW)
**What exists (line ~80 in `PlcGatewayHostedService.cs`):**
```csharp
// FOR TESTING: If no configs found, add hardcoded test PLC
```
This block adds a hardcoded `192.168.1.100` Siemens test PLC when the DB returns nothing.

**Risk:** If DB connection fails on startup and `appsettings.json` also has no config, the test PLC is activated and tries to connect to a non-existent address, polluting logs.

**Fix required:** Remove this test block before production. The `appsettings.json` fallback is the correct safety net.

---

### GAP 8 — `PlcConfigPersistenceService` Config Path Hardcoded to `D:\OpcLogs` (LOW)
`PlcConfigPersistenceService` defaults `plc-config.json` to `D:\OpcLogs\plc-config.json` via `DataLogging:BasePath`. The `plc-config.json` file is a secondary persistence mechanism written by the Web UI PLC configurator. This path is not in `appsettings.json` under `DataLogging:BasePath` — it will always use the default and silently create `D:\OpcLogs\` if it doesn't exist.

**Risk:** Low — the file is only written when someone uses the PLC Web UI config panel. Not on the critical read path.

---

## 4. Full Gap Summary Table

| # | Gap | Severity | Impact | Fix Sprint |
|---|-----|----------|--------|------------|
| 1 | No PLC state machine / circuit breaker | 🔴 CRITICAL | Worker loops forever on dead PLC, no escalation | Sprint 1 |
| 2 | No `age_ms` / `quality: STALE` in PLC cache | 🟠 HIGH | Operator sees silently stale values | Sprint 1 |
| 3 | No per-PLC diagnostics endpoint | 🟠 HIGH | Cannot monitor PLC health from HMI | Sprint 1 |
| 4 | Cache has no max-age eviction | 🟠 HIGH | Disconnected PLC tags served indefinitely as valid | Sprint 1 |
| 5 | REST fallback covers OPC only — PLC not included | 🟠 HIGH | PLC tags go blank when MQTT dies, no REST recovery | Sprint 1 |
| 6 | No per-source MQTT liveness for PLC vs OPC | 🟠 HIGH | Cannot distinguish PLC offline from MQTT offline | Sprint 2 |
| 7 | No hard driver timeout wrapper at worker level | 🟠 HIGH | Native DLL hang (libplctag) can freeze scan loop indefinitely | Sprint 1 |
| 8 | C# backoff timers use `DateTime.UtcNow` not monotonic | 🟡 MEDIUM | System clock jump breaks reconnect backoff timing | Sprint 1 |
| 9 | No scan cycle watchdog / jitter metrics | 🟡 MEDIUM | Silent scan degradation undetectable | Sprint 1 |
| 10 | No MQTT Birth/Death (LWT) messages | 🟡 MEDIUM | PLC offline detection is heuristic (10s poll), not instant | Sprint 1 |
| 11 | Plaintext DB credentials in `appsettings.json` | 🔴 CRITICAL | Credentials in source-controlled file — security violation | Sprint 1 (pre-deploy) |
| 12 | No structured JSON logging / correlation IDs | 🟡 MEDIUM | Cannot correlate scan cycle → MQTT publish → browser in logs | Sprint 2 |
| 13 | No scan_sequence_id on cache entries | 🟡 MEDIUM | UI may show partial scan state (mixed cycle data) | Sprint 2 |
| 14 | PLC tags not in `tag_master` (appsettings path) | 🟡 MEDIUM | No DB historization, no RBAC area assignment | Sprint 2 (when PLC connected) |
| 15 | No config versioning / validation / rollback | 🟢 LOW | Hot-reload could activate bad config silently | Sprint 3 |
| 16 | Test hardcode in `PlcGatewayHostedService` | 🟢 LOW | Log pollution on DB failure | Sprint 1 cleanup |
| 17 | Persistence path default `D:\OpcLogs` | 🟢 LOW | Silent directory creation | Sprint 2 cleanup |
| 18 | No redundancy / HA strategy documented | 🟢 LOW | Future migration harder without defined approach | Document only |
| 19 | Python HMI Gevent scaling limit | 🟢 LOW | Greenlet starvation possible under very heavy load | Document only — not urgent |
| 20 | No write path architecture defined | 🟢 LOW | Must gate before any PLC write support is added | Document only |
| 21 | **PLC IP address not loading into worker at runtime** | 🔴 CRITICAL | `GET /api/plc/connections` shows `ipAddress: ""`, `protocol: "Unknown"`, `tagCount: 0` — DB config loads `Rockwel_PLC_001` but IP never maps into driver config. Worker fails 3 attempts at startup then enters permanent backoff. Auto-reconnect loop exists but never retries because it has no IP to connect to. | Sprint 1 (pre-PLC) |
| 22 | **`consecutiveFailures: 0` after 3 failed attempts** | 🟠 HIGH | Worker exits after 3 retries but failure counter reads 0 — diagnostics are misleading. Cannot use `consecutiveFailures` to gauge health. | Sprint 1 |
| 23 | **No formal state machine with validated transitions** | 🔴 CRITICAL | `Faulted` enum exists but `HandlePollFailure()` never triggers it. No `TransitionTo()` validation like OPC dispatcher. States set inline (`_state = Running`) — invalid transitions undetected. OPC has validated FSM, PLC does not. | Sprint 1 |
| 24 | **No MQTT `_sequenceId` per publish cycle** | 🟡 MEDIUM | OPC MQTT publisher increments `_sequenceId` per batch, PLC has none. UI cannot detect partial-scan state or correlate MQTT payloads with scan cycles. | Sprint 2 |
| 25 | **No MQTT ChangedOnly publish mode** | 🟡 MEDIUM | OPC filters changed-only tags before publish. PLC uses Bulk mode — sends all tags every cycle regardless of value change. Increases MQTT bandwidth unnecessarily. | Sprint 2 |
| 26 | **No stale change-detection entry purge** | 🟡 MEDIUM | OPC `PruneStaleChangeDetectionEntries()` removes disabled-tag entries from `_lastPublishedValue`. PLC has no equivalent — unbounded growth when tags disabled mid-run. | Sprint 2 |

---

## 4A. Code-Verified Deep Architecture Review (25-Point Analysis)

> **Status:** All findings below were verified against actual source files AND compared to OPC DA production code.  
> **Session date:** May 2026. No code changes made — documentation only.  
> **Method:** OPC working implementation (OpcStaDispatcher, OpcAutoConnectService, OpcMqttPublisherService) used as gold standard → PLC code compared against it.

| # | Topic | Code-Verified Finding | Verdict | Action |
|---|-------|-----------------------|---------|--------|
| 1 | Historian / cache coupling | Historian is a separate `BackgroundService` ✅ fully decoupled. Cache write (`PlcTagValuesPoolService`) is **synchronous inline** in polling loop — minor blocking risk. | ⚠️ Accept with fix | Sprint 1: fire-and-forget pool write (`_ = Task.Run(...)`) |
| 2 | Memory bounds | `MAX_SAMPLES_PER_TAG = 100` bounded ✅. Drop-oldest overflow policy ✅. `_totalSamplesDropped` counter ✅. WebSocket push has no backpressure mechanism. | ⚠️ Mostly OK | Doc note — monitor under load |
| 3 | Monotonic clock / backoff | `PlcWorker.cs` uses `DateTime.UtcNow` for backoff elapsed timing ⚠️. Python `app.py` uses `time.monotonic()` ✅. A system clock step (NTP, DST) can break C# reconnect backoff. **OPC uses `Task.Delay` duration-based — immune to clock jump.** | 🔴 Fix | Sprint 1: replace with `Task.Delay` or `Stopwatch` |
| 4 | Scan watchdog | No scan cycle duration tracking, no jitter detection, no overrun counter anywhere in `PlcWorker.cs`. Silent scan degradation is undetectable. **OPC `OpcStaDispatcher` has watchdog: fires every 30s, escalates Degraded→Faulted after 120s stale.** | 🔴 Fix | Sprint 1: watchdog counter + warning log + expose on diagnostics endpoint |
| 5 | Hard driver timeout | libplctag sets `Tag.Timeout = TimeSpan.FromSeconds(2)` per tag ✅ (library-level). `ReadAllTagsAsync()` uses `Task.WhenAll(readTasks)` but has **no outer `Task.WhenAny` + hard cutoff** at the worker call site — a native DLL hang bypasses per-tag timeout. **OPC `InvokeAsync<T>(func, timeout)` wraps every call with `Task.WhenAny(task, Task.Delay(timeout))`.** | 🔴 Fix | Sprint 1: wrap call with `Task.WhenAny(readTask, Task.Delay(hardTimeout))` |
| 6 | MQTT single point of failure | No MQTT auth, no TLS, no queue limits in Mosquitto config. REST fallback in `app.py` partially mitigates ✅, but fallback only covers OPC path — PLC path missing (see Gap 5). | 🔴 Fix | Sprint 1: add PLC to REST fallback. Sprint 3: Mosquitto hardening |
| 7 | Birth/Death LWT | No LWT `will_set` call found in MQTT connection code. PLC offline detection is purely heuristic (10s MQTT silence) — not event-driven. **OPC plan includes LWT in S1-11.** | 🔴 Fix | Sprint 1: add LWT on connect |
| 8 | Config versioning | `Version="1.0"` field exists in `appsettings.json` ✅, but the value is **never read or checked** in `Program.cs` or any service. No schema validation. | ⚠️ Accept with future work | Sprint 3: validate on startup, reject bad config |
| 9 | scan_sequence_id | No sequence counter found on cache entries, MQTT payloads, or in any log. Cannot detect if UI is showing mixed scan-cycle data. **OPC `_sequenceId = Interlocked.Increment(ref _sequenceId)` per publish cycle — full scan correlation.** | 🔴 Fix | Sprint 2: add incrementing seq on every scan publish |
| 10 | Structured logging | Template-style structured logging exists ✅ (`_logger.LogInformation("PlcWorker {PlcId} ...")`). No JSON sink, no Serilog, no correlation IDs across scan → MQTT → HMI. | ⚠️ Accept with future work | Sprint 2: add Serilog JSON sink |
| 11 | Security — plaintext credentials | 🔴 CRITICAL: `appsettings.json` contains `Password=cereveate@222` (PostgreSQL) and empty MQTT auth fields. File is committed in repo. | 🔴 BLOCKER — fix before deploy | Sprint 1 (pre-deploy): move all secrets to environment variables |
| 12 | Write path architecture | System is read-only today ✅. No write gate, no command topic, no ack protocol, no RBAC write role defined. Must be fully documented before any write code is written. | ✅ Accept (read-only) | Sprint 3: write path documentation |
| 13 | Redundancy | Single C# server instance. No active-standby, no load balancer, no shared-state MQTT bridge. | ✅ Accept for now | Sprint 3: document HA strategy |
| 14 | Python Gevent scaling | Gevent cooperative multitasking known limit ✅ — documented, understood. Not an issue at current tag count. | ✅ Accept | Document only |
| 15 | OPC / PLC separation | Completely separate code paths ✅ — OpcMonitorService and PlcGateway are independent. An OPC failure cannot cascade to PLC. This is a deliberate architectural strength. | ✅ STRENGTH — keep | No action needed |
| 16 | **IP address not reaching driver at runtime** | 🔴 LIVE-VERIFIED: `GET /api/plc/connections` response shows `"ipAddress": ""`, `"protocol": "Unknown"`, `"tagCount": 0`, `"pollCount": 0`. DB config loads `Rockwel_PLC_001` correctly but the IP field from `appsettings.json` (`192.168.0.20`) never maps into the worker. Worker fails 3 connect attempts at startup (no IP to reach) then enters backoff. Auto-reconnect loop is coded correctly but is useless without a valid IP. | 🔴 Fix before PLC connected | Sprint 1: S1-13 |
| 17 | **`consecutiveFailures` reads 0 after failed startup** | Live API: `"consecutiveFailures": 0` even though `"lastError": "Failed to connect after 3 attempts"`. The retry loop in `ConnectWithRetryAsync` is a separate counter from the worker-level `_consecutiveFailures` field — they are not in sync. | 🔴 Fix | Sprint 1: S1-14 |
| 18 | **No formal state machine — `Faulted` enum exists but never triggered** | `PlcWorkerState.Faulted` defined in enum but `HandlePollFailure()` never transitions to it. No `TransitionTo()` validated method like `OpcStaDispatcher.TransitionTo()`. States set inline (`_state = PlcWorkerState.Running`) — invalid transitions undetected. **OPC `IsValidTransition(from, to)` enforces FSM, logs REJECTED transitions at ERROR.** | 🔴 Fix | Sprint 1: add `TransitionTo()` + trigger Faulted on 5+ consecutive errors |
| 19 | **MQTT `_sequenceId` missing in PLC publish** | `OpcMqttPublisherService` increments `_sequenceId` per publish, writes `SequenceId` field to every entry. PLC MQTT has no sequence tracking — cannot correlate payload to scan cycle. | 🔴 Fix | Sprint 2: add `_sequenceId` to PLC MQTT publish |
| 20 | **MQTT ChangedOnly mode missing in PLC** | OPC: `PublishMode: ChangedOnly` — only sends tags whose value changed since last publish. `_lastPublishedValue` dict tracks previous state. PLC uses **Bulk mode** — sends all tags every cycle regardless of change. | 🟠 Consider | Sprint 2: evaluate ChangedOnly for PLC (bandwidth optimization) |
| 21 | **Stale change-detection entry purge missing** | OPC `PruneStaleChangeDetectionEntries()` removes disabled-tag entries from `_lastPublishedValue` dict every 60s. PLC has no equivalent — unbounded growth when tags disabled mid-run. | 🟠 Fix | Sprint 2: add purge logic |
| 22 | **No `/api/plc/diagnostics` endpoint** | OPC plan: `GET /api/health/dispatcher` returns threadId, apartment, queueDepth, opsProcessed, timeoutCount, state, lastSuccess, lastHeartbeat. PLC `PlcWorker.GetStatus()` returns rich diagnostics (`consecutiveFailures`, `avgReadTimeMs`, `scanRateStats`) but **no REST controller exposes this**. Only `/api/plc/connections` and `/api/plc/health` (pool-level) exist. | 🔴 Fix | Sprint 1: add `PlcController.GetDiagnostics()` endpoint |
| 23 | **Python REST fallback missing PLC path** | `_rest_fallback_poller()` calls `GET /api/opc/values` when MQTT dies. PLC tags are NOT covered — when MQTT drops, PLC tags silently go blank in browser. The C# endpoint `/api/plc/values` exists, Python just never calls it. | 🔴 Fix | Sprint 1: add PLC endpoint call to `_rest_fallback_poller()` |
| 24 | **No per-source MQTT liveness (PLC vs OPC)** | `_transport_state["last_mqtt_msg_at"]` stamped on every `on_mqtt_message()`. All topics (OPC + PLC) share the same timestamp. When PLC offline while OPC alive, Python cannot distinguish sources. **Need separate `last_plc_mqtt_msg_at`.** | 🟠 Fix | Sprint 2: track per-source liveness |
| 25 | **`age_ms` / `quality: Stale` missing on PLC cache** | `PlcTagValueCacheEntry` has `CachedAt` but `age_ms` is never computed. `GetAllTagValues()` returns raw entries — no age. OPC Fix #5 adds `age_ms = _compute_age_ms()` to every response. PLC has `quality: Uncertain` but no `Stale` enum value. Pool `IsHealthy()` checks overall age but never propagates to individual entry quality. | 🔴 Fix | Sprint 1: compute `age_ms` in API response + add `Stale` quality |

### Key Code Locations Referenced in This Analysis

| File | Relevant Lines | Finding |
|------|---------------|---------|
| `CSharpBackend/Services/PlcGateway/Services/PlcWorker.cs` | ~350–370 | Cache write sync inline in poll loop (Point 1) |
| `CSharpBackend/Services/PlcGateway/Services/PlcWorker.cs` | backoff logic | `DateTime.UtcNow` used for elapsed (Point 3) |
| `CSharpBackend/Services/PlcGateway/Drivers/RockwellDriver.cs` | `ReadAllTagsAsync()` | `Task.WhenAll` — no outer timeout (Point 5) |
| `CSharpBackend/Services/PlcGateway/Services/PlcSampleBufferService.cs` | constants | `MAX_SAMPLES_PER_TAG = 100`, drop-oldest ✅ (Point 2) |
| `CSharpBackend/appsettings.json` | DB connection string | Plaintext `Password=cereveate@222` (Point 11) |
| `HMI/app.py` | `_rest_fallback_poller()` ~L1466 | Only calls `/api/opc/values` — PLC path missing (Point 6 / Gap 5) |
| `HMI/app.py` | backoff timing | `time.monotonic()` ✅ (Point 3 — Python side is correct) |
| `CSharpBackend/Services/PlcGateway/Services/PlcWorker.cs` | `HandlePollFailure()` | Never calls `TransitionTo(Faulted)` (Point 18) |
| `CSharpBackend/Services/PlcGateway/Services/PlcWorker.cs` | `ConnectWithRetryAsync()` | `_consecutiveFailures` NOT incremented (Point 17) |
| `CSharpBackend/Services/OpcStaDispatcher.cs` | `TransitionTo()` method | Validated FSM with `IsValidTransition()` (gold standard for Point 18) |
| `CSharpBackend/Services/OpcMqttPublisherService.cs` | `_sequenceId` | `Interlocked.Increment(ref _sequenceId)` per batch (Point 19) |
| `CSharpBackend/Services/OpcMqttPublisherService.cs` | `PruneStaleChangeDetectionEntries()` | Purge disabled-tag entries every 60s (Point 21) |

---

## 5. Target Architecture — Production-Grade Final State

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             C# PLC GATEWAY (Target)                              │
│                                                                                   │
│  PlcWorker State Machine per PLC:                                                │
│    Created → Starting → Running                                                  │
│                       ↘ Faulted (5 consec failures / 2 min)                     │
│                            └─ Cooldown (5 min → 10 min → 20 min ...)            │
│                                 └─ Connecting (retry) → Running (on success)    │
│                                                                                   │
│  PlcTagValuesPoolService:                                                        │
│    ✅ age_ms on every entry                                                      │
│    ✅ quality: Good / Stale / Disconnected / Unknown                             │
│    ✅ max-age eviction (300s) — stale flag, not removal                          │
│                                                                                   │
│  GET /api/plc/diagnostics   (new)                                                │
│    → per worker: state, consecutiveFailures, lastSuccessTime,                   │
│      totalPolls, successfulPolls, avgReadTimeMs, tagCount, lastError            │
│                                                                                   │
│  GET /api/plc/connections   (existing — already used by Python proxy)           │
│    → fields: isConnected, lastError, tagCount, lastPollTime, consecutiveFailures│
└──────────────────────────────────────────────────────────────────────────────────┘
              │ MQTT  +  REST fallback
              ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                         PYTHON HMI (Target)                                      │
│                                                                                   │
│  Per-source liveness tracking:                                                   │
│    last_opc_mqtt_msg_at  (existing)                                              │
│    last_plc_mqtt_msg_at  (NEW — per PlcId in future)                            │
│                                                                                   │
│  Tag cache write — PLC path:                                                     │
│    age_ms = _compute_age_ms(tag.get('timestamp'))   (apply existing helper)     │
│    quality propagated from C# response                                           │
│    Stale tags broadcast with quality='STALE' marker                              │
│                                                                                   │
│  /api/system-status:                                                             │
│    transport.plc_sources: { plcId: { lastMsgAt, isStale, tagCount } }           │
└──────────────────────────────────────────────────────────────────────────────────┘
              │ Socket.IO
              ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                         REACT HMI (Target)                                       │
│                                                                                   │
│  Tag value display:                                                              │
│    quality='STALE' → value shown in grey with "(stale Xs ago)" tooltip          │
│    quality='Disconnected' → value shown as "---" with red dot                   │
│                                                                                   │
│  OPC/PLC status banner (existing):                                               │
│    ⚠ PLC Rockwel_PLC_001: NOT CONNECTED  (already working)                     │
│    + age indicator: "Last data: 4m 32s ago" when stale                          │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Implementation Sprint Plan

### Sprint 1 — C# + Python Hardening (do before connecting physical PLC)

| ID | Task | File | Effort |
|----|------|------|--------|
| S1-1 | PLC Worker state machine — add `Faulted` + `Cooldown` states | `PlcWorker.cs` | Medium |
| S1-1a | **Add validated `TransitionTo()` method (OPC pattern)** — enforce FSM with `IsValidTransition()`, log REJECTED transitions at ERROR | `PlcWorker.cs` | Small |
| S1-2 | Circuit breaker — 5 failures / 2 min → Faulted → 5 min cooldown | `PlcWorker.cs` | Medium |
| S1-3 | Add `age_ms` to `PlcTagValueCacheEntry` and all API responses | `PlcTagValuesPoolService.cs`, `PlcController.cs` | Small |
| S1-4 | Add `quality` enum propagation (Good / Stale / Disconnected) | `PlcTagValuesPoolService.cs` | Small |
| S1-4a | **Add `PlcTagQuality.Stale` enum value** — currently only has `Uncertain`, need explicit `Stale` for age-based degradation | `PlcTagValuesPoolService.cs` | Trivial |
| S1-5 | `GET /api/plc/diagnostics` endpoint — per-worker stats | `PlcController.cs` | Small |
| S1-5a | **Expose `PlcWorker.GetStatus()` data via new endpoint** — `state`, `consecutiveFailures`, `lastSuccessTime`, `avgReadTimeMs`, `scanRateStats` | `PlcController.cs` | Small |
| S1-6 | Remove test hardcode from `PlcGatewayHostedService` | `PlcGatewayHostedService.cs` | Trivial |
| S1-7 | **Add PLC REST fallback path** — `_rest_fallback_poller()` must also call `GET /api/plc/values` when MQTT is dead; merge into `latest_tag_values` with `source='REST_FALLBACK_PLC'` | `HMI/app.py` | Small |
| S1-8 | **Move all credentials to environment variables** — `appsettings.json` must reference `%DB_PASSWORD%`, `%MQTT_PASSWORD%` etc; never commit plaintext passwords | `appsettings.json`, deploy scripts | Small |
| S1-9 | **Hard driver timeout at worker level** — wrap `ReadAllTagsAsync()` call in `Task.WhenAny(readTask, Task.Delay(hardTimeout))` to prevent native libplctag hang from freezing scan loop | `PlcWorker.cs` | Small |
| S1-10 | **Scan watchdog** — track scan cycle elapsed; if any scan exceeds 2× expected interval emit a warning log; counter exposed on `/api/plc/diagnostics` | `PlcWorker.cs` | Small |
| S1-11 | **MQTT Birth/Death LWT** — on connect publish `plc/status/alive`, set LWT to `plc/status/dead` so subscribers detect drop instantly rather than via 10s poll | `PlcWorker.cs` or MQTT helper | Small |
| S1-12 | **Replace `DateTime.UtcNow` backoff with `Task.Delay` or `Stopwatch`** — monotonic clock immune to system clock adjustments | `PlcWorker.cs` | Trivial |
| S1-13 | **Fix IP address mapping from DB config into driver** — `PlcConfigLoaderService` loads `Rockwel_PLC_001` from DB but `ipAddress` arrives empty at runtime; trace mapping from DB record → `PlcWorkerConfig` → driver init and fix the missing field | `PlcConfigLoaderService.cs`, `PlcGatewayHostedService.cs` | Small |
| S1-14 | **Fix `consecutiveFailures` counter** — after 3 failed connect attempts counter reads 0; increment `_consecutiveFailures` inside `ConnectWithRetryAsync()` on every failed attempt | `PlcWorker.cs` | Trivial |

### Sprint 2 — Python HMI + DB Prep + Observability (do when PLC is being connected)

| ID | Task | File | Effort |
|----|------|------|--------|
| S2-1 | Apply `_compute_age_ms()` to PLC MQTT path in `on_mqtt_message()` | `app.py` | Small |
| S2-2 | Add `last_plc_mqtt_msg_at` liveness tracking separate from OPC | `app.py` | Small |
| S2-3 | Expose per-PLC transport state in `/api/system-status` | `app.py` | Small |
| S2-4 | Insert PLC tags into `historian_meta.tag_master` | SQL migration | Medium |
| S2-5 | Assign `plant_id`/`area_id` to PLC tags for RBAC area filtering | SQL migration | Small |
| S2-6 | **Add `scan_sequence_id`** — increment per scan cycle; include in every cache entry and MQTT payload so UI can detect partial/stale cycles | `PlcWorker.cs`, `PlcTagValueCacheEntry` | Small |
| S2-6a | **Mirror OPC `_sequenceId` pattern** — `Interlocked.Increment(ref _sequenceId)` in polling loop, write to `SequenceId` field in MQTT payload | `PlcWorker.cs`, MQTT publisher | Small |
| S2-7 | **Structured JSON logging + correlation IDs** — add Serilog JSON sink; include `PlcId`, `ScanSeq`, `TagCount` on each scan log line; enables log correlation across scan → MQTT → browser | `Program.cs`, `PlcWorker.cs` | Medium |
| S2-8 | **MQTT ChangedOnly publish mode (optional optimization)** — mirror `OpcMqttPublisherService` pattern: track `_lastPublishedValue` dict, only publish changed tags | PLC MQTT publisher | Medium |
| S2-9 | **Stale change-detection entry purge** — add `PruneStaleChangeDetectionEntries()` to remove disabled-tag entries from `_lastPublishedValue` every 60s | PLC MQTT publisher | Small |

### Sprint 3 — React HMI + Deployment Hardening (do after Sprint 2 verified)

| ID | Task | File | Effort |
|----|------|------|--------|
| S3-1 | Stale quality visual — grey text + "(stale Xs ago)" tooltip | Tag value display component | Small |
| S3-2 | `---` display for `quality='Disconnected'` tags | Tag value display component | Small |
| S3-3 | "Last data: Xs ago" indicator next to PLC banner | `IndustrialHMIPrototype.tsx` | Small |
| S3-4 | **Mosquitto hardening** — enable username/password auth, TLS listener :8883, set `max_queued_messages`, `persistence true`, `autosave_interval 300` | `mosquitto.conf` | Medium |
| S3-5 | **Config versioning + validation** — read `Version` field in `appsettings.json`; validate schema on startup; reject + log if config fails validation; no silent hot-reload of bad config | `appsettings.json`, `Program.cs` | Small |
| S3-6 | **Write path gate documentation** — define command topic schema `plc/cmd/{plc_id}/{tag}`, acknowledge topic, write confirmation timeout, rollback policy, and required user RBAC role before any write code is written | Doc only | Medium |
| S3-7 | **Redundancy / HA strategy documentation** — document failover approach (active-standby C# backend, shared DB, MQTT bridge) for future second server | Doc only | Medium |

---

## 6B. REST Fallback Architecture — OPC vs PLC Gap Analysis

### How REST Fallback Works (OPC — fully implemented)

```
MQTT dead (30s grace) + SignalR dead
          ↓
_rest_fallback_poller() activates in app.py (~L1466)
          ↓
GET http://localhost:5001/api/opc/values
          ↓
Tags merged into latest_tag_values with source='REST_FALLBACK'
          ↓
Broadcast to browser via Socket.IO
```

Code path (`app.py`):
```python
values_url = f"{base_url}/api/opc/values"   # ← OPC endpoint only
resp = requests.get(values_url, timeout=5)
# ... merge into latest_tag_values
```

### PLC REST Fallback — MISSING (Gap 5)

When MQTT dies:
- ✅ OPC tags: recovered via `GET /api/opc/values`
- ❌ PLC tags: **not recovered** — `_rest_fallback_poller()` never calls `GET /api/plc/values`

PLC tags go silently stale in the browser with no error indication.

### Target Fix (Sprint 1 — code change deferred until PLC physically connected)

```python
# In _rest_fallback_poller() — both endpoints must be called:
opc_url = f"{base_url}/api/opc/values"
plc_url = f"{base_url}/api/plc/values"

# OPC path (existing):
resp = requests.get(opc_url, timeout=5)
# merge with source='REST_FALLBACK'

# PLC path (NEW — Sprint 1 item S1-7):
resp = requests.get(plc_url, timeout=5)
# merge with source='REST_FALLBACK_PLC'
```

The C# endpoint `GET /api/plc/values` already exists — the Python caller is the only missing piece.

### Transport Priority Order (Target — both OPC and PLC)

```
Priority 1: MQTT  (low latency, real-time, both OPC and PLC publish here)
Priority 2: REST Fallback  (activates after 30s MQTT + SignalR dead)
    → Calls BOTH /api/opc/values AND /api/plc/values
    → Merged into single latest_tag_values store
    → Source tagged: 'REST_FALLBACK' or 'REST_FALLBACK_PLC'
Priority 3: Manual refresh (operator-triggered, always available)
```

---

## 7. Safety Rules for PLC Development

These mirror the 10 OPC Safety Rules established in `RESILIENCE_FIX_PLAN.md`:

1. **One fix at a time** — implement, build, verify, move to next. Never bundle multiple fixes.
2. **Test after every change** — at minimum: build succeeds + PLC tag count correct + no new errors in log.
3. **Backoff is non-negotiable** — never poll a disconnected PLC faster than 30s intervals.
4. **Circuit breaker before auto-reconnect** — state machine (Gap 1) must be done before any auto-reconnect work.
5. **`age_ms` on every tag** — no tag value leaves the C# boundary without a timestamp. No exception.
6. **`quality` field is mandatory** — consumer must never guess if a value is fresh. Good / Stale / Disconnected.
7. **MQTT failure must not block polling** — PLC polling loop and MQTT publishing are decoupled. MQTT drop = silent, polling continues.
8. **REST fallback is the safety net, not the primary path** — primary = MQTT. REST fallback activates only when MQTT is confirmed dead.
9. **No PLC tag hardcoding in code** — all tag definitions come from `tag_master` (DB primary) or `appsettings.json` (JSON fallback). Never in C# source.
10. **`tag_master` is the single source of truth** — when physical PLC is connected, all tags must be registered in `tag_master`. The `appsettings.json` fallback is for emergency bootstrap only, not production operation.

---

## 8. OPC vs PLC Architecture Comparison

| Concern | OPC DA | PLC Gateway | Gap? |
|---------|--------|-------------|------|
| Threading model | Dedicated STA thread (COM) | `Task.Run` per PLC (async) | None — PLC doesn't use COM |
| Connection isolation | Single connection (OPC server) | One worker per PLC | ✅ PLC is better — full isolation |
| Reconnect backoff | OpcAutoConnectService: 1s→2s→4s→8s→30s | PlcWorker: 30s→60s→120s | ✅ Both good |
| Circuit breaker | `OpcStaDispatcher` Degraded state (5 errors) | ❌ Not implemented for PLC | 🔴 GAP 1 |
| State machine | String-based states in Dispatcher → **Typed enum with validated transitions** | `PlcWorkerState` enum, **ad-hoc inline sets** | 🔴 PLC needs formal FSM + `TransitionTo()` |
| `age_ms` freshness | ✅ All 3 write paths (MQTT, SignalR, REST) | ❌ Not in pool or API response | 🟠 GAP 2 |
| Bounded queue | `BlockingCollection(1000)` in Dispatcher | N/A (direct async call) | None — no queue needed |
| Per-op timeout | `InvokeAsync<T>(timeout)` in Dispatcher | Driver-level `TimeoutMs` config | 🔴 No outer timeout — native DLL hang bypasses it |
| Diagnostics endpoint | `/api/health/dispatcher` (detailed) | ❌ `/api/plc/connections` (basic only) | 🟠 GAP 3 — data exists in `GetStatus()`, no endpoint |
| Config source | `logging-config.json` + `StartupTagSeedService` | `tag_master` DB + `appsettings.json` | ✅ PLC is better |
| MQTT publishing | `OpcMqttPublisherService` (ChangedOnly) | `PlcGateway.Mqtt` (Bulk only) | ⚠ Consider ChangedOnly for PLC too |
| MQTT `_sequenceId` | ✅ `Interlocked.Increment(ref _sequenceId)` per batch | ❌ Missing | 🔴 Cannot correlate scan cycles |
| MQTT stale-entry purge | ✅ `PruneStaleChangeDetectionEntries()` every 60s | ❌ Missing | 🟡 Unbounded growth risk |
| Transport arbitration | MQTT > SignalR > REST in Python | MQTT > REST in Python | ✅ SignalR not needed for PLC |
| REST fallback coverage | ✅ `/api/opc/values` called | ❌ `/api/plc/values` never called | 🔴 PLC tags go blank when MQTT dies |
| Per-source MQTT liveness | ✅ `last_mqtt_msg_at` per topic (planned) | ❌ Shared timestamp across OPC+PLC | 🟠 Cannot distinguish PLC offline from broker dead |
| Tag staleness UI | ❌ Not yet in UI | ❌ Not yet in UI | Both need Sprint 3 |
| Watchdog timer | ✅ 30s tick, 120s stale threshold, escalates Degraded→Faulted | ❌ Zero watchdog code | 🔴 Hung scan loop undetectable |
| `consecutiveFailures` tracking | ✅ Increments on any error (connect or read) | ❌ Only read errors, not connect errors | 🟠 Misleading diagnostics |
| Backoff clock safety | ✅ `Task.Delay` duration-based (immune to clock jump) | ❌ `DateTime.UtcNow` comparison (NTP/DST breaks it) | 🟠 Rare but fixable |

### Summary — PLC Must Adopt from OPC

**Blocking (fix before PLC connects):**
1. Formal state machine with `TransitionTo()` validation (like `OpcStaDispatcher`)
2. Hard timeout wrapper at worker level: `Task.WhenAny(readTask, Task.Delay(timeout))`
3. Python REST fallback must call `/api/plc/values`
4. Fix IP address mapping bug (S1-13)

**High priority (fix during integration):**
5. Add `/api/plc/diagnostics` endpoint (data already exists)
6. Watchdog timer with scan cycle tracking
7. `consecutiveFailures` increment in `ConnectWithRetryAsync()`
8. `age_ms` + `quality: Stale` in API responses

**Medium priority (polish):**
9. MQTT `_sequenceId` per publish cycle
10. Monotonic backoff with `Task.Delay` instead of `DateTime` comparison
11. Per-source MQTT liveness tracking

---

## 9. Production Readiness Checklist

**Must complete before going live with physical PLC:**

- [ ] S1-1/S1-2: PLC Worker state machine + circuit breaker
- [ ] S1-3/S1-4: `age_ms` + `quality` on all PLC API responses
- [ ] S1-5: `/api/plc/diagnostics` endpoint
- [ ] S1-6: Remove test hardcode
- [ ] S2-4: PLC tags registered in `historian_meta.tag_master`
- [ ] S2-5: `plant_id`/`area_id` assigned (RBAC correct)
- [ ] Verify `appsettings.json` IP address `192.168.0.20` matches physical PLC
- [ ] Verify Rockwell path `"1,0"` matches actual PLC backplane/slot
- [ ] Network test: `ping 192.168.0.20` from server → reply
- [ ] Port test: `Test-NetConnection -ComputerName 192.168.0.20 -Port 44818` → TcpTestSucceeded=True
- [ ] `GET /api/plc/values` returns tag values with `quality: Good`
- [ ] `GET /api/plc/connections` shows `isConnected: true` for `Rockwel_PLC_001`
- [ ] HMI top bar shows no ⚠ PLC banner (connected state)
- [ ] MQTT topic `Rockwel_PLC_001/tags/bulk` receiving messages in Mosquitto
- [ ] Python HMI broadcasting PLC tags to browser via Socket.IO
- [ ] Section H test suite passes: 35/35 (covers OPC; run equivalent for PLC)
- [ ] 30-minute soak test: zero tag gaps, zero `quality: Stale` during steady-state

---

## 10. Key File Reference

| File | Role |
|------|------|
| `CSharpBackend/appsettings.json` | PLC config fallback — IP, port, tags, MQTT settings |
| `CSharpBackend/Services/PlcGateway/Services/PlcWorker.cs` | Core polling loop, reconnect backoff, state |
| `CSharpBackend/Services/PlcGateway/Services/PlcGatewayManager.cs` | Add/remove/restart workers at runtime |
| `CSharpBackend/Services/PlcGateway/Services/PlcTagValuesPoolService.cs` | Shared cache — all reads/writes |
| `CSharpBackend/Services/PlcGateway/Services/PlcConfigLoaderService.cs` | DB + JSON config loading, MQTT topic auto-register |
| `CSharpBackend/Services/PlcGateway/Services/PlcGatewayHostedService.cs` | ASP.NET hosted service lifecycle |
| `CSharpBackend/Services/PlcGateway/Services/PlcDataLoggingService.cs` | Background polling orchestrator |
| `CSharpBackend/Services/PlcGateway/Drivers/RockwellDriver.cs` | libplctag EtherNet/IP CIP driver |
| `CSharpBackend/Services/PlcGateway/Controllers/PlcController.cs` | REST API (values, connections, health) |
| `HMI/app.py` | MQTT subscriber, REST fallback, `/api/opc-plc-status` proxy |
| `HMI/apex-hmi/src/hooks/useOpcPlcStatus.ts` | React hook — 10s poll for PLC banner |
| `HMI/apex-hmi/src/components/hmi/IndustrialHMIPrototype.tsx` | Banner: ⚠ PLC X: NOT CONNECTED |
| **OPC Reference Files (Gold Standard):** | |
| `CSharpBackend/Services/OpcStaDispatcher.cs` | Validated state machine, watchdog, hard timeout |
| `CSharpBackend/Services/OpcAutoConnectService.cs` | Reconnect backoff, consecutive failure tracking |
| `CSharpBackend/Services/OpcMqttPublisherService.cs` | `_sequenceId`, ChangedOnly mode, stale-entry purge |

---

## 11. OPC vs PLC — Detailed Code Comparison & Alignment Findings

> **Comparison method:** OPC DA production code (verified working, battle-tested) used as gold standard → PLC Gateway code compared line-by-line.  
> **Files compared:**
> - OPC: `OpcStaDispatcher.cs`, `OpcAutoConnectService.cs`, `OpcMqttPublisherService.cs`, `OpcDaService.cs`
> - PLC: `PlcWorker.cs`, `PlcGatewayManager.cs`, `PlcTagValuesPoolService.cs`, `PlcConfigLoaderService.cs`

### 11.1 State Machine Architecture

| Aspect | OPC Implementation | PLC Implementation | Gap |
|--------|-------------------|-------------------|-----|
| **State enum** | `DispatcherState` (Starting/Running/Degraded/Faulted/ShuttingDown/Stopped) | `PlcWorkerState` (Created/Starting/Connecting/Running/Disconnected/Stopping/Stopped/Faulted) | ✅ PLC has more states |
| **State transitions** | `TransitionTo(next, reason)` — validated via `IsValidTransition()`, invalid transitions REJECTED and logged | Inline assignment: `_state = PlcWorkerState.Running` — no validation | 🔴 **PLC missing validated FSM** |
| **`Faulted` state trigger** | Auto-escalates: 5 consecutive errors → `Degraded`, watchdog 120s stale + Degraded → `Faulted` | `Faulted` enum exists but **never triggered** — `HandlePollFailure()` only increments counter | 🔴 **Dead code** |
| **State logging** | Every transition logged: `"[OPC STATE] Running → Degraded | 5 consecutive dispatcher errors"` | State changes logged but no formal reason field | 🟡 Less structured |
| **Code snippet** | ```csharp<br>TransitionTo(DispatcherState.Degraded, $"{_consecutiveErrors} consecutive errors");<br>``` | ```csharp<br>_state = PlcWorkerState.Running; // ← no validation<br>``` | — |

**Recommendation:** Add `PlcWorker.TransitionTo()` method that mirrors `OpcStaDispatcher` pattern exactly.

---

### 11.2 Reconnect & Backoff Logic

| Aspect | OPC Implementation | PLC Implementation | Gap |
|--------|-------------------|-------------------|-----|
| **Backoff ladder** | `1s → 2s → 4s → 8s → 30s` (exponential, capped at 30s) | `30s → 60s → 120s` (doubles, capped at 120s) | ✅ Different strategy, both valid |
| **Backoff timing** | `await Task.Delay(delay, stoppingToken)` — duration-based | `DateTime.UtcNow < _workerNextConnectAt` — clock comparison | 🟠 **PLC vulnerable to NTP/DST clock jump** |
| **Failure counter** | `_consecutiveFailures++` on **every** error (connect or dispatch) | `_consecutiveFailures++` only in `HandlePollFailure()` — **connect errors not counted** | 🔴 **Misleading diagnostics** |
| **Offline logging** | Every attempt logged with backoff value | `_plcOfflineLogged` flag — one-time log only | ✅ PLC is cleaner (no log flood) |
| **Code snippet** | ```csharp<br>_consecutiveFailures++;<br>await Task.Delay(backoff, ct);<br>``` | ```csharp<br>_workerNextConnectAt = DateTime.UtcNow.AddSeconds(_workerBackoffSeconds);<br>if (DateTime.UtcNow < _workerNextConnectAt) continue;<br>``` | — |

**Recommendation:** Replace `_workerNextConnectAt` clock-comparison with `Task.Delay` in `PlcWorker.cs`. Increment `_consecutiveFailures` inside `ConnectWithRetryAsync()`.

---

### 11.3 Operation Timeout & Watchdog

| Aspect | OPC Implementation | PLC Implementation | Gap |
|--------|-------------------|-------------------|-----|
| **Per-operation timeout** | `InvokeAsync<T>(func, TimeSpan timeout)` — wraps every dispatcher call with `Task.WhenAny(task, Task.Delay(timeout))` | Driver has `TimeoutMs` field but **no outer timeout** at worker call site | 🔴 **Native DLL hang freezes scan loop** |
| **Timeout counter** | `Interlocked.Increment(ref _timeoutCount)` on timeout, exposed via `/api/health/dispatcher` | No timeout counter | 🔴 **Cannot detect hung calls** |
| **Watchdog timer** | `Timer` fires every 30s, checks `_lastSuccess` age, escalates `Degraded → Faulted` after 120s | **No watchdog code anywhere** | 🔴 **Silent failure risk** |
| **Heartbeat tracking** | `_lastHeartbeat` updated every 100 ops | `_lastSuccessTime` updated on every good poll | ✅ PLC has equivalent |
| **Code snippet** | ```csharp<br>if (await Task.WhenAny(task, Task.Delay(timeout)) != task) {<br>  Interlocked.Increment(ref _timeoutCount);<br>  throw new TimeoutException(...);<br>}<br>``` | ```csharp<br>readResult = await _driver.ReadAllTagsAsync(); // ← unguarded<br>``` | — |

**Recommendation:** Add `Task.WhenAny` wrapper in `PlcWorker.PollingLoopAsync()`. Add watchdog timer that fires every 30s.

---

### 11.4 MQTT Publishing Architecture

| Aspect | OPC Implementation | PLC Implementation | Gap |
|--------|-------------------|-------------------|-----|
| **Sequence ID** | `private long _sequenceId = 0;`<br>`var seq = Interlocked.Increment(ref _sequenceId);` | No sequence counter | 🔴 **Cannot correlate scan cycles** |
| **Publish mode** | `ChangedOnly` — tracks `_lastPublishedValue` dict, only sends changed tags | `Bulk` — sends all tags every cycle | 🟡 Bandwidth inefficiency |
| **Change detection** | `var isChanged = prevValue == null || prevValue != tv.Value;` | No change tracking | — |
| **Stale entry purge** | `PruneStaleChangeDetectionEntries(enabledTagIds)` every 60s or when tag set shrinks | No purge logic | 🟡 **Unbounded growth when tags disabled** |
| **IsChanged field** | `new OpcTagPublishEntry { IsChanged = isChanged, SequenceId = seq }` | Not in payload | — |
| **Code snippet** | ```csharp<br>entries.Add(new OpcTagPublishEntry {<br>  SequenceId = seq,<br>  IsChanged = isChanged<br>});<br>``` | ```csharp<br>// No sequenceId, no IsChanged field<br>``` | — |

**Recommendation:** Add `_sequenceId` to PLC MQTT publish. Consider adding `ChangedOnly` mode as optimization (not blocking).

---

### 11.5 Diagnostics & Health Endpoints

| Aspect | OPC Implementation | PLC Implementation | Gap |
|--------|-------------------|-------------------|-----|
| **Per-worker diagnostics** | `GET /api/health/dispatcher` returns: `threadId`, `apartment`, `queueDepth`, `maxQueueDepth`, `opsProcessed`, `timeoutCount`, `rejectedCount`, `state`, `lastStateChange`, `stateReason`, `lastSuccess`, `lastHeartbeat`, `lastError` | `PlcWorker.GetStatus()` returns rich data but **no REST endpoint exposes it** | 🔴 **Data exists, not accessible** |
| **Pool-level health** | `GET /api/health/opc` returns: `status`, `tagCount`, `healthScore`, `lastPollMs` | `GET /api/plc/health` returns similar | ✅ Parity |
| **Connection status** | `GET /api/health/opc` shows `isConnected` per server | `GET /api/plc/connections` shows `isConnected` per PLC | ✅ Parity |
| **Metrics snapshot** | `GetMetrics()` — lock-free read via volatile reference swap | `GetStatus()` — lock-protected via `_stateLock` | ⚠️ PLC has minor lock contention |

**Recommendation:** Add `GET /api/plc/diagnostics` controller endpoint that returns `PlcWorker.GetStatus()` data for all workers.

---

### 11.6 Python HMI Transport Layer

| Aspect | OPC Implementation | PLC Implementation | Gap |
|--------|-------------------|-------------------|-----|
| **REST fallback** | `_rest_fallback_poller()` calls `GET /api/opc/values` when MQTT dies | **Never calls `GET /api/plc/values`** | 🔴 **PLC tags go blank when MQTT drops** |
| **Per-source liveness** | `_transport_state["last_mqtt_msg_at"]` stamped on every `on_mqtt_message()` | All MQTT topics share same `last_mqtt_msg_at` timestamp | 🟠 **Cannot distinguish PLC offline from broker dead** |
| **Transport priority** | `MQTT > SignalR > REST` | `MQTT > REST` (no SignalR for PLC) | ✅ Correct — SignalR not needed |
| **Age computation** | `age_ms = _compute_age_ms(tag.get('timestamp'))` applied to OPC tags | **Not applied to PLC tags** | 🟠 **No freshness indicator** |
| **Code snippet** | ```python<br>values_url = f"{base_url}/api/opc/values"<br>resp = requests.get(values_url, timeout=5)<br>``` | ```python<br># PLC endpoint never called<br>``` | — |

**Recommendation:** Add `/api/plc/values` call to `_rest_fallback_poller()`. Add `last_plc_mqtt_msg_at` separate from `last_mqtt_msg_at`.

---

### 11.7 Cache & Pool Architecture

| Aspect | OPC Implementation | PLC Implementation | Gap |
|--------|-------------------|-------------------|-----|
| **Cache structure** | `TagValuesPoolService` — `ConcurrentDictionary<string, TagValue>` | `PlcTagValuesPoolService` — `ConcurrentDictionary<string, PlcTagValueCacheEntry>` | ✅ Parity |
| **Cache key format** | `itemId` (OPC tag name) | `"{PlcId}::{Address}"` | ✅ PLC is better (multi-PLC support) |
| **`age_ms` field** | Planned (Fix #5) | `CachedAt` exists but **`age_ms` never computed** | 🟠 **Not in API response** |
| **`quality: Stale`** | Planned (Fix #5) | `quality: Uncertain` used, **no `Stale` enum value** | 🟠 **No age-based degradation** |
| **Max-age eviction** | Planned (Fix #4) | `IsHealthy()` checks overall pool age but **not per-entry** | 🟠 **Disconnected PLC tags served indefinitely** |
| **Code snippet** | ```csharp<br>var ageSec = (DateTime.UtcNow - entry.CachedAt).TotalSeconds;<br>if (ageSec > MaxAgeSeconds)<br>  entry = entry with { Quality = PlcTagQuality.Stale };<br>``` | ```csharp<br>// No age_ms computation, no Stale quality<br>``` | — |

**Recommendation:** Add `age_ms` computation in `GetAllTagValues()`. Add `PlcTagQuality.Stale` enum value. Mark entries as `Stale` when age exceeds threshold (e.g. 10s).

---

### 11.8 Summary — Alignment Checklist

| Category | OPC (Gold Standard) | PLC (Current) | Aligned? |
|----------|-------------------|--------------|----------|
| ✅ **Worker isolation** | One connection per server | One worker per PLC | ✅ |
| ✅ **Dual config source** | JSON + DB | DB + JSON fallback | ✅ |
| ✅ **Scan rate scheduler** | Multiple groups per rate | Per-tag scan rate | ✅ |
| ✅ **MQTT fire-and-forget** | `_ = Task.Run(async () => publish)` | Same pattern | ✅ |
| ✅ **Reconnect backoff** | Exponential with cap | Exponential with cap | ✅ |
| 🔴 **Formal state machine** | Validated `TransitionTo()` | Inline sets, no validation | ❌ |
| 🔴 **Circuit breaker** | 5 errors → Degraded, watchdog → Faulted | `Faulted` never triggered | ❌ |
| 🔴 **Watchdog timer** | 30s tick, 120s threshold | No watchdog | ❌ |
| 🔴 **Hard timeout wrapper** | `Task.WhenAny` on every call | No outer timeout | ❌ |
| 🔴 **REST fallback PLC** | Covers OPC | Doesn't cover PLC | ❌ |
| 🔴 **`age_ms` / `Stale`** | Planned | Not computed | ❌ |
| 🔴 **MQTT `_sequenceId`** | Per batch | Missing | ❌ |
| 🔴 **`/api/plc/diagnostics`** | Detailed | Missing endpoint | ❌ |
| 🟠 **Backoff monotonic clock** | `Task.Delay` | `DateTime` comparison | ⚠️ |
| 🟠 **`consecutiveFailures`** | All errors counted | Only read errors | ⚠️ |
| 🟠 **Per-source liveness** | Planned | Shared timestamp | ⚠️ |
| 🟡 **MQTT ChangedOnly** | Yes | Bulk only | ⚠️ |
| 🟡 **Stale-entry purge** | Yes | Missing | ⚠️ |

**Priority to fix (before PLC connects):**
1. Formal state machine with `TransitionTo()` validation
2. Hard timeout wrapper: `Task.WhenAny(readTask, Task.Delay(timeout))`
3. Python REST fallback add `/api/plc/values`
4. Fix IP address mapping bug (S1-13)

**Key insight:** PLC architecture is ~80% aligned with OPC. The missing 20% are critical safety/observability features that OPC learned through production battle-testing. Adopting them proactively prevents future incidents.

---

## 12. Pre-Production Readiness — OPC Lessons Applied to PLC

**Based on OPC production experience, these are NON-NEGOTIABLE before PLC goes live:**

### 12.1 Must-Have (Blocking)
- [ ] Validated state machine — invalid transitions MUST be rejected and logged
- [ ] Circuit breaker — runaway reconnect loops MUST trigger Faulted state
- [ ] Hard timeout on every driver call — native DLL hangs MUST be detected
- [ ] Watchdog timer — scan loop freezes MUST be detected within 30s
- [ ] REST fallback covers PLC — MQTT failure MUST NOT blank the UI
- [ ] `consecutiveFailures` accurate — diagnostics MUST reflect reality
- [ ] `/api/plc/diagnostics` endpoint — per-worker health MUST be queryable
- [ ] IP address mapping fixed — worker MUST receive correct IP from config
- [ ] Plaintext credentials removed — secrets MUST be in environment variables

### 12.2 Should-Have (Before Scale)
- [ ] `age_ms` on every tag — UI MUST show freshness
- [ ] `quality: Stale` degradation — old values MUST be marked
- [ ] MQTT `_sequenceId` — scan cycles MUST be correlatable in logs
- [ ] Per-source MQTT liveness — PLC offline MUST be distinguishable from broker failure
- [ ] Monotonic backoff clock — backoff MUST be immune to NTP/DST

### 12.3 Nice-to-Have (Polish)
- [ ] MQTT ChangedOnly mode — bandwidth optimization
- [ ] Stale change-detection purge — unbounded growth prevention
- [ ] Structured JSON logging — Serilog sink with correlation IDs
- [ ] Scan cycle jitter metrics — performance degradation detection

**OPC taught us:** Systems appear to work in dev/staging. Production exposes every gap. Fix proactively, not reactively.

---

## 13. Enterprise-Grade Architecture Additions — Expert Review Findings

> **Review date:** May 2026  
> **Reviewer:** Industrial automation expert (SCADA/HMI architecture specialist)  
> **Verdict:** Architecture is already at industrial-grade design level. Foundation is strong. The following additions are required to reach platform-grade maturity.

### ARCHITECTURAL STRENGTHS CONFIRMED ✅

| Strength | Why It Matters | Industry Impact |
|----------|----------------|-----------------|
| **Worker isolation (one PLC = one worker)** | Prevents cascading freezes, driver deadlocks, scan starvation | Most badly designed systems poll all PLCs in one global loop — this does not |
| **OPC and PLC separation** | Avoids STA contamination, COM deadlocks, threading conflicts | **Critical decision — never merge OPC and PLC engines** |
| **REST fallback strategy** | Browser never silently freezes when MQTT dies | Correct philosophy for industrial HMIs |
| **Modular fault-isolated design** | Each component can fail independently without system collapse | **This decision will save the platform at scale** |
| **Production thinking already present** | Document includes operator safety, stale values, diagnostics, watchdogs, reconnect policy, HA strategy | Beyond most SME industrial systems |

---

### 13.1 ADD: Global System Supervisor Layer 🔴 VERY IMPORTANT

**Problem:** Each PLC worker supervises itself, but there is **no global supervisor above all workers**.

**Why critical:** When system grows beyond 10 PLCs, you need coordinated shutdown, degraded mode, overload protection, broker failure policy, emergency recovery, memory pressure handling, CPU protection, platform-level health score.

**Current architecture:**
```
Worker → independent (self-supervised)
```

**Required architecture:**
```
IndustrialSystemSupervisorService (NEW)
    ├── monitors all workers
    ├── monitors memory usage
    ├── monitors MQTT broker health
    ├── monitors DB connection pool
    ├── monitors queue depth across system
    ├── monitors CPU starvation
    ├── can degrade system globally
    └── coordinated graceful shutdown
```

**New Component: `IndustrialSystemSupervisorService`**

Responsibilities:
- **Global health score** — aggregate health of all subsystems (OPC + PLC + MQTT + DB + Python)
- **Overload mode** — detect when system is under stress (CPU >80%, memory >90%, queue depth >1000)
- **Throttling** — dynamically slow scan rates when overload detected
- **Graceful degradation** — disable low-priority features first (trends, diagnostics) to preserve critical alarms
- **Coordinated restart** — when MQTT broker dies, pause all workers, wait for recovery, resume in staggered order
- **Emergency shutdown** — kill-switch for runaway loops or memory leaks

**Implementation sketch:**
```csharp
public class IndustrialSystemSupervisorService : BackgroundService
{
    private SystemHealthState _globalHealth;
    
    public enum SystemHealthState
    {
        Healthy,           // All subsystems normal
        Degraded,          // One subsystem struggling
        Overloaded,        // CPU/memory pressure
        CriticalFailure,   // Multiple subsystems down
        EmergencyShutdown  // Manual kill-switch activated
    }
    
    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            var cpu = GetCpuUsage();
            var mem = GetMemoryUsage();
            var mqttHealth = _mqttPublisher.IsConnected;
            var dbHealth = _dbPool.IsHealthy();
            var workerHealth = _plcGatewayManager.GetAllWorkerHealth();
            
            if (cpu > 80 || mem > 90) TransitionTo(SystemHealthState.Overloaded);
            if (!mqttHealth && !dbHealth) TransitionTo(SystemHealthState.CriticalFailure);
            
            // Degradation policy
            if (_globalHealth == SystemHealthState.Overloaded)
            {
                SlowNonCriticalScans();
                DisableTrendLogging();
            }
            
            await Task.Delay(TimeSpan.FromSeconds(10), ct);
        }
    }
}
```

**When to implement:** Sprint 3 (after basic PLC connectivity proven stable).

---

### 13.2 ADD: Scan Budget Protection 🔴 VERY IMPORTANT

**Problem:** Each worker scans independently. There is **no total system scan budget**. With 40 PLCs × 5000 tags × aggressive scan rates, system can destroy CPU, MQTT, network, and browser.

**Required component: `GlobalScanBudgetManager`**

Responsibilities:
- **Reject impossible scan rates** — if user requests 10ms scan on 1000 tags, reject config with clear error
- **Throttle workers** — if total system load exceeds budget, slow low-priority workers first
- **Prioritize critical tags** — alarms/trips always get full scan rate, diagnostics can degrade
- **Dynamic adjustment** — under overload, automatically increase scan intervals for non-critical tags

**Example budget calculation:**
```
Total CPU budget: 4 cores × 80% = 3.2 cores available
Per-scan overhead: ~5ms per 100 tags (measured)
Max sustainable scans/sec: (3.2 cores × 1000ms) / 5ms = 640 scans/sec

If config requests:
  PLC1: 100 tags @ 100ms = 10 scans/sec
  PLC2: 200 tags @ 50ms  = 40 scans/sec
  PLC3: 5000 tags @ 10ms = 500 scans/sec ← REJECTED (exceeds budget)
```

**Implementation approach:**
```csharp
public class GlobalScanBudgetManager
{
    private const int MaxSystemScansPerSecond = 500;
    
    public bool ValidateScanConfig(List<PlcConfigEntry> configs)
    {
        var totalScansPerSec = configs.Sum(c => 
            c.Tags.Count * (1000.0 / c.PollingIntervalMs));
        
        if (totalScansPerSec > MaxSystemScansPerSecond)
        {
            _logger.LogError(
                "Scan budget exceeded: {Requested} scans/sec > {Max} max",
                totalScansPerSec, MaxSystemScansPerSecond);
            return false;
        }
        return true;
    }
}
```

**When to implement:** Sprint 2 (before multi-PLC production load).

---

### 13.3 ADD: Priority Classes for Tags 🔴 CRITICAL FOR OVERLOAD

**Problem:** All tags are treated equally. Under overload, system cannot decide what to sacrifice first.

**Required: Tag priority classification**

| Priority | Example Tags | Degradation Policy |
|----------|--------------|-------------------|
| **Critical** | Alarms, trips, safety interlocks | Never degraded — always full scan rate |
| **High** | Live process values (pressure, temp, level) | Degrade only under severe overload (2× scan rate max) |
| **Medium** | Trend data, setpoints | Can degrade to 5× scan rate |
| **Low** | Diagnostics, counters, status | Can degrade to 10× or pause entirely |

**DB schema addition:**
```sql
ALTER TABLE historian_meta.tag_master 
  ADD COLUMN priority INT DEFAULT 2;  -- 0=Critical, 1=High, 2=Medium, 3=Low

CREATE INDEX idx_tag_master_priority ON historian_meta.tag_master(priority, scan_rate_ms);
```

**Degradation logic:**
```csharp
if (_systemSupervisor.GlobalHealth == SystemHealthState.Overloaded)
{
    // Critical tags: keep 100% scan rate
    // High: 2× slower
    // Medium: 5× slower
    // Low: pause
    
    foreach (var worker in _workers.Values)
    {
        var tags = worker.GetTags();
        foreach (var tag in tags)
        {
            if (tag.Priority == TagPriority.Critical) continue;
            if (tag.Priority == TagPriority.Low) 
                worker.PauseTag(tag.Address);
            else
                worker.SlowTag(tag.Address, factor: tag.Priority == TagPriority.High ? 2 : 5);
        }
    }
}
```

**When to implement:** Sprint 3 (after scan budget protection).

---

### 13.4 ADD: MQTT Backpressure Protection 🔴 CRITICAL FUTURE ISSUE

**Problem:** Document partially mentions this but not deeply enough. You MUST protect against **producer faster than consumer**: PLC scan faster than MQTT publish, browser slower than backend, network congestion.

**Required protections:**

1. **Bounded publish queue** — cap MQTT queue at 10,000 messages
2. **Message drop policy** — when queue full, drop oldest low-priority messages first
3. **Coalescing** — if 5 updates for same tag are queued, drop middle 3, keep first + last
4. **"Latest value wins" policy** — for real-time values, only newest matters

**Implementation:**
```csharp
public class MqttBackpressureManager
{
    private readonly BlockingCollection<MqttMessage> _queue = new(10_000);
    
    public bool TryEnqueue(MqttMessage msg)
    {
        if (_queue.Count >= 9_000)  // 90% full
        {
            // Coalescing: if same tag already queued, replace
            var existing = _queue.FirstOrDefault(m => 
                m.Topic == msg.Topic && m.TagId == msg.TagId);
            if (existing != null)
            {
                _queue.TryTake(out _);  // remove old
                _totalCoalesced++;
            }
            
            // Drop policy: low-priority first
            if (_queue.Count >= 10_000)
            {
                if (msg.Priority == TagPriority.Low)
                {
                    _totalDropped++;
                    return false;  // drop
                }
            }
        }
        
        return _queue.TryAdd(msg);
    }
}
```

**When to implement:** Sprint 2 (before multi-PLC load).

---

### 13.5 ADD: Browser Subscription Filtering 🟠 VERY IMPORTANT (FUTURE)

**Problem:** Currently all PLC tags → browser. This will not scale. At 10,000 tags, browser CPU dies, Socket.IO traffic explodes.

**Required architecture evolution:**

**Current (Phase 1):**
```
PLC → MQTT → Python → Socket.IO → Browser (ALL tags)
```

**Future (Phase 2):**
```
PLC → MQTT → Python
                ↓
            Socket.IO (filtered per user session)
                ↓
Browser subscribes only to visible assets/tags

Example:
  User opens Pump-101 page → only Pump-101 tags stream
  User closes page → unsubscribe
```

**Implementation approach:**
```python
# In app.py Socket.IO handler
@socketio.on('subscribe_asset')
def on_subscribe_asset(data):
    asset_id = data.get('asset_id')
    sid = request.sid
    
    # Get tags for this asset from tag_master
    tags = db.query(
        "SELECT tag_id FROM tag_master WHERE asset_id = %s", 
        (asset_id,)
    )
    
    # Store subscription in session
    _session_subscriptions[sid] = set(t['tag_id'] for t in tags)
    
    # When broadcasting, filter:
    for tag_update in latest_tag_values:
        if tag_update['tag_id'] in _session_subscriptions[sid]:
            emit('tag_update', tag_update, room=sid)
```

**When to implement:** Sprint 4 (after 1000+ tags in production).

---

### 13.6 ADD: Historian Write Isolation 🔴 VERY IMPORTANT

**Problem:** Currently historian is decoupled (good), but rule is not explicitly enforced: **Historian failure MUST NEVER slow scan loop.**

**Required enforcement:**

1. **Async buffering** — historian writes go through bounded queue (never `await` in scan loop)
2. **Drop protection** — if historian queue full, drop oldest samples, log warning, keep scanning
3. **Historian queue health metrics** — expose `/api/historian/queue-health` with depth, drop count, oldest sample age

**Explicit rule in code:**
```csharp
// PlcWorker.cs — polling loop
var samples = _scheduler.GetTagsDueForScan();
var readResult = await _driver.ReadTagsAsync(samples);

// GOOD: Fire-and-forget to historian
_ = Task.Run(() => _historianIngest.BufferSamples(readResult.Values));

// BAD: Never do this (blocks scan loop)
// await _historianIngest.WriteSamplesAsync(readResult.Values);  ← FORBIDDEN
```

**Circuit breaker for historian:**
```csharp
if (_historianQueue.Count > 100_000)
{
    _logger.LogCritical("Historian queue overload — dropping samples");
    _historianQueue.Clear();  // nuclear option
}
```

**When to implement:** Sprint 1 (verify isolation exists, add metrics).

---

### 13.7 ADD: Event Journal / Audit Trail 🟡 IMPORTANT (COMPLIANCE)

**Problem:** Missing completely. Industrial systems require audit logging for compliance, diagnostics, RCA, customer trust.

**Required events to log:**

| Event | Severity | Example |
|-------|----------|---------|
| PLC disconnected | Warning | `2026-05-26T08:41:23.123Z | PLC Rockwel_PLC_001 DISCONNECTED | reason: network timeout` |
| PLC reconnected | Info | `2026-05-26T08:42:15.456Z | PLC Rockwel_PLC_001 ONLINE | tags: 128` |
| Quality degraded to Stale | Warning | `2026-05-26T08:41:30.789Z | Tag TY1101A quality: Good → Stale | age: 15s` |
| Driver timeout | Error | `2026-05-26T08:41:25.000Z | Driver timeout | PLC: Rockwel_PLC_001 | elapsed: 5000ms` |
| MQTT offline | Critical | `2026-05-26T08:40:00.000Z | MQTT broker UNREACHABLE | broker: localhost:1883` |
| REST fallback activated | Warning | `2026-05-26T08:40:30.000Z | REST fallback ACTIVATED | reason: MQTT dead 30s` |
| Operator acknowledged alarm | Info | `2026-05-26T08:43:00.000Z | Alarm ACK | user: john.doe | alarm: HH-101-HIGH` |
| Config change | Info | `2026-05-26T09:00:00.000Z | Config reloaded | PLCs: 3 → 5 | tags: 128 → 256` |

**Schema:**
```sql
CREATE TABLE historian_raw.event_journal (
    event_id BIGSERIAL PRIMARY KEY,
    event_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type VARCHAR(50) NOT NULL,  -- PLC_DISCONNECT, MQTT_OFFLINE, etc.
    severity VARCHAR(20) NOT NULL,    -- INFO, WARNING, ERROR, CRITICAL
    source VARCHAR(100),               -- PlcWorker, OpcStaDispatcher, MqttPublisher
    correlation_id UUID,               -- links related events
    operator VARCHAR(100),             -- user who triggered (if applicable)
    message TEXT,
    details JSONB
);

CREATE INDEX idx_event_journal_time ON historian_raw.event_journal(event_time DESC);
CREATE INDEX idx_event_journal_type ON historian_raw.event_journal(event_type);
```

**When to implement:** Sprint 3 (after core stability).

---

### 13.8 ADD: Configuration Validation Engine 🔴 VERY IMPORTANT

**Problem:** Config validation is partially mentioned but not comprehensive. You need **full validation before activation**.

**Required validations:**

| Check | Example Failure | Action |
|-------|----------------|--------|
| Duplicate tag IDs | Two tags both named `TY1101A` | Reject config, log error |
| Invalid scan rates | Scan rate = -1 or 0 | Reject, default to 1000ms |
| Impossible IPs | IP = `999.999.999.999` | Reject config |
| Unsupported protocols | Protocol = `BANANA` | Reject, list valid protocols |
| Circular mappings | Tag A maps to Tag B, Tag B maps to Tag A | Reject config |
| Invalid slot path | Rockwell path = `X,Y,Z` (non-numeric) | Reject, require `backplane,slot` |
| Scan budget exceeded | Total scans/sec > max capacity | Reject, show budget calc |
| Conflicting IPs | Two PLCs same IP:port | Reject, require unique endpoints |

**New component: `ConfigValidationService`**

```csharp
public class ConfigValidationService
{
    public ValidationResult Validate(List<PlcConfigEntry> configs)
    {
        var errors = new List<string>();
        
        // Duplicate tag IDs
        var tagIds = configs.SelectMany(c => c.Tags.Select(t => t.TagId)).ToList();
        var duplicates = tagIds.GroupBy(t => t).Where(g => g.Count() > 1);
        if (duplicates.Any())
            errors.Add($"Duplicate tag IDs: {string.Join(", ", duplicates.Select(d => d.Key))}");
        
        // Invalid IPs
        foreach (var config in configs)
        {
            if (!IPAddress.TryParse(config.IpAddress, out _))
                errors.Add($"Invalid IP for {config.PlcId}: {config.IpAddress}");
        }
        
        // Scan budget
        if (!_scanBudgetManager.ValidateScanConfig(configs))
            errors.Add("Scan budget exceeded");
        
        return new ValidationResult 
        { 
            IsValid = errors.Count == 0, 
            Errors = errors 
        };
    }
}
```

**Enforcement rule:** **NO config becomes active unless validated.**

**When to implement:** Sprint 2 (before multi-PLC production).

---

### 13.9 ADD: Cold Start Strategy 🟠 IMPORTANT

**Problem:** What happens when 20 PLCs reconnect simultaneously? You need **staggered reconnect startup**. Otherwise: broker spike, DB spike, CPU spike, network burst.

**Required: Randomized startup jitter**

```csharp
// In PlcGatewayHostedService.LoadAndStartPlcsAsync()
var configs = await _configLoader.LoadAllEnabledPlcsAsync();

// Instead of:
// foreach (var config in configs) await StartWorker(config);  ← all at once

// Do:
var startupJitter = TimeSpan.FromSeconds(2);  // 2s between each worker
foreach (var config in configs)
{
    await StartWorker(config);
    await Task.Delay(startupJitter);  // stagger startup
}

// Or even better: randomized jitter
var random = new Random();
foreach (var config in configs)
{
    await StartWorker(config);
    await Task.Delay(random.Next(1000, 5000));  // 1-5s random delay
}
```

**Why important:** Production plants often see "thundering herd" after power restoration. All PLCs come online simultaneously → system overload → cascade failure.

**When to implement:** Sprint 2 (before multi-PLC deployment).

---

### 13.10 ADD: Alarm Engine Architecture (RESERVE NOW) 🟡 FUTURE CRITICAL

**Problem:** Document discusses tags but not alarm engine. You eventually need full alarm management.

**Reserve architecture section now for:**

- **Alarm state machine** — NORMAL → UNACKED → ACKED → RETURN_TO_NORMAL → SHELVED
- **Alarm acknowledgement** — operator must acknowledge critical alarms
- **Shelved alarms** — temporary suppression (maintenance mode)
- **Deadband** — prevent chattering (alarm trips at 100, must drop to 95 before re-arm)
- **Chattering suppression** — if alarm flips >10 times/minute, suppress and log "CHATTERING"
- **Alarm flood protection** — max 50 new alarms/minute, beyond that enter FLOOD mode

**Schema placeholder:**
```sql
-- Reserve table structure now, implement later
CREATE TABLE historian_raw.alarm_state (
    alarm_id BIGSERIAL PRIMARY KEY,
    tag_id VARCHAR(255) REFERENCES historian_meta.tag_master(tag_id),
    alarm_type VARCHAR(50),  -- HI, HI-HI, LO, LO-LO, DEVIATION
    state VARCHAR(50),        -- NORMAL, UNACKED, ACKED, RTN, SHELVED
    priority INT,             -- 0=Critical, 1=High, 2=Medium, 3=Low
    setpoint NUMERIC,
    deadband NUMERIC,
    trip_time TIMESTAMPTZ,
    ack_time TIMESTAMPTZ,
    ack_user VARCHAR(100),
    rtn_time TIMESTAMPTZ,
    shelved_until TIMESTAMPTZ
);
```

**When to implement:** Sprint 5+ (after core PLC/OPC stability proven).

---

## 14. Biggest Architectural Risk — Python HMI Bottleneck (FUTURE)

**Problem identified:** Python HMI is currently doing too much:

- MQTT consume
- Arbitration
- Cache management
- RBAC filtering
- Socket.IO broadcasting
- REST fallback
- API proxy

**Risk:** With 100 users + many PLCs + large trends + many websocket updates → **gevent/event loop overload**.

**Not now. But later.**

**Future evolution strategy:**

**Phase 1 (Current):**
```
C# acquisition core
    ↓
MQTT broker
    ↓
Python HMI (orchestration + RBAC + Socket.IO)
    ↓
Browser
```

**Phase 2 (Future — after 100+ users):**
```
C# acquisition core
    ↓
MQTT broker
    ↓
Stateless web layer (Node.js or Go microservice)
    ↓
Browser (subscribes more directly)

Python becomes:
  - RBAC service (auth/permissions)
  - Config management
  - Alarm orchestration
  - Trend query API
```

**When to consider:** When Socket.IO latency >500ms or Python CPU >70% sustained.

**Key insight:** Python is fine for orchestration. It's not fine as a high-throughput real-time message relay at scale.

---

## 15. Architecture Maturity Scorecard — Expert Assessment

> **Reviewer:** Industrial automation expert (15+ years SCADA/HMI experience)  
> **Review date:** May 2026  
> **Assessment method:** Code review + architecture document analysis + comparison to industrial gold standards

| Area | Rating | Notes |
|------|--------|-------|
| **Separation of concerns** | A | OPC/PLC/MQTT/Python/React fully decoupled — textbook architecture |
| **Fault isolation** | A | Worker-per-PLC isolation prevents cascading failures |
| **Scalability potential** | A- | Foundation strong, needs global supervisor + scan budget for 50+ PLCs |
| **Observability** | B+ | Good diagnostics planned, needs event journal + correlation IDs |
| **Resilience** | B | REST fallback + backoff excellent, needs circuit breaker + watchdog completion |
| **Production readiness** | B | Core solid, critical safety features (timeout, stale, diagnostics) must complete |
| **Operational safety** | A- | Stale quality awareness + RBAC + quality propagation already designed in |
| **Security** | C+ | Plaintext credentials + MQTT hardening blocking issues |
| **Future scalability** | B+ | Needs backpressure + subscription filtering + global supervisor |
| **Industrial design maturity** | A- | **Already beyond most SME industrial systems** |

**Overall verdict:** This is no longer a "small application architecture." It is evolving into **industrial data platform architecture**.

**Foundation strength:** The decoupled modular fault-isolated design will save the platform at scale. **This was the most important architectural decision.**

---

## 16. Critical Path to Production — Priority Order

### 🔴 BLOCKING (Must fix before PLC connects)

1. IP mapping bug (S1-13)
2. Formal state machine with validated transitions (S1-1, S1-1a)
3. Hard timeout wrapper: `Task.WhenAny(readTask, Task.Delay(timeout))` (S1-9)
4. `age_ms` + `quality: Stale` (S1-3, S1-4, S1-4a)
5. REST fallback for PLC in Python (S1-7)
6. Credentials removal to environment variables (S1-8)
7. Watchdog timer (S1-10)
8. `/api/plc/diagnostics` endpoint (S1-5, S1-5a)
9. MQTT LWT (S1-11)
10. `consecutiveFailures` fix (S1-14)

### 🟠 HIGH PRIORITY (Before multi-PLC production)

11. Global scan budget manager
12. MQTT backpressure protection
13. Configuration validation engine
14. Cold start staggered reconnect
15. Historian write isolation verification + metrics

### 🟡 IMPORTANT (Before scale >10 PLCs)

16. Global system supervisor service
17. Tag priority classes
18. Browser subscription filtering
19. Event journal / audit trail
20. Per-source MQTT liveness tracking

### 🟢 FUTURE (Platform evolution)

21. Alarm engine architecture
22. Python HMI evolution to stateless web layer
23. MQTT ChangedOnly publish mode
24. Structured JSON logging with correlation IDs
25. HA / redundancy strategy implementation

---

## 17. Expert Final Recommendation

**This architecture is ready to evolve into an enterprise-grade industrial data platform.**

**Key decisions that will save you later:**

1. ✅ Worker isolation (one PLC = one task)
2. ✅ OPC and PLC separation (never merge)
3. ✅ REST fallback strategy
4. ✅ No hardcoded tags (DB-driven)
5. ✅ Quality propagation awareness
6. ✅ Stale data handling planned

**What must be added before scale:**

1. 🔴 Global system supervisor
2. 🔴 Scan budget protection
3. 🔴 MQTT backpressure
4. 🔴 Config validation engine
5. 🟠 Event journal
6. 🟠 Tag priority classes

**Most critical insight from expert review:**

> "Most industrial systems fail because they treat all data equally and have no degradation strategy. Your architecture already thinks in terms of fault domains, quality degradation, and operator safety. That thinking will scale. Add the global supervisor and scan budget protection, and this becomes a platform that can run a real plant."

**Recommendation: Proceed with confidence. The foundation is sound.**

---

## 18. Event Bus Architecture — Platform Evolution (Sprint 4)

> **Implementation phase:** Sprint 4 (AFTER Global Supervisor stable)  
> **Type:** Platform evolution architecture (NOT urgent fix)  
> **Scope:** BOTH OPC and PLC (unified approach)  
> **Complexity:** Lightweight, in-process initially (NO Kafka/distributed systems)  
> **Purpose:** Architectural decoupling backbone for AI/analytics/alarm extensibility

### 18.1 Why Event Bus is Needed (Strategic, Not Urgent)

**Current architecture (Sprint 1-3) works well:**
```
OPC Worker → OpcMqttPublisherService → MQTT
           → TagValuesPoolService → REST API
           → HistorianIngestService → DB

PLC Worker → PlcMqttPublisherService → MQTT
           → PlcTagValuesPoolService → REST API
           → PlcHistorianIngestService → DB
```
**This is correct separation. Nothing is broken here.**

**But future vision requires:**
- AI/ML integration
- OEE calculation
- Predictive maintenance
- Alarm engine
- Analytics pipelines
- Audit trail
- Quality monitoring

**Without event bus:** Every new feature = modify worker code → coupling grows → maintenance nightmare

**With event bus:** New features = new subscriber → zero changes to core acquisition → clean evolution

---

### 18.2 Event Bus is NOT About (Important Clarifications)

**Event bus is NOT:**
- ❌ PLC communication protocol
- ❌ Semantic intelligence layer
- ❌ Asset taxonomy system
- ❌ Historian replacement
- ❌ MQTT replacement
- ❌ Urgently needed for PLC connection

**Event bus IS:**
- ✅ Architectural decoupling backbone
- ✅ Foundation for AI/analytics extensibility
- ✅ Isolation mechanism for failures
- ✅ Replay/observability infrastructure
- ✅ Future-proof evolution strategy

**Critical distinction:** Your historian semantic layer, taxonomy model, RBAC, and acquisition isolation are **already correct**. Event bus **enhances** them, doesn't replace them.

---

### 18.3 Target Unified Architecture (Sprint 4)

**Key insight:** OPC and PLC become **event producers** with same interface. All consumers work for both.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    EVENT PRODUCERS (Unified)                         │
├─────────────────────────────────────────────────────────────────────┤
│  OPC Worker      → IndustrialEventBus.PublishAsync(event)          │
│  PLC Worker      → IndustrialEventBus.PublishAsync(event)          │
│  Future: Modbus  → IndustrialEventBus.PublishAsync(event)          │
│  Future: BACnet  → IndustrialEventBus.PublishAsync(event)          │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────┐
        │   IndustrialEventBus (Lightweight) │
        │   - Bounded queue (10k events)     │
        │   - Priority dispatch              │
        │   - Async handlers                 │
        │   - Correlation IDs                │
        │   - Replay buffer (30s)            │
        └────────────────┬───────────────────┘
                         │
         ┌───────────────┴───────────────┬─────────────────┬─────────────────┐
         ▼                               ▼                 ▼                 ▼
┌────────────────┐           ┌─────────────────┐  ┌──────────────┐  ┌──────────────┐
│ MQTT Subscriber│           │Historian Writer │  │Alarm Engine  │  │AI/Analytics  │
│  (OPC + PLC)   │           │  (OPC + PLC)    │  │ (Future)     │  │ (Future)     │
└────────────────┘           └─────────────────┘  └──────────────┘  └──────────────┘
         │                               │                 │                 │
         ▼                               ▼                 ▼                 ▼
    Mosquitto                        PostgreSQL        AlarmDB          ML Pipeline
```

**Key benefit:** Write subscriber ONCE → works for OPC, PLC, Modbus, BACnet, anything.

---

### 18.4 Core Event Types (Start Minimal)

**Do NOT overbuild. Start with ONLY these:**

```csharp
// Core event interface
public interface IIndustrialEvent
{
    Guid EventId { get; }
    string EventType { get; }
    DateTime TimestampUtc { get; }
    string Source { get; }        // "OPC" or "PLC_Rockwel_PLC_001"
    Guid CorrelationId { get; }
    EventSeverity Severity { get; }
}

// Tag value event (most common)
public class TagValueUpdatedEvent : IIndustrialEvent
{
    public string Source { get; set; }          // "PLC_Rockwel_PLC_001" or "OPC_Matrikon"
    public string TagId { get; set; }
    public object? Value { get; set; }
    public string Quality { get; set; }         // "Good", "Stale", "Bad"
    public DateTime Timestamp { get; set; }
    public long SequenceId { get; set; }
    public Dictionary<string, object> Metadata { get; set; }  // extensible
}

// Scan cycle event (for diagnostics)
public class ScanCycleCompletedEvent : IIndustrialEvent
{
    public string Source { get; set; }          // which worker
    public int TagCount { get; set; }
    public long DurationMs { get; set; }
    public bool Success { get; set; }
    public long SequenceId { get; set; }
}

// Connection events
public class AcquisitionConnectedEvent : IIndustrialEvent
{
    public string Source { get; set; }          // "PLC_Rockwel_PLC_001"
    public string Protocol { get; set; }        // "Rockwell", "OPC-DA"
    public string Endpoint { get; set; }        // "192.168.0.20:44818"
}

public class AcquisitionDisconnectedEvent : IIndustrialEvent
{
    public string Source { get; set; }
    public string Reason { get; set; }
    public int ConsecutiveFailures { get; set; }
}

// Quality degradation event
public class QualityDegradedEvent : IIndustrialEvent
{
    public string Source { get; set; }
    public string TagId { get; set; }
    public string PreviousQuality { get; set; }
    public string CurrentQuality { get; set; }
    public string Reason { get; set; }          // "age > 10s", "driver timeout"
}
```

**That's it. Don't add more initially.**

---

### 18.5 Event Bus Interface (Minimal Contract)

```csharp
public interface IIndustrialEventBus
{
    /// <summary>Publish event asynchronously (fire-and-forget, never blocks producer)</summary>
    Task PublishAsync<TEvent>(TEvent @event) where TEvent : IIndustrialEvent;
    
    /// <summary>Subscribe to event type with async handler</summary>
    void Subscribe<TEvent>(Func<TEvent, Task> handler) where TEvent : IIndustrialEvent;
    
    /// <summary>Unsubscribe handler</summary>
    void Unsubscribe<TEvent>(Func<TEvent, Task> handler) where TEvent : IIndustrialEvent;
    
    /// <summary>Get diagnostics (queue depth, drop count, subscriber count)</summary>
    EventBusDiagnostics GetDiagnostics();
}
```

---

### 18.6 Implementation (Lightweight, In-Process)

```csharp
public class IndustrialEventBus : IIndustrialEventBus, IDisposable
{
    private readonly Channel<IIndustrialEvent> _channel;
    private readonly ConcurrentDictionary<Type, List<Func<IIndustrialEvent, Task>>> _subscribers;
    private readonly ILogger<IndustrialEventBus> _logger;
    private readonly Task _dispatchTask;
    private readonly CancellationTokenSource _cts;
    
    // Bounded queue — CRITICAL
    private const int MaxQueueDepth = 10_000;
    
    // Replay buffer (last 30s of events)
    private readonly ConcurrentQueue<IIndustrialEvent> _replayBuffer;
    private const int MaxReplayBufferSize = 5_000;
    
    // Metrics
    private long _totalPublished;
    private long _totalDropped;
    private long _totalDispatched;
    
    public IndustrialEventBus(ILogger<IndustrialEventBus> logger)
    {
        _logger = logger;
        _subscribers = new();
        _replayBuffer = new();
        
        // Bounded channel with drop-oldest policy on full
        _channel = Channel.CreateBounded<IIndustrialEvent>(new BoundedChannelOptions(MaxQueueDepth)
        {
            FullMode = BoundedChannelFullMode.DropOldest
        });
        
        _cts = new CancellationTokenSource();
        _dispatchTask = Task.Run(DispatchLoopAsync);
    }
    
    public async Task PublishAsync<TEvent>(TEvent @event) where TEvent : IIndustrialEvent
    {
        if (await _channel.Writer.WaitToWriteAsync(_cts.Token))
        {
            if (_channel.Writer.TryWrite(@event))
            {
                Interlocked.Increment(ref _totalPublished);
                
                // Add to replay buffer
                _replayBuffer.Enqueue(@event);
                while (_replayBuffer.Count > MaxReplayBufferSize)
                    _replayBuffer.TryDequeue(out _);
            }
            else
            {
                Interlocked.Increment(ref _totalDropped);
                _logger.LogWarning("Event dropped (queue full): {EventType}", @event.EventType);
            }
        }
    }
    
    public void Subscribe<TEvent>(Func<TEvent, Task> handler) where TEvent : IIndustrialEvent
    {
        var eventType = typeof(TEvent);
        var wrappedHandler = new Func<IIndustrialEvent, Task>(async e => await handler((TEvent)e));
        
        _subscribers.AddOrUpdate(
            eventType,
            _ => new List<Func<IIndustrialEvent, Task>> { wrappedHandler },
            (_, list) => { list.Add(wrappedHandler); return list; }
        );
        
        _logger.LogInformation("Subscriber added for {EventType}", eventType.Name);
    }
    
    private async Task DispatchLoopAsync()
    {
        await foreach (var @event in _channel.Reader.ReadAllAsync(_cts.Token))
        {
            var eventType = @event.GetType();
            
            if (_subscribers.TryGetValue(eventType, out var handlers))
            {
                foreach (var handler in handlers)
                {
                    try
                    {
                        // Fire-and-forget to prevent slow subscriber blocking others
                        _ = Task.Run(async () =>
                        {
                            try
                            {
                                await handler(@event);
                                Interlocked.Increment(ref _totalDispatched);
                            }
                            catch (Exception ex)
                            {
                                _logger.LogError(ex, 
                                    "Event handler failed for {EventType} from {Source}", 
                                    @event.EventType, @event.Source);
                            }
                        });
                    }
                    catch (Exception ex)
                    {
                        _logger.LogError(ex, "Failed to dispatch event {EventType}", eventType.Name);
                    }
                }
            }
        }
    }
    
    public void Dispose()
    {
        _cts.Cancel();
        _channel.Writer.Complete();
        _dispatchTask.Wait(TimeSpan.FromSeconds(5));
        _cts.Dispose();
    }
}
```

**Key features:**
- ✅ Bounded queue (10k events) with drop-oldest policy
- ✅ Fire-and-forget dispatch (slow subscriber never blocks others)
- ✅ Replay buffer (last 30s for reconnect/diagnostics)
- ✅ Metrics (published, dropped, dispatched counters)
- ✅ Exception isolation (handler failure doesn't crash bus)

---

### 18.7 Migration Path — OPC + PLC Workers

**BEFORE (Sprint 1-3):**
```csharp
// PlcWorker.cs (current direct coupling)
var readResult = await _driver.ReadTagsAsync(tagsDue);

if (readResult.Success && readResult.Values.Count > 0)
{
    // Direct calls to multiple systems
    _pool.Update(readResult.Values, readResult.ReadDurationMs);
    _sharedPool?.UpdateFromPlc(PlcId, cacheEntries, DateTime.UtcNow);
    _sampleBuffer?.AddSamples(samples);
    
    _lastSuccessTime = DateTime.UtcNow;
    _successfulPolls++;
}
```

**AFTER (Sprint 4 — with event bus):**
```csharp
// PlcWorker.cs (decoupled via events)
var readResult = await _driver.ReadTagsAsync(tagsDue);

if (readResult.Success && readResult.Values.Count > 0)
{
    // Single event publish — all downstream systems are subscribers
    await _eventBus.PublishAsync(new TagValueUpdatedEvent
    {
        EventId = Guid.NewGuid(),
        EventType = "TagValueUpdated",
        TimestampUtc = DateTime.UtcNow,
        Source = $"PLC_{PlcId}",
        CorrelationId = _scanCorrelationId,
        Severity = EventSeverity.Normal,
        TagId = /* ... */,
        Value = /* ... */,
        Quality = /* ... */,
        SequenceId = _scanSequenceId++
    });
    
    // Scan cycle event for diagnostics
    await _eventBus.PublishAsync(new ScanCycleCompletedEvent
    {
        Source = $"PLC_{PlcId}",
        TagCount = readResult.Values.Count,
        DurationMs = readResult.ReadDurationMs,
        Success = true,
        SequenceId = _scanSequenceId
    });
    
    _lastSuccessTime = DateTime.UtcNow;
    _successfulPolls++;
}
```

**Same pattern applies to `OpcServerConnection.cs` — OPC and PLC unified.**

---

### 18.8 Subscriber Examples

**MQTT Subscriber (replaces `PlcMqttPublisherService`):**
```csharp
public class MqttEventSubscriber : BackgroundService
{
    private readonly IIndustrialEventBus _eventBus;
    private readonly MqttPublisher _mqttPublisher;
    
    protected override Task ExecuteAsync(CancellationToken ct)
    {
        // Subscribe to tag value events from ANY source (OPC or PLC)
        _eventBus.Subscribe<TagValueUpdatedEvent>(async @event =>
        {
            // Publish to MQTT topic based on source
            var topic = @event.Source.StartsWith("OPC") 
                ? $"opc/{@event.Source}/tags/bulk"
                : $"{@event.Source}/tags/bulk";
            
            await _mqttPublisher.PublishAsync(topic, @event);
        });
        
        return Task.CompletedTask;
    }
}
```

**Historian Subscriber (replaces `PlcHistorianIngestService`):**
```csharp
public class HistorianEventSubscriber : BackgroundService
{
    private readonly IIndustrialEventBus _eventBus;
    private readonly IHistorianWriter _historian;
    
    protected override Task ExecuteAsync(CancellationToken ct)
    {
        // Subscribe to tag value events from ANY source
        _eventBus.Subscribe<TagValueUpdatedEvent>(async @event =>
        {
            // Write to historian (same logic for OPC and PLC)
            await _historian.WriteAsync(new HistorianSample
            {
                TagId = @event.TagId,
                Value = @event.Value,
                Quality = @event.Quality,
                Timestamp = @event.Timestamp,
                Source = @event.Source
            });
        });
        
        return Task.CompletedTask;
    }
}
```

**Future: Alarm Subscriber (Sprint 5):**
```csharp
public class AlarmEventSubscriber : BackgroundService
{
    protected override Task ExecuteAsync(CancellationToken ct)
    {
        _eventBus.Subscribe<TagValueUpdatedEvent>(async @event =>
        {
            // Evaluate alarm conditions
            if (@event.Value is double numValue && numValue > alarmThreshold)
            {
                await _alarmEngine.TripAlarmAsync(@event.TagId, numValue);
            }
        });
        
        return Task.CompletedTask;
    }
}
```

---

### 18.9 Event Priority & Backpressure

**Priority levels:**
```csharp
public enum EventPriority
{
    Critical = 0,    // Alarms, safety trips
    High = 1,        // PLC state changes
    Normal = 2,      // Tag value updates
    Low = 3          // Diagnostics, metrics
}
```

**Drop policy when queue full:**
1. Drop Low priority first
2. Then Normal (but coalesce — keep latest value per tag)
3. High and Critical never dropped (block publisher if needed)

**Implementation:**
```csharp
if (_channel.Writer.TryWrite(@event) == false)
{
    // Queue full — apply priority-based drop policy
    if (@event.Priority == EventPriority.Low)
    {
        _totalDropped++;
        return;  // Drop immediately
    }
    
    if (@event.Priority == EventPriority.Normal)
    {
        // Coalesce: if same tag already queued, drop old, keep new
        CoalesceAndRetry(@event);
    }
    
    // Critical/High: wait (blocks producer briefly)
    await _channel.Writer.WriteAsync(@event);
}
```

---

### 18.10 What Does NOT Change (Important)

**Keep unchanged:**
- ✅ Historian semantic layer (`historian_meta` schema)
- ✅ Taxonomy model (asset hierarchy, plant/area/unit)
- ✅ RBAC (user permissions, role-based filtering)
- ✅ PLC worker isolation (one worker per PLC)
- ✅ OPC/PLC separation (still separate acquisition engines)
- ✅ MQTT broker (still primary transport to Python/browser)
- ✅ REST fallback strategy (still needed when MQTT dies)

**Event bus ENHANCES these, doesn't replace them.**

---

### 18.11 Diagnostics & Observability

**New endpoint: `GET /api/events/diagnostics`**

```json
{
  "queueDepth": 127,
  "maxQueueDepth": 10000,
  "totalPublished": 1847293,
  "totalDropped": 42,
  "totalDispatched": 1847251,
  "replayBufferSize": 3421,
  "subscribers": {
    "TagValueUpdatedEvent": 4,
    "ScanCycleCompletedEvent": 2,
    "AcquisitionConnectedEvent": 3
  },
  "lastDropTime": "2026-05-26T08:41:23.456Z",
  "avgDispatchLatencyMs": 2.3
}
```

---

### 18.12 Migration Strategy (Incremental)

**Phase 1 (Sprint 4.1): Infrastructure**
- Add event bus implementation
- Add core event types
- Register as singleton in DI container
- Add diagnostics endpoint

**Phase 2 (Sprint 4.2): First Subscribers**
- Migrate MQTT publisher → MqttEventSubscriber
- Migrate Historian → HistorianEventSubscriber
- PLC workers publish events (OPC still direct for now)

**Phase 3 (Sprint 4.3): Complete Migration**
- OPC workers publish events
- Remove direct coupling in `OpcServerConnection.cs`
- Verify OPC + PLC both work through event bus

**Phase 4 (Sprint 5+): New Subscribers**
- Add alarm engine subscriber
- Add AI/ML analytics subscriber
- Add OEE calculation subscriber
- Add audit trail subscriber

**Rule: Never break existing functionality. Migrate incrementally.**

---

### 18.13 What NOT to Do (Critical)

**❌ Do NOT over-engineer:**
- No Kafka (not needed initially)
- No RabbitMQ (in-process is enough)
- No Redis Streams (adds complexity)
- No distributed event sourcing (overkill)
- No CQRS (not needed)
- No event store (replay buffer is enough)

**❌ Do NOT mix concerns:**
- Event bus has NO business logic
- Event bus has NO analytics
- Event bus has NO AI
- Event bus is ONLY transport + dispatch

**❌ Do NOT make events chatty:**
- No event per tag per scan (bundle in TagValueUpdatedEvent)
- No debug events in production
- No trace events flooding the bus

**✅ DO keep it simple:**
- In-process Channel<T> is perfect
- Bounded queue with drop policy
- Fire-and-forget dispatch
- Replay buffer for diagnostics only

---

### 18.14 Success Criteria (Sprint 4 Complete)

**Functional:**
- [ ] Event bus handles 10,000 events/sec without drops
- [ ] MQTT publisher receives events from both OPC and PLC
- [ ] Historian writer receives events from both OPC and PLC
- [ ] New subscriber can be added without modifying workers
- [ ] Replay buffer allows last 30s event inspection

**Performance:**
- [ ] Event publish latency <1ms (p99)
- [ ] Dispatch latency <5ms (p99)
- [ ] Zero memory leaks after 24h soak test
- [ ] Queue depth stays <1000 under normal load

**Observability:**
- [ ] `/api/events/diagnostics` shows real-time metrics
- [ ] Dropped events logged with reason
- [ ] Correlation IDs trace events end-to-end
- [ ] Slow subscriber detected and logged

---

### 18.15 Long-Term Vision (Sprint 5+)

**With event bus foundation, future becomes:**

```
Event Producers:
  - OPC DA workers
  - PLC workers (Rockwell, Siemens, Modbus, etc.)
  - BACnet gateway (future)
  - SNMP collectors (future)
  - REST API writes (future)

Event Subscribers:
  - MQTT publisher → Python HMI
  - Historian writer → PostgreSQL
  - Alarm engine → alarm state machine
  - AI/ML pipeline → predictive models
  - OEE calculator → production metrics
  - Audit logger → compliance trail
  - Quality monitor → SPC charts
  - Anomaly detector → maintenance alerts
  - Dashboard aggregator → real-time KPIs
```

**All without modifying core acquisition code. That's the power.**

---

### 18.16 Implementation Checklist

**Sprint 4.1 — Infrastructure (Week 1)**
- [ ] Create `Events/` folder with interfaces
- [ ] Implement `IndustrialEventBus.cs`
- [ ] Add event types: `TagValueUpdatedEvent`, `ScanCycleCompletedEvent`, connection events
- [ ] Register as singleton in `Program.cs`
- [ ] Add `/api/events/diagnostics` endpoint
- [ ] Unit tests for bounded queue + drop policy

**Sprint 4.2 — First Migration (Week 2)**
- [ ] Create `MqttEventSubscriber.cs`
- [ ] Create `HistorianEventSubscriber.cs`
- [ ] Modify `PlcWorker.cs` to publish events
- [ ] Test PLC path: worker → event bus → MQTT + Historian
- [ ] Verify no regressions in PLC data flow

**Sprint 4.3 — OPC Migration (Week 3)**
- [ ] Modify `OpcServerConnection.cs` to publish events
- [ ] Test OPC path: worker → event bus → MQTT + Historian
- [ ] Remove direct coupling code
- [ ] Verify OPC and PLC both work identically
- [ ] 24h soak test

**Sprint 4.4 — Observability (Week 4)**
- [ ] Add correlation IDs to all events
- [ ] Add event replay API for diagnostics
- [ ] Add slow subscriber detection
- [ ] Dashboard showing event bus metrics
- [ ] Documentation + operator training

---

### 18.17 Expert Final Word on Event Bus

**Why this matters for YOUR vision:**

You explicitly want:
- AI/ML integration
- Predictive maintenance
- OEE calculation
- Modular analytics

**Without event bus:** Each addition requires surgery on core workers → coupling explosion → technical debt accumulates → platform becomes unmaintainable

**With event bus:** Each addition = new subscriber → zero worker changes → platform stays clean → AI/analytics teams work independently

**This is the difference between:**
- A custom SCADA system (hard to extend)
- An industrial data platform (built for evolution)

**Your architecture is already 90% there. Event bus is the final 10% that enables platform thinking.**

---

## 19. Updated Sprint Roadmap (Complete Architecture Evolution)

| Sprint | Main Goal | Key Deliverables | Why This Order |
|--------|-----------|------------------|----------------|
| **Sprint 1** | **Operational correctness** | IP mapping fix, state machine, hard timeout, REST fallback, watchdog, credentials removal, `consecutiveFailures` fix | **System must work first** |
| **Sprint 2** | **Stability + diagnostics** | Scan budget, MQTT backpressure, config validation, cold start jitter, `/api/plc/diagnostics`, historian isolation metrics | **System must be stable** |
| **Sprint 3** | **Global supervisor + observability** | `IndustrialSystemSupervisorService`, event journal, per-source liveness, correlation IDs, overload detection, degraded mode | **System must be observable** |
| **Sprint 4** | **Event bus architecture** | Lightweight event bus, migrate OPC + PLC to event producers, MQTT + Historian to subscribers, replay buffer, diagnostics | **System must be extensible** |
| **Sprint 5+** | **Alarm/AI/analytics** | Alarm engine subscriber, AI/ML pipeline subscriber, OEE calculator, predictive maintenance, anomaly detection | **System becomes intelligent** |

**This sequence ensures:** Operational → Stable → Observable → Extensible → Intelligent

**Nothing is done prematurely. Everything builds on the previous foundation.**

---

## 11. Database Cleanup Log & FK Restoration Notes

> **CRITICAL:** When PLC tags are re-inserted into `historian_meta.tag_master`, the FK and dependent data listed below must be re-created. Do NOT skip this.

### Cleanup performed: 2026-05-26

#### What was deleted

| Table | Rows deleted | Reason |
|-------|-------------|--------|
| `historian_raw.trip_event_tracking` | 3375 | FK reference to deleted tags — trip/alarm event history for `Rockwel_PLC_001` tags |
| `historian_meta.tag_master` (plant=`Plant1`) | 9 | Fake/test rows — no real PLC tags |
| `historian_meta.tag_master` (plant=`PLANT_001`) | 32 | Fake/test rows with wrong plant assignment |

#### Why deleted
- All 41 rows under `server_progid = 'Rockwel_PLC_001'` with `plant IN ('PLANT_001', 'Plant1')` were test/fake data inserted during development.
- They had wrong plant assignment (`PLANT_001` / `Plant1` instead of correct plant `FTP-1`).
- They were blocking clean DB config loading at runtime.

#### FK constraint that was broken
- **Constraint name:** `fk_trip_tag`
- **On table:** `historian_raw.trip_event_tracking`
- **FK column:** `trip_tag_id` → references `historian_meta.tag_master(tag_id)`
- **Cascade behaviour:** No cascade — must manually delete child rows before parent

#### What must be done when real PLC tags are inserted
When the physical PLC is connected and real tags are inserted into `historian_meta.tag_master`:

1. Insert correct tags with `plant = 'FTP-1'` (the verified plant value from DB screenshot), `server_progid = 'Rockwel_PLC_001'`, `enabled = true`, correct `plc_ip_address = '192.168.0.20'`
2. The FK constraint `fk_trip_tag` will automatically apply to new rows — no action needed to re-create it (it is a constraint on `trip_event_tracking`, not dropped)
3. The 3375 trip event rows that were deleted were historical test data — they do not need to be restored
4. Verify after insert: `SELECT COUNT(*) FROM historian_meta.tag_master WHERE server_progid = 'Rockwel_PLC_001' AND enabled = true;` — should return tag count > 0
| `HMI/apex-hmi/src/hooks/useOpcPlcStatus.ts` | React hook — 10s poll for PLC banner |
| `HMI/apex-hmi/src/components/hmi/IndustrialHMIPrototype.tsx` | Banner: ⚠ PLC X: NOT CONNECTED |
