# HMI Integration Guide — OPC/PLC Central Module ↔ apex-hmi via EMQX

**Date:** May 7, 2026  
**Broker:** EMQX (chosen to replace raw TCP custom publisher)  
**Status:** Phase 1 partially complete — Phase 1 gap documented — Phase 2 defined

---

## Table of Contents
1. [System Overview](#1-system-overview)
2. [Correct Data Flow — As It Should Be](#2-correct-data-flow--as-it-should-be)
3. [Phase 1 — Server Side (OPC + Reliability)](#3-phase-1--server-side-opc--reliability)
4. [Phase 2 — HMI Linking via EMQX](#4-phase-2--hmi-linking-via-emqx)
5. [EMQX Broker Setup](#5-emqx-broker-setup)
6. [Auth, RBAC & Reports (Unchanged)](#6-auth-rbac--reports-unchanged)
7. [Startup Order](#7-startup-order)
8. [Risk Register](#8-risk-register)

---

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│  SOURCE LAYER                                                           │
│  OPC DA Server (Matrikon.OPC.Simulation.1)                             │
│  PLC Devices (Rockwell / Siemens / Modbus / Omron / ABB / Mitsubishi)  │
└────────────────────────────┬────────────────────────────────────────────┘
                             │ OPC DA / Driver protocol
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  CENTRAL MODULE  (C# ASP.NET Core — Port 5001, x86)                    │
│                                                                         │
│  OpcServerConnection (1000ms poll)                                      │
│       ↓                                                                 │
│  DataLoggingService                                                     │
│       ↓ UpdatePool()                                                    │
│  TagValuesPoolService  ← single source of truth for ALL tag values     │
│       │                                                                 │
│       ├─ HistorianIngestHostedService → PostgreSQL TimescaleDB          │
│       ├─ Parquet logging (SelectedTags only)                            │
│       ├─ GET /api/opc/values (REST polling fallback)                    │
│       └─ [PHASE 1 GAP] → MqttPublisher → EMQX  ❌ NOT YET WIRED        │
│                                                                         │
│  PlcGatewayHostedService                                                │
│       └─ MqttPublisher → EMQX → plc/+/bulk  ✅ ALREADY WORKING         │
└─────────────────────────────────────────────────────────────────────────┘
                             │ EMQX broker
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  HMI BACKEND  (Python Flask — Port 6001)                               │
│                                                                         │
│  MQTTClientService (paho-mqtt)                                          │
│       ↓ subscribes: plc/+/bulk, opc/tags/bulk [PHASE 2]               │
│  LiveDataBuffer (last-value per tag)                                    │
│       ↓                                                                 │
│  SocketIO → emit mqtt_tag_update                                        │
│                                                                         │
│  SignalRListener → /opcHub  [TO BE DISABLED in Phase 2]                │
│  REST blueprints → auth / alarms / reports / RBAC                      │
└─────────────────────────────────────────────────────────────────────────┘
                             │ SocketIO + REST
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  FRONTEND  (React 18 + Vite — apex-hmi, built static)                  │
│                                                                         │
│  mqtt-websocket.ts  → socket.io-client → Flask :6001                  │
│       listens: mqtt_tag_update, mqtt_alarm, tag_update                 │
│  api.ts             → axios → Flask :6001/api (all REST)               │
│  auth-context.tsx   → JWT + session token (30s heartbeat)              │
│  reportApi.ts       → daily / shift / monthly reports                  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Correct Data Flow — As It Should Be

### OPC Tag Live Data (Target state — after both phases complete)

```
OPC Server
    ↓ 1000ms poll
OpcServerConnection.GetCachedValues()
    ↓
DataLoggingService.LogData()
    ↓
TagValuesPoolService.UpdatePool(allValues, timestamp, deadbandMap?)
    │
    │  [POOL ENTRY — what is stored per tag]
    │  TagId, Value, Quality, Timestamp
    │  SequenceId    — monotonic per-tag, persists across restarts
    │  IsChanged     — deadband applied here (one place, shared by all consumers)
    │  IsStale       — set when OPC disconnects (pool is never wiped)
    │  PreviousValue — shadow copy for WAL reads
    │
    ├──→ HistorianIngestHostedService
    │       reads GetTagValues(mappedTagIds)
    │       → RateControllerService (deadband / interval check)
    │       → DbWriterService (circuit breaker + spool fallback)
    │       → PostgreSQL historian_raw.historian_timeseries
    │
    ├──→ DataLoggingService (Parquet write path — separate counter)
    │       writes only SelectedTags every parquetIntervalMs (5000ms default)
    │       → rotating 10MB files in D:\OpcLogs\Data
    │
    ├──→ REST: GET /api/opc/values
    │       reads GetAllTagValues()
    │       → HMI polls this as fallback if MQTT unavailable
    │
    └──→ [PHASE 1 GAP — items 13-17] MqttPublisher.PublishOpcBulkAsync()
                every poll cycle (1000ms), fire-and-forget
                topic: opc/tags/bulk
                    ↓
                EMQX Broker (TCP 1883)
                    ↓
                Flask MQTTClientService subscribes opc/tags/bulk
                    ↓
                LiveDataBuffer.update_batch(tags)
                    ↓
                SocketIO.emit("mqtt_tag_update", { source:"opc", tags:[...] })
                    ↓
                apex-hmi mqtt-websocket.ts receives event
                    ↓
                React state updates → HMI live display
```

### PLC Tag Live Data (Already Working — no changes needed)

```
PLC Drivers (Rockwell / Siemens / Modbus / Omron / ABB / Mitsubishi)
    ↓
PlcGatewayHostedService
    ↓
MultiProtocolPublisherService
    ↓
MqttPublisher.PublishAsync()   [exponential backoff ✅ fixed May 2026]
    topics: plc/{plcId}/bulk, plc/all, plc/health
    ↓
EMQX Broker
    ↓
Flask MQTTClientService (already subscribes plc/+/bulk)
    ↓
LiveDataBuffer → SocketIO → apex-hmi     ✅ WORKING TODAY
```

### Database Write Decision (per tag, every cycle)

```
TagValuesPoolService → GetTagValues(mappedTagIds)
    ↓
RateControllerService.ProcessSample(tagId, value, timestamp)
    │
    ├── First sample ever?                → WRITE
    ├── Interval elapsed + deadband > 0  → WRITE if |current − last| > deadband
    ├── Interval elapsed + deadband = 0  → WRITE if current ≠ last
    └── Spike (deadband exceeded before interval) → WRITE immediately
    
    Otherwise → FILTER (skip DB write this cycle)
    ↓
DbWriterService.WriteBatchAsync()
    circuit open?  → SpoolManagerService.SpoolAsync() (disk WAL fallback)
    circuit closed → PostgreSQL COPY (bulk insert, binary mode)
    ↓
    ON FAILURE:
        consecutive failures ≥ 5 → circuit OPEN
        PersistCircuitBreakerState() → circuit_breaker_state.json
        (CB state survives restart — DB not hammered on startup after a crash)
```

---

## 3. Phase 1 — Server Side (OPC + Reliability)

### 3.1 What Is ALREADY Done ✅ (Implemented May 2026, all files compile clean)

#### `Services/TagValuesPoolService.cs`

| Feature | Detail |
|---------|--------|
| **SequenceId** | Monotonic per-tag counter. Incremented on every `UpdatePool()` call. Persisted to `seq_state.json` every 30s. Restarts do not reset IDs — prevents replay duplicates. |
| **IsChanged** | Deadband evaluation happens here once. All consumers (historian, WAL, MQTT) see the same change flag. No duplicated deadband logic. |
| **IsStale** | Set on all entries when OPC disconnects. Pool is NEVER cleared — `MarkAllStale()` replaces `ClearPool()`. Last-known values survive with `IsStale=true`. HMI can show "last known" instead of blank. |
| **PreviousValue** | Shadow copy of last value kept per entry. WAL reads pool snapshot directly — no dependency on DB queue overflow to detect changes. |
| **PoolUpdated event** | Fired after every `UpdatePool()`. Consumers wire to this event instead of polling independently. |
| **GetPoolSnapshot()** | Returns full pool snapshot for WAL writer. |
| **GetChangedValues()** | Returns only `IsChanged=true` entries. DB writer uses this. |
| **ClearPool() obsolete** | Annotated `[Obsolete]`. Now redirects to `MarkAllStale()` — call sites compile, behaviour is safe. |

#### `Services/HistorianIngest/Services/DbWriterService.cs`

| Feature | Detail |
|---------|--------|
| **CB state persisted** | `PersistCircuitBreakerState()` called on OPEN and CLOSE transitions. Writes to `circuit_breaker_state.json`. |
| **Restart protection** | `LoadCircuitBreakerState()` in constructor. If CB was OPEN at last shutdown and the 2-minute cooldown has not expired, CB stays OPEN on startup. DB is not hammered after a failure restart. |

#### `Services/PlcGateway/Transport/MqttPublisher.cs`

| Feature | Detail |
|---------|--------|
| **Exponential backoff** | `_backoffMs` starts at 500ms, doubles on each failure, caps at 30,000ms. |
| **Retry guard** | `_nextRetryTime` checked before every `ConnectAsync()`. Tight reconnect loop eliminated. |
| **Backoff reset** | `_backoffMs = 500` resets on successful connection. |

#### `Services/HistorianIngest/Services/SpoolManagerService.cs`

| Feature | Detail |
|---------|--------|
| **Replay throttle** | 50ms `Task.Delay` between each replayed spool file. Prevents burst flooding the DB on recovery. |
| **Row-by-row recovery** | On deserialization failure, `TryRowByRowRecoveryAsync()` reads the file line-by-line and creates a partial recovery batch from valid rows before moving the file to `.error`. |

#### `Services/DataLoggingService.cs`

| Feature | Detail |
|---------|--------|
| **Crash watchdog upgraded** | The main loop `catch` block now: `LogCritical` + `_tagPool.MarkAllStale()` + `_healthService.UpdateOpcHealth(CRITICAL)`. Operators see an immediate health alert instead of a silent `LogError`. |
| **IHealthStatusService injected** | Constructor now takes `IHealthStatusService healthService`. |

---

### 3.2 Phase 1 GAP — What Is NOT Yet Done ❌

> **This is the critical missing link.** OPC tag values currently reach `TagValuesPoolService` correctly but are NOT published to EMQX. The MQTT path only covers PLC data today. Without this, Phase 2 cannot deliver live OPC data to the HMI.

**Root cause:** `MqttPublisher` lives in the `PlcGateway` namespace and only has methods for PLC payloads (`PublishAsync`, `PublishWithSamplesAsync`, `PublishHealthAsync`). There is no `PublishOpcBulkAsync` method. `DataLoggingService` has no reference to any MQTT publisher at all.

#### Required Change 1 — Add `PublishOpcBulkAsync` to `MqttPublisher.cs`

```csharp
/// <summary>
/// Publish OPC DA tag values from TagValuesPoolService to EMQX.
/// Topic: opc/tags/bulk
/// Called every OPC poll cycle (1000ms) by DataLoggingService — fire-and-forget.
/// DO NOT retain — stale OPC values on broker are dangerous for operators.
/// </summary>
public async Task<bool> PublishOpcBulkAsync(
    IReadOnlyList<TagValueCacheEntry> tagValues,
    DateTime batchTimestamp,
    CancellationToken ct = default)
{
    if (!IsConnected)
    {
        if (!await ConnectAsync(ct)) return false;
    }

    await _publishLock.WaitAsync(ct);
    try
    {
        var payload = new
        {
            timestamp  = batchTimestamp,
            source     = "opc_da",
            tagCount   = tagValues.Count,
            values     = tagValues.Select(v => new
            {
                tagId      = v.TagId,
                value      = v.Value,
                quality    = v.Quality,
                timestamp  = v.Timestamp,
                sequenceId = v.SequenceId,
                isChanged  = v.IsChanged,
                isStale    = v.IsStale
            })
        };

        var json  = JsonSerializer.Serialize(payload, _jsonOptions);
        var topic = BuildTopic("opc/tags/bulk");

        // retain: false — never retain live value messages on broker
        return await PublishToTopicAsync(topic, json, ct, retain: false);
    }
    catch (Exception ex)
    {
        _logger.LogError(ex, "[MQTT PUB] OPC bulk publish failed");
        _isConnected = false;
        return false;
    }
    finally
    {
        _publishLock.Release();
    }
}
```

#### Required Change 2 — Inject `MqttPublisher` into `DataLoggingService.cs`

```csharp
private readonly MqttPublisher? _mqttPublisher; // nullable — broker down must not crash OPC loop

public DataLoggingService(
    LoggingConfigService configService,
    MappingCacheService mappingCache,
    TagValuesPoolService tagPool,
    ILogger<DataLoggingService> logger,
    ILoggerFactory loggerFactory,
    IConfiguration configuration,
    IHealthStatusService healthService,
    MqttPublisher? mqttPublisher = null)      // ← add this parameter
{
    _mqttPublisher = mqttPublisher;
    // ... rest of existing constructor
}
```

#### Required Change 3 — Call publish after `UpdatePool()` inside `LogData()`

In `DataLoggingService.cs`, immediately after `_tagPool.UpdatePool(allValues, batchTimestamp)`:

```csharp
// Fire-and-forget MQTT publish — broker latency MUST NOT delay OPC poll loop
if (_mqttPublisher is not null)
{
    var snapshot = _tagPool.GetAllTagValues();
    _ = _mqttPublisher.PublishOpcBulkAsync(snapshot, batchTimestamp, stoppingToken)
        .ContinueWith(t =>
        {
            if (t.IsFaulted)
                _logger.LogWarning("[MQTT] OPC bulk publish threw: {Err}",
                    t.Exception?.GetBaseException().Message);
        }, TaskContinuationOptions.OnlyOnFaulted);
}
```

> **Critical rule:** Never `await` MQTT inside the OPC polling loop. If the broker is slow or down, the pool must continue updating at full speed.

#### Required Change 4 — Register `MqttPublisher` in `Program.cs`

```csharp
// Register as singleton so DataLoggingService and PlcGateway share the same publisher instance
builder.Services.AddSingleton<MqttPublisher>(provider =>
{
    var config = provider.GetRequiredService<MqttTransportConfig>();
    var logger = provider.GetRequiredService<ILogger<MqttPublisher>>();
    return new MqttPublisher(config, logger);
});
```

#### Required Change 5 — Add EMQX section to `appsettings.json`

```json
"MqttTransport": {
  "BrokerHost":        "127.0.0.1",
  "BrokerPort":        1883,
  "ClientId":          "cereveate_central_opc",
  "Username":          "cereveate_opc",
  "Password":          "CHANGE_ME",
  "TopicPrefix":       "",
  "QualityOfService":  1,
  "KeepAliveSeconds":  60,
  "RetainMessages":    false,
  "PublishMode":       "Bulk"
}
```

---

### 3.3 Phase 1 — Master Checklist

| # | Item | File | Status |
|---|------|------|--------|
| 1 | SequenceId per-tag (persisted to seq_state.json) | TagValuesPoolService.cs | ✅ Done |
| 2 | IsChanged at pool level (deadband in one place) | TagValuesPoolService.cs | ✅ Done |
| 3 | IsStale + MarkAllStale() replaces ClearPool() | TagValuesPoolService.cs | ✅ Done |
| 4 | PreviousValue shadow copy per entry | TagValuesPoolService.cs | ✅ Done |
| 5 | PoolUpdated event for consumers | TagValuesPoolService.cs | ✅ Done |
| 6 | GetPoolSnapshot() / GetChangedValues() | TagValuesPoolService.cs | ✅ Done |
| 7 | Circuit breaker state persisted to disk | DbWriterService.cs | ✅ Done |
| 8 | CB restart protection (cooldown survives restart) | DbWriterService.cs | ✅ Done |
| 9 | MQTT backoff 500ms → 30s with retry guard | MqttPublisher.cs | ✅ Done |
| 10 | Spool replay throttle 50ms between files | SpoolManagerService.cs | ✅ Done |
| 11 | Spool row-by-row recovery on corrupt file | SpoolManagerService.cs | ✅ Done |
| 12 | Crash watchdog → MarkAllStale + health CRITICAL | DataLoggingService.cs | ✅ Done |
| **13** | **PublishOpcBulkAsync() added to MqttPublisher** | **MqttPublisher.cs** | **❌ TODO** |
| **14** | **MqttPublisher injected into DataLoggingService** | **DataLoggingService.cs** | **❌ TODO** |
| **15** | **Fire-and-forget publish called after UpdatePool()** | **DataLoggingService.cs** | **❌ TODO** |
| **16** | **MqttPublisher registered as singleton in DI** | **Program.cs** | **❌ TODO** |
| **17** | **MqttTransport section added to appsettings.json** | **appsettings.json** | **❌ TODO** |

> **Items 13–17 are Phase 1 completion requirements. Phase 2 cannot start until these are done.**

---

## 4. Phase 2 — HMI Linking via EMQX

> **Prerequisite:** Phase 1 items 13–17 complete. EMQX broker running. Verify `opc/tags/bulk` messages visible in EMQX dashboard before proceeding.

### 4.1 Flask Backend — `config.json`

**Current state:**
```json
"mqtt": {
  "broker_host": "127.0.0.1",
  "broker_port": 1883,
  "client_id":   "hmi_backend"
}
```

**Target state:**
```json
"mqtt": {
  "broker_host": "127.0.0.1",
  "broker_port": 1883,
  "username":    "cereveate_hmi",
  "password":    "CHANGE_ME",
  "client_id":   "hmi_backend",
  "subscribe_topics": [
    "opc/tags/bulk",
    "plc/+/bulk",
    "alarms/active",
    "alarms/events"
  ]
},
"signalr": {
  "enabled":  false,
  "host":     "127.0.0.1",
  "port":     5001,
  "hub_path": "/opcHub"
}
```

> Add `signalr.enabled: false` — MQTT is now the live data path. Keep the file, just gate it.

### 4.2 Flask Backend — `services/mqtt_client_service.py`

Add `opc/tags/bulk` topic handler:

```python
# Read topics from config (with sensible default)
SUBSCRIBE_TOPICS = config.get("mqtt", {}).get("subscribe_topics", [
    "plc/+/bulk",
    "opc/tags/bulk"
])

def on_message(self, client, userdata, msg):
    topic = msg.topic
    try:
        payload = json.loads(msg.payload.decode())
    except Exception:
        return

    if topic == "opc/tags/bulk":
        # OPC DA values from C# TagValuesPoolService
        for tag in payload.get("values", []):
            self._live_buffer.update(
                tag_id    = tag["tagId"],
                value     = tag["value"],
                quality   = tag["quality"],
                timestamp = tag["timestamp"],
                is_stale  = tag.get("isStale", False)
            )
        socketio.emit("mqtt_tag_update", {
            "source": "opc",
            "tags":   payload.get("values", [])
        })

    elif topic.startswith("plc/") and topic.endswith("/bulk"):
        # PLC values — existing handler, no change needed
        ...
```

### 4.3 Flask Backend — `services/signalr_listener.py`

Gate with config flag (do NOT delete the file):

```python
def start(self):
    if not config.get("signalr", {}).get("enabled", True):
        logger.info(
            "SignalRListener disabled in config — MQTT via EMQX is the live data source"
        )
        return
    # ... existing connection code unchanged
```

### 4.4 Frontend (apex-hmi) — NO CHANGES REQUIRED

| File | Status | Reason |
|------|--------|--------|
| `services/mqtt-websocket.ts` | ✅ No change | Already listens to `mqtt_tag_update` / `mqtt_alarm` / `tag_update` via socket.io-client |
| `services/api.ts` | ✅ No change | All REST calls stay on Flask :6001 |
| `context/auth-context.tsx` | ✅ No change | JWT + MFA + session heartbeat unchanged |
| `services/reportApi.ts` | ✅ No change | Reports hit Flask → PostgreSQL |
| `App.tsx` routing | ✅ No change | No new routes needed |
| All report pages | ✅ No change | Data source unchanged |

### 4.5 Topic Structure After Phase 2

| Topic | Publisher | Subscriber | Rate | Notes |
|-------|-----------|------------|------|-------|
| `opc/tags/bulk` | C# DataLoggingService | Flask MQTTClientService | 1000ms | ALL OPC DA tags |
| `opc/tags/{tagId}` | Optional | Optional | — | Not needed unless per-tag subscription required |
| `plc/all` | C# PlcGateway | Flask | On change | All PLC tags bulk |
| `plc/{plcId}/bulk` | C# PlcGateway | Flask | On change | Per-PLC tags |
| `plc/health` | C# HealthPublisher | Flask | 3s | PLC health metrics |
| `alarms/active` | C# AlarmService (future) | Flask | On change | Current alarm list |
| `alarms/events` | C# AlarmService (future) | Flask | On event | New alarm stream |

### 4.6 Phase 2 — Checklist

| # | Item | File | Status |
|---|------|------|--------|
| 1 | EMQX broker deployed and reachable | — | ❌ |
| 2 | EMQX ACL rules configured (see Section 5) | EMQX dashboard | ❌ |
| 3 | Phase 1 items 13–17 complete and verified | C# side | ❌ |
| 4 | EMQX credentials added to Flask config.json | config.json | ❌ |
| 5 | `opc/tags/bulk` added to subscribe_topics | config.json | ❌ |
| 6 | `opc/tags/bulk` handler added to mqtt_client_service.py | mqtt_client_service.py | ❌ |
| 7 | SignalRListener gated with config flag | signalr_listener.py | ❌ |
| 8 | Verify `mqtt_tag_update` events arrive in browser devtools | HMI browser | ❌ |
| 9 | Verify OPC tag values show on HMI live display | HMI UI | ❌ |
| 10 | Set `signalr.enabled: false` in production config | config.json | ❌ |

---

## 5. EMQX Broker Setup

### Quick Deploy — Docker (Windows)

```bat
docker run -d --name emqx ^
  -p 1883:1883 ^
  -p 8083:8083 ^
  -p 18083:18083 ^
  emqx/emqx:latest
```

| Port | Protocol | Used by |
|------|----------|---------|
| 1883 | MQTT TCP | C# MqttPublisher, Flask paho-mqtt |
| 8083 | MQTT WebSocket | Future: apex-hmi direct subscription |
| 18083 | HTTP Dashboard | Admin configuration |

Dashboard: `http://localhost:18083`  
Default credentials: `admin` / `public` — **change immediately**.

### Windows Service (Production)
Download installer from https://www.emqx.io/downloads → Windows.  
Install as Windows Service for auto-start.

### EMQX ACL Rules (Dashboard → Access Control → Authorization)

```
# C# Central Module — publish only
Username: cereveate_opc
  ALLOW  PUBLISH    opc/tags/#
  ALLOW  PUBLISH    plc/#
  ALLOW  PUBLISH    alarms/#
  DENY   ALL        *

# Flask HMI Backend — subscribe only
Username: cereveate_hmi
  ALLOW  SUBSCRIBE  opc/tags/#
  ALLOW  SUBSCRIBE  plc/#
  ALLOW  SUBSCRIBE  alarms/#
  DENY   ALL        *
```

---

## 6. Auth, RBAC & Reports (Unchanged)

These components work today and require zero changes in either phase.

### Authentication Flow
```
apex-hmi login form
    ↓ POST /api/auth/login (Flask auth_controller)
    IF mfaRequired:
        ↓ POST /api/auth/mfa/verify (TOTP or security question)
    ↓ returns { token: JWT, user: {...} }
    ↓ auth-context.tsx stores JWT in memory/localStorage
    ↓ api.ts injects:
        Authorization: Bearer {JWT}
        X-Session-Token: {sessionToken}
        on every request
    ↓ Flask validates JWT + session on every protected endpoint
    ↓ 30s heartbeat: POST /api/session/activity
    ↓ Admin force-logout → 401 sessionExpired → auto logout
```

### Roles
| Role | Access |
|------|--------|
| Admin | Full access + user management + force-logout any session |
| Supervisor | Alarm acknowledgement + all reports |
| Operator | Live HMI view + read-only |

### Reports Data Source
```
apex-hmi reportApi.ts
    → GET /api/reports/{daily|shift|monthly}?date=...&plant=...
    → Flask report_service.py
    → PostgreSQL historian_raw.historian_timeseries
       (aggregated by TimescaleDB continuous aggregates)
    → returns structured report data + XLSX export
```

> Reports depend on `historian_raw.historian_timeseries` being populated.  
> That requires `historian_meta.tag_master` to have enabled entries with valid `tag_id` values.

---

## 7. Startup Order (Production)

```
1. PostgreSQL / TimescaleDB          must be up before C# or Flask write anything
2. EMQX Broker                       must be up before C# publishes or Flask subscribes
3. C# Central Module  dotnet run     connects OPC, publishes opc/tags/bulk + plc/* to EMQX
4. Flask HMI Backend  python app.py  subscribes EMQX, serves REST + SocketIO on :6001
5. apex-hmi                          served by Flask (dev) or Nginx (prod) — connects to :6001
```

---

## 8. Risk Register

| Risk | Affected Component | Impact | Mitigation |
|------|--------------------|--------|-----------|
| Phase 1 items 13–17 not complete | OPC → HMI live data | No OPC data in HMI regardless of EMQX | Complete before any Phase 2 work — verify via EMQX dashboard |
| MQTT publish awaited in OPC loop | TagValuesPoolService freshness | Pool stops at broker speed, not OPC speed | Always fire-and-forget — never `await` MQTT in `LogData()` |
| EMQX broker down | All live data | No real-time HMI updates | Flask falls back: HMI polls REST `/api/opc/values` every 1s |
| SignalR + MQTT both active | LiveDataBuffer | Duplicate updates, possible race conditions | Disable SignalR via `signalr.enabled: false` once MQTT verified |
| EMQX auth misconfigured | C# publish path | C# cannot connect to broker | Test anonymous first, add credentials after smoke test passes |
| CB state file corrupted | DbWriterService startup | CB stuck open permanently | Delete `circuit_breaker_state.json` — CB resets to CLOSED on next startup |
| TagMaster table empty | Historian writes | No DB inserts despite pool being full | `HistorianIngestHostedService` logs critical warning "No enabled tag mappings" on startup |
| apex-hmi SocketIO disconnect | Live display | HMI freezes on last-known values | socket.io auto-reconnect configured (5 attempts, 1s delay between) |

---

## Appendix — Files Modified in Phase 1 (May 2026 Batch)

| File | Summary of Changes |
|------|--------------------|
| `Services/TagValuesPoolService.cs` | SequenceId + IsChanged + IsStale + MarkAllStale() + PreviousValue + PoolUpdated event + GetPoolSnapshot() + GetChangedValues() + seq_state.json persistence every 30s |
| `Services/HistorianIngest/Services/DbWriterService.cs` | Circuit breaker state written to `circuit_breaker_state.json` on OPEN/CLOSE. `LoadCircuitBreakerState()` in constructor keeps CB OPEN on restart if cooldown not expired |
| `Services/PlcGateway/Transport/MqttPublisher.cs` | Exponential backoff 500ms → 30s max with `_nextRetryTime` retry guard. Backoff resets to 500ms on successful connect |
| `Services/HistorianIngest/Services/SpoolManagerService.cs` | 50ms `Task.Delay` throttle between replayed spool files. `TryRowByRowRecoveryAsync()` recovers valid rows from corrupt files before moving to `.error` folder |
| `Services/DataLoggingService.cs` | Crash watchdog: `LogCritical` + `_tagPool.MarkAllStale()` + `_healthService.UpdateOpcHealth(CRITICAL)` on main loop exception. `IHealthStatusService` injected |
