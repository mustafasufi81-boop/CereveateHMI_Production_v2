# OPC DA + PLC Gateway — As-Built Data Flow
**Date:** 24 May 2026  
**Verified Against:** Actual source code (not docs only)  
**Status:** PRODUCTION — reflects what is ACTUALLY running

---

## 1. OPC DA — AS-BUILT DATA FLOW

### 1.1 Top-Level Picture

```
OPC DA Server (e.g. Matrikon.OPC.Simulation.1)
    │   COM/DCOM — Windows x86 only
    ▼
OpcServerConnection.cs  [polls every OpcPollingIntervalMs = 1000ms via Timer]
    │   ReadTagValues() → caches in memory dict → raises TagValuesUpdated event
    ▼
OpcDaService.cs  [singleton — manages all connections, exposes ReadAllTagValues()]
    │
    ├──► DataLoggingService.cs  [BackgroundService — has its OWN dedicated OPC connection]
    │       │   Creates OpcServerConnection independently (separate COM object)
    │       │   Polls every OpcPollingIntervalMs (1000ms)
    │       │   Calls TagValuesPoolService.UpdatePool() EVERY cycle
    │       │
    │       ├──► TagValuesPoolService.cs  [ConcurrentDictionary — shared in-memory cache]
    │       │       Updated every 1000ms by DataLoggingService
    │       │       Read by: OpcController (REST), OpcDaHub (SignalR)
    │       │
    │       └──► Parquet Writer
    │               SelectedTags from logging-config.json only
    │               Writes every 5000ms (configurable interval)
    │               Rotates at 10MB file size
    │               Output: D:\OpcLogs\Data\*.parquet
    │
    ├──► HistorianIngestHostedService.cs  [BackgroundService — reads DIRECTLY from OpcDaService]
    │       │   DOES NOT use TagValuesPoolService (bypasses DataLoggingService entirely)
    │       │   Calls _opcDaService.ReadAllTagValues() in PrecisePollingLoopAsync
    │       │   Syncs tag_master enabled tags → subscribes them to OPC if not already monitored
    │       │   Skips PLC tags (by checking ServerProgId vs OPC connection list)
    │       │
    │       ▼
    │   RateControllerService.cs  [per-tag deadband + interval filtering]
    │       │   IF deadband_value > 0 → |current - last| > deadband → write
    │       │   ELSE → current != last → write
    │       │   Also checks: timeSinceLastWrite >= DbLoggingIntervalMs
    │       │   Returns null → filtered (skip DB write)
    │       │   Returns MappedSample → pass to batcher
    │       │
    │       ▼
    │   BatcherService.cs  [accumulates MappedSamples in bounded channel]
    │       │   Flushes on: ShardCount batches OR FlushIntervalMs elapsed
    │       │
    │       ▼
    │   DbWriterService.cs  [PostgreSQL BINARY COPY — fastest bulk insert]
    │       │   Writes to: historian_raw.historian_timeseries
    │       │   On DB failure → SpoolManagerService (write to disk, replay later)
    │       │   Circuit breaker: stops writes when DB is unhealthy
    │       │
    │       └──► PostgreSQL / TimescaleDB
    │               historian_raw.historian_timeseries (hypertable)
    │               Columns: time, tag_id, value_num, value_bool, value_text,
    │                        quality, source, opc_timestamp, mapping_version
    │
    ├──► OpcDaHub.cs  [SignalR hub — real-time broadcast]
    │       Wired: _opcDaService.TagValuesUpdated += async lambda
    │       Broadcasts: Clients.All.SendAsync("TagValuesUpdated")
    │       Web UI subscribes via SignalR or polls GET /api/opc/values
    │
    └──► OpcMqttPublisherService.cs  [BackgroundService — OPC → MQTT]
            Reads: _opcDaService.ReadAllTagValues() (same main connection)
            Publishes: Topic = opc/{serverProgId}/tags/bulk
            Mode: ChangedOnly by default (only sends changed tags)
            QoS: configurable (OpcMqttTransport section in appsettings.json)
            ISOLATION: MQTT failure does NOT block historian or parquet writes
            Config: appsettings.json → OpcMqttTransport:Enabled (must be true)
```

### 1.2 Configuration Sources — OPC

| Setting | Source | Key | Default |
|---------|--------|-----|---------|
| OPC polling interval | `logging-config.json` | `OpcPollingIntervalMs` | 1000 ms |
| Parquet write interval | `logging-config.json` | `ParquetIntervalMs` | 5000 ms |
| Selected tags (parquet) | `logging-config.json` | `SelectedTags[]` | — |
| DB historian connection | `appsettings.json` | `ConnectionStrings:Historian` | — |
| Batch size | `appsettings.json` | `Historian:Writer:ShardCount` | — |
| Spool dir/size | `appsettings.json` | `Historian:Spool.*` | — |
| Rate control per tag | PostgreSQL `historian_meta.tag_master` | `deadband_value`, `db_logging_interval_ms` | — |
| OPC MQTT enabled | `appsettings.json` | `OpcMqttTransport:Enabled` | false |
| OPC MQTT broker | `appsettings.json` | `OpcMqttTransport:BrokerHost/BrokerPort` | — |

### 1.3 Mapping Cache — How Tags Enter Historian

```
PostgreSQL: historian_meta.tag_master
    │   Columns: tag_id, tag_name, data_type, deadband_value,
    │            db_logging_interval_ms, enabled, server_progid
    │
    │   pg_notify('mapping_updated') fires on INSERT/UPDATE/DELETE
    ▼
MappingCacheService.cs
    │   Listens to NOTIFY channel (instant update on change)
    │   Falls back to 30s polling if NOTIFY not received
    │   ConcurrentDictionary<string, TagMapping> _cache
    ▼
HistorianIngestHostedService.cs uses:
    GetAllEnabledMappings() — which tags to watch
    GetMapping(tagId) — per-tag deadband/interval for rate control
```

### 1.4 Timestamp Handling — Critical Detail

```
OPC Server returns: TagValue.Timestamp (OPC server clock)
HistorianIngest does:
    1. Uses pollTimestamp (DateTime.UtcNow at start of poll cycle) → stored in historian DB
       WHY: Respects DbLoggingIntervalMs. Using OPC timestamp would break rate control.
    2. Stores opcTimestamp separately as OpcTimestamp column → audit trail only
    3. FixTimestampForUniqueness(): if same tag gets same timestamp, adds +1ms
       → prevents TimescaleDB hypertable unique constraint violation
       → LRU evicts tracking state at 50K tags to prevent memory leak
```

### 1.5 Spool (Offline Buffering)

```
DB write fails
    ▼
SpoolManagerService.cs
    Writes batch to disk: appsettings.json → Historian:Spool:SpoolDirectory
    Max spool size: Historian:Spool:MaxSpoolSizeMB
    Drops OLDEST files when limit exceeded (never crashes)
    ▼
Spool Replay Timer (every Spool:ReplayIntervalSeconds)
    SemaphoreSlim(1) — only one replay at a time (no DB flooding)
    Throttled: Spool:ReplayBatchSize rows per cycle
    Replays oldest files first → deletes after success
```

---

## 2. PLC GATEWAY — AS-BUILT DATA FLOW

### 2.1 Top-Level Picture

```
Physical PLCs (TCP/IP network)
    │
    │   Siemens S7    → SiemensS7Driver.cs  (S7.Net library)
    │   Allen-Bradley → RockwellDriver.cs   (libplctag library)
    │   Modbus TCP    → ModbusTcpDriver.cs  (NModbus library)
    │   Omron FINS    → OmronDriver.cs      (FINS TCP)
    │   ABB           → AbbDriver.cs        (NModbus)
    │   Mitsubishi    → MitsubishiDriver.cs (NModbus)
    │
    ▼
PlcDriverFactory.cs
    Creates correct driver instance based on PlcProtocol enum
    EtherNetIP is DELETED — throws exception if configured
    ▼
PlcConnectionManager.cs  [manages all PLC connection lifecycles]
    For each PLC: one PlcConnection object + one isolated Task (PollingLoopAsync)
    Each loop is fully isolated: exception in PLC-1 does NOT affect PLC-2
    Polls every PollingIntervalMs (per-PLC config)
    ▼
PlcPoolManager → PlcTagValuesPoolService
    ConcurrentDictionary<"PlcId:TagId", PlcTagValue>
    Updated on every poll cycle
    PlcTagValue: { Value, Quality, Timestamp, PlcId, TagId }
    ▼
PlcSampleBufferService
    Buffers multiple samples per tag before publish
    Allows MQTT to send sample history (not just latest value)
    ▼
MultiProtocolPublisherService.cs  [BackgroundService — publishes every PublishIntervalMs]
    Reads: PlcTagValuesPoolService.GetAllValues() OR PlcSampleBufferService
    ▼
    ┌─────────────────────────────┬────────────────────────────────┐
    │                             │                                │
    ▼                             ▼                                ▼
MqttPublisher.cs          REST API                     LocalTcpBroadcastService.cs
(if Enabled=true)         PlcController.cs             Port 5050
Topic: plc/{plcId}/tags   GET /api/plc/values          Newline-delimited JSON
QoS 1 (at-least-once)     GET /api/plc/status          For plant-floor HMIs
Auto-reconnect            Always available             No internet required
```

### 2.2 PLC Config Loading

```
PlcConfigLoaderService.cs (startup + on-demand reload)
    1st try: PostgreSQL historian_meta.tag_master (WHERE source_type = 'PLC')
    Fallback: appsettings.json → PlcGateway:Connections[]
    
    After loading: EnsureMqttTopicsRegisteredAsync()
        Rule: topic_name = PlcId exactly (no prefix/suffix)
        Auto-inserts MQTT topic rows so subscribing HMI needs no manual DB step

PlcConfigPersistenceService.cs
    Saves runtime config changes back to JSON file
    Used when PLCs are added/modified via REST API at runtime
```

### 2.3 PLC Historian — CURRENT STATE (Direct DB Writes)

```
PlcTagValuesPoolService (shared cache)
    ▼
PlcHistorianIngestService.cs  ← STILL EXISTS IN CODE (not yet removed)
    Rate control: deadband + interval (same logic as OPC historian)
    Batch insert: BINARY COPY to plc_gateway.plc_timeseries
    
NOTE: The architecture doc marks this for REMOVAL and replacement with
      Central MQTT Subscriber. As of 24 May 2026, PlcHistorianIngestService
      is still present and writing directly to plc_gateway.plc_timeseries.
      MqttSubscriberService (Central Subscriber) does NOT yet exist in code.
```

### 2.4 PLC Database Tables (Currently Separate from OPC)

```
plc_gateway.plc_connections   — PLC config (plc_id, protocol, host, port, ...)
plc_gateway.plc_tags          — Tag definitions per PLC
plc_gateway.plc_timeseries    — PLC historian data (TimescaleDB hypertable)
                                Columns: time, tag_id, value, quality, plc_id, source_type

historian_raw.historian_timeseries  — OPC historian data (separate table)

FUTURE: Unified into historian_raw.historian_timeseries with source_type column.
        SQL migration defined in architecture docs but NOT yet executed.
```

### 2.5 Configuration Sources — PLC

| Setting | Source | Key |
|---------|--------|-----|
| PLC connections | DB or `appsettings.json` | `PlcGateway:Connections[]` |
| MQTT enabled | `appsettings.json` | `PlcGateway:Mqtt:Enabled` |
| MQTT broker | `appsettings.json` | `PlcGateway:Mqtt:BrokerHost/BrokerPort` |
| Publish interval | `appsettings.json` | `PlcGateway:Transport:PublishIntervalMs` |
| Local TCP port | `appsettings.json` | `PlcGateway:Transport:LocalTcpPort` (5050) |
| Per-tag deadband | `historian_meta.tag_master` | `deadband_value` |
| Per-tag interval | `historian_meta.tag_master` | `db_logging_interval_ms` |

---

## 3. COMBINED: WHERE THINGS ACTUALLY WRITE

| Data | Written By | Written To | Frequency |
|------|-----------|-----------|-----------|
| OPC values (historian) | `HistorianIngestHostedService` | `historian_raw.historian_timeseries` | Per tag's `DbLoggingIntervalMs` (only on change) |
| OPC values (parquet) | `DataLoggingService` | `D:\OpcLogs\Data\*.parquet` | Every 5000ms, SelectedTags only |
| OPC values (HMI cache) | `DataLoggingService` → `TagValuesPoolService` | In-memory | Every 1000ms |
| OPC values (MQTT) | `OpcMqttPublisherService` | MQTT broker `opc/{server}/tags/bulk` | Changed values only |
| OPC values (SignalR) | `OpcDaHub` | Browser WebSocket | Every TagValuesUpdated event |
| PLC values (historian) | `PlcHistorianIngestService` | `plc_gateway.plc_timeseries` | Per deadband/interval |
| PLC values (MQTT) | `MultiProtocolPublisherService` | MQTT broker `plc/{plcId}/tags` | Every `PublishIntervalMs` |
| PLC values (REST) | `PlcController` | HTTP response (no storage) | On client request |
| PLC values (TCP) | `LocalTcpBroadcastService` | TCP port 5050 | Every `PublishIntervalMs` |

---

## 4. ARCH DOCS vs ACTUAL CODE — DISCREPANCIES

| Item | Architecture Doc Says | Actual Code | Impact |
|------|-----------------------|-------------|--------|
| `HistorianIngestHostedService` reads from | `OpcDaService.ReadAllTagValues()` directly | ✅ CONFIRMED — `_opcDaService.ReadAllTagValues()` called at line 729 | None — correct |
| `DataLoggingService` is NOT in historian path | Parquet only | ✅ CONFIRMED — `TagValuesPoolService` is only for HMI/REST, not historian | None |
| OPC MQTT Publisher | Described as future/new | ✅ EXISTS NOW — `OpcMqttPublisherService.cs` implemented and registered | Good — MQTT publishing done |
| `PlcHistorianIngestService` | Marked ⚠️ REMOVED in future arch | ❌ STILL IN CODE — not yet deleted | Low risk — still writing PLC data to DB correctly |
| Central MQTT Subscriber | Marked 🆕 NEW | ❌ DOES NOT EXIST YET — `MqttSubscriberService.cs` not found | No impact on current ops |
| PLC + OPC unified table | `historian_raw.historian_timeseries` with `source_type` column | ❌ NOT YET — PLC uses `plc_gateway.plc_timeseries`, OPC uses `historian_raw.historian_timeseries` | Queries must JOIN two tables to get all data |
| `EtherNetIpDriver.cs` | DELETED (throws exception) | ✅ CONFIRMED — file does not exist in `Drivers/` folder | None |

---

## 5. CRITICAL RULES (DO NOT VIOLATE)

1. **`OpcDaService` is the single OPC truth source** — historian reads `ReadAllTagValues()`, NOT TagValuesPoolService
2. **`DataLoggingService` creates its own OPC connection** — separate from main; only for parquet + HMI cache
3. **`TagValuesPoolService` is HMI-only** — feeds `GET /api/opc/values` and SignalR; NOT the historian source
4. **Rate control is mandatory** — `RateControllerService.ProcessSample()` must not be bypassed for DB writes
5. **PLC isolation** — each PLC runs in its own Task; exceptions do not cross PLC boundaries
6. **Spool oldest-first drop** — when spool exceeds `MaxSpoolSizeMB`, drop oldest files, never crash
7. **No simulation values** — drivers return `null` / `Quality=Bad` on failure; never generate fake data

---

## 6. FILE LOCATIONS (Key Source Files)

```
Services/
├── OpcDaService.cs                              — OPC connection manager (singleton)
├── OpcServerConnection.cs                       — Single OPC server polling (COM/DCOM)
├── DataLoggingService.cs                        — Dedicated OPC loop → parquet + HMI pool
├── TagValuesPoolService.cs                      — HMI in-memory cache only
├── OpcMqttPublisherService.cs                   — OPC → MQTT publisher
├── OpcAutoConnectService.cs                     — Auto-reconnect background service
├── HistorianIngest/
│   ├── Services/HistorianIngestHostedService.cs  — Main historian pipeline (polls OpcDaService)
│   ├── Services/RateControllerService.cs         — Deadband/interval filtering
│   ├── Services/MappingCacheService.cs           — tag_master cache (NOTIFY + 30s poll)
│   ├── Services/BatcherService.cs                — Sample accumulator (bounded channel)
│   ├── Services/DbWriterService.cs               — PostgreSQL BINARY COPY writer
│   └── Services/SpoolManagerService.cs           — Disk spool for offline buffering
└── PlcGateway/
    ├── Services/PlcConnectionManager.cs          — PLC lifecycle + isolated polling loops
    ├── Services/PlcConfigLoaderService.cs        — Loads PLC config from DB or JSON
    ├── Services/PlcTagValuesPoolService.cs        — PLC shared cache (ConcurrentDictionary)
    ├── Services/PlcSampleBufferService.cs         — Multi-sample buffer before publish
    ├── Transport/MultiProtocolPublisherService.cs — Publishes to MQTT + REST + TCP
    ├── Transport/MqttPublisher.cs                 — MQTT client (QoS 1, auto-reconnect)
    ├── Transport/LocalTcpBroadcastService.cs      — Plant-floor TCP broadcast (port 5050)
    └── Drivers/
        ├── PlcDriverFactory.cs                   — Creates driver by protocol enum
        ├── SiemensS7Driver.cs                    — S7.Net
        ├── RockwellDriver.cs                     — libplctag
        ├── ModbusTcpDriver.cs                    — NModbus
        ├── OmronDriver.cs                        — FINS TCP
        ├── AbbDriver.cs                          — NModbus
        └── MitsubishiDriver.cs                   — NModbus

Hubs/
└── OpcDaHub.cs                                  — SignalR hub (real-time OPC broadcast)

Controllers/
├── OpcController.cs                             — GET /api/opc/values (reads TagValuesPool)
└── PlcController.cs                             — GET /api/plc/values, /api/plc/status
```

---

*Generated: 24 May 2026*  
*Source verified: actual .cs files in Services/ directory*  
*Arch docs consulted: ARCHITECTURE_OPC_CURRENT_VS_FUTURE.md, ARCHITECTURE_PLC_CURRENT_VS_FUTURE.md*
