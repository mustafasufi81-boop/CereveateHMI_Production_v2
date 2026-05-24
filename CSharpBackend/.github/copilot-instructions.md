# Cereveate OPC DA / Analytics Platform – AI Agent Guide

## ⛔ CRITICAL: NO SIMULATION CODE POLICY ⛔

**THIS IS A PRODUCTION INDUSTRIAL SYSTEM - COMPANY POLICY VIOLATION WARNING**

### STRICTLY PROHIBITED (ZERO TOLERANCE):
1. **NO `Random()` or `NextDouble()` or fake value generation** inside ANY driver or service
2. **NO placeholder implementations** that return dummy/fake data
3. **NO "simulation" mode** inside production communication drivers
4. **NO hardcoded test values** that pretend to be real PLC/OPC data

### WHY THIS IS CRITICAL:
- Industrial systems control REAL equipment (pumps, turbines, valves)
- Fake values can cause **DANGEROUS DECISIONS** by operators
- Simulation data mixed with real data = **DATA INTEGRITY VIOLATION**
- Company policy treats this as **SERIOUS MISCONDUCT**

### WHAT TO DO INSTEAD:
- If a driver is not implemented → **throw `NotImplementedException`** with clear message
- If connection fails → return `null` value with `Quality = Bad` or `CommError`
- If you need test data → use **SEPARATE simulation server** (e.g., Matrikon OPC Simulator)
- **NEVER** mix simulation logic inside production code

### DELETED FILES (Dec 2025):
- `EtherNetIpDriver.cs` - DELETED because it was a placeholder returning null/fake values
- Use `PlcProtocol.Rockwell` with `RockwellDriver.cs` for Allen-Bradley PLCs instead

### WORKING DRIVERS (Real Implementation):
| Protocol | Driver | Library | Status |
|----------|--------|---------|--------|
| `Rockwell` | RockwellDriver.cs | libplctag | ✅ WORKING |
| `SiemensS7` | SiemensS7Driver.cs | S7.Net | ✅ WORKING |
| `ModbusTcp` | ModbusTcpDriver.cs | NModbus | ✅ WORKING |
| `Omron` | OmronDriver.cs | FINS TCP | ✅ WORKING |
| `ABB` | AbbDriver.cs | NModbus | ✅ WORKING |
| `Mitsubishi` | MitsubishiDriver.cs | NModbus | ✅ WORKING |
| `EtherNetIP` | ❌ DELETED | - | NOT IMPLEMENTED (throws error) |

---

## High-Level Architecture
```
══════════════════ OPC DA PATH ══════════════════
OPC DA Servers (Local/Remote via DCOM — Windows x86 only)
    ↓
OpcDaService (singleton — manages all OPC connections, exposes ReadAllTagValues())
    ↓
    ├── OpcDaHub (SignalR) ← TagValuesUpdated event → Web UI real-time
    ├── OpcMqttPublisherService → MQTT broker  topic: opc/{serverId}/tags/bulk
    ├── DataLoggingService (own OPC conn) → Parquet files + TagValuesPoolService (HMI cache)
    │       TagValuesPoolService → OpcController GET /api/opc/values → HMI polling
    └── HistorianIngestHostedService → RateController → BatcherService → DbWriterService
            ↓                                                              ↓
    historian_raw.historian_timeseries (TimescaleDB)         SpoolManagerService (disk)

══════════════════ PLC GATEWAY PATH ══════════════════
Physical PLCs (TCP/IP)
    ↓
PlcDriverFactory → [SiemensS7 | Rockwell | ModbusTcp | Omron | ABB | Mitsubishi]
    ↓
PlcConnectionManager → one isolated polling Task per PLC
    ↓
PlcTagValuesPoolService (ConcurrentDictionary — shared cache)
    ↓
MultiProtocolPublisherService
    ├── MqttPublisher → MQTT broker  topic: plc/{plcId}/tags
    ├── PlcController REST API → GET /api/plc/values
    └── LocalTcpBroadcastService → Port 5050 (plant-floor HMIs)
PlcHistorianIngestService → plc_gateway.plc_timeseries (TimescaleDB)

══════════════════ ANALYTICS PATH ══════════════════
Parquet files (D:\OpcLogs\Data\) → PostgresLogger importer → sensor_data (TimescaleDB)
historian_raw.historian_timeseries → FastAPI (port 8000) + Flask BI (port 5001)
```

## Core Service Boundaries
1. **C# Runtime (`Program.cs`)**: ASP.NET Core with SignalR hub `/opcHub`, background hosted services (auto-connect, data logging, backup, historian ingest, PLC gateway, MQTT publisher). **MUST BE x86 for COM interop**.
2. **OPC DA Acquisition**: `OpcDaService` (singleton) manages multiple connections; `OpcServerConnection` polls tags (1000ms default); raises `TagValuesUpdated` event; exposes `ReadAllTagValues()` as the single truth source for all OPC consumers.
3. **TagValuesPoolService (HMI Cache Only)**: In-memory tag cache updated by `DataLoggingService` every 1000ms. Accessed **only** by: (a) HMI via `/api/opc/values` API, (b) `OpcDaHub` SignalR broadcasts. ⛔ **NOT used by historian** — historian reads `OpcDaService.ReadAllTagValues()` directly. Uses `ConcurrentDictionary` for thread safety.
4. **Parquet Logging**: `DataLoggingService` maintains its **own dedicated OPC connection** (separate from the main `OpcDaService` connection). Writes rotating 10MB parquet files for **selected tags only** (from `logging-config.json` → `SelectedTags`). Also updates `TagValuesPoolService` every 1000ms for HMI use. NOT in the historian write path.
5. **Historian Ingest Pipeline**: `HistorianIngestHostedService` → reads **directly from `OpcDaService.ReadAllTagValues()`** → auto-subscribes enabled `tag_master` OPC tags if not yet monitored → skips PLC tags (by `server_progid` match) → `RateControllerService` (deadband + interval) → `BatcherService` (bounded channel) → `DbWriterService` (BINARY COPY) → `historian_raw.historian_timeseries`. On DB failure → `SpoolManagerService` (disk, oldest-drop, throttled replay).
6. **OPC MQTT Publisher**: `OpcMqttPublisherService` reads `OpcDaService.ReadAllTagValues()` and publishes changed-values-only to topic `opc/{serverProgId}/tags/bulk`. Controlled by `appsettings.json → OpcMqttTransport:Enabled`. Failure does NOT affect historian or parquet.
7. **PLC Gateway**: `PlcConnectionManager` manages one isolated polling Task per PLC (protocol drivers: S7, Rockwell, Modbus, Omron, ABB, Mitsubishi). Results feed `PlcTagValuesPoolService`. `MultiProtocolPublisherService` publishes to MQTT (`plc/{plcId}/tags`), REST (`/api/plc/values`), and TCP port 5050 simultaneously. `PlcHistorianIngestService` writes directly to `plc_gateway.plc_timeseries` (separate table from OPC historian — unification is future work).
8. **PostgresLogger**: Imports parquet columns into TimescaleDB `sensor_data` table; FastAPI (`api/main.py`) serves trends + WebSocket `/ws/live-data`.
9. **Historical Analytics (`HistoricalTrends`)**: Flask (port 5001) viewer + FastAPI BI (port 8000) executing stateless engines in `bi_engines/`.

## Non-Negotiable Patterns (DO NOT ALTER)
1. **Remote OPC discovery COM cast** (`OpcDaService.cs` lines 94–104): `EnumClassesOfCategories` → `out object` → cast to `OpcRcw.Comn.IEnumGUID`. Wrong cast = E_NOINTERFACE.
2. **SignalR event wiring** (`OpcDaHub.cs` lines 44–47): `_opcDaService.TagValuesUpdated += async (s, e) => await OnTagValuesUpdatedAsync(s, e)` → broadcast `Clients.All.SendAsync("TagValuesUpdated")`. Must use async lambda to avoid async void.
3. **Singleton + HostedService reuse**: Register singleton first, then `AddHostedService(provider => provider.GetRequiredService<LogBackupService>())` to reuse same instance.
4. **File locking in logging & simulation**: Preserve `lock(_fileLock)` (C#) and `.lock` file + temp file rename (Python) patterns. Atomic writes prevent corruption.
5. **Historian pipeline reads from OpcDaService directly**: `HistorianIngestHostedService` calls `_opcDaService.ReadAllTagValues()` (the main singleton connection) instead of reading from `TagValuesPoolService`. `DataLoggingService` is **NOT** in the historian write path — it only handles Parquet files. DO NOT reintroduce `TagValuesPoolService` as a historian data source.
6. **RateControllerService change detection**: MANDATORY logic for database writes (lines 156-170): IF `deadband_value > 0` THEN check `|current - last| > deadband`, ELSE check `current != previous`. Only writes to database when values change. DO NOT bypass rate controller.

## Data Flows (Essential)

### Real-Time OPC Flow (VERIFIED MAY 2026 — matches actual code)
```
OPC Server (Matrikon.OPC.Simulation.1)
    ↓
OpcServerConnection.ReadTagValues() [polls every OpcPollingIntervalMs=1000ms via Timer]
    ↓
OpcDaService (singleton — ALL consumers call ReadAllTagValues() from here)
    ↓
    ├─────→ DataLoggingService  [PARQUET + HMI CACHE ONLY — NOT historian path]
    │       • Has its OWN dedicated OPC connection (separate COM object)
    │       • Polls every 1000ms: reads values → UpdatePool() → optionally writes parquet
    │       • Parquet writes: every 5000ms, SelectedTags from logging-config.json, 10MB rotation
    │       • TagValuesPoolService updated every 1000ms regardless of parquet interval
    │
    ├─────→ HMI Web UI
    │       • API: GET /api/opc/values (OpcController.cs)
    │       • Reads: TagValuesPoolService.GetAllTagValues()  ← fed by DataLoggingService
    │       • Also: SignalR subscription (OpcDaHub broadcasts TagValuesUpdated)
    │
    ├─────→ OpcMqttPublisherService  [OPC → MQTT — verified in OpcMqttPublisherService.cs]
    │       • Reads: _opcDaService.ReadAllTagValues() directly
    │       • Publishes changed values only (ChangedOnly mode default)
    │       • Topic: opc/{serverProgId}/tags/bulk  QoS: configurable
    │       • Config: appsettings.json → OpcMqttTransport:Enabled (must be true to activate)
    │       • ISOLATION: MQTT failure does NOT block historian or parquet
    │
    ├─────→ HistorianIngestHostedService  [DIRECT OPC READ — verified in code line 729]
    │       • Reads: _opcDaService.ReadAllTagValues() directly — NOT TagValuesPoolService
    │       • On startup: auto-subscribes enabled tag_master OPC tags not yet monitored
    │       • Skips PLC tags: checks server_progid vs list of OPC connection ProgIDs
    │       • Uses pollTimestamp (not OPC timestamp) for DB — respects DbLoggingIntervalMs
    │       • Preserves OPC server timestamp in opc_timestamp column for audit trail
    │       • Timestamp dedup: adds +1ms if same tag gets same timestamp (LRU, max 50K tags)
    │       • Rate Control: RateControllerService.ProcessSample()
    │         → deadband>0: |curr-last|>deadband → write
    │         → no deadband: curr!=last → write
    │         → interval not elapsed AND no spike → filter
    │       • Pipeline: RateController → BatcherService (bounded channel) → DbWriterService
    │       • DB write: BINARY COPY to historian_raw.historian_timeseries
    │       • DB fail: SpoolManagerService → disk (oldest-drop at MaxSpoolSizeMB)
    │       • Spool replay: throttled via SemaphoreSlim(1), configurable rate
    │
    └─────→ SignalR Hub (OpcDaHub.cs)
            • Wired: _opcDaService.TagValuesUpdated += async lambda
            • Broadcast: Clients.All.SendAsync("TagValuesUpdated")
```

### Parquet Logging Flow (Separate Path)
```
DataLoggingService [same loop, 1000ms]
    ↓
Check: timeSinceLastWrite >= _currentIntervalMs (5000ms)
    ↓
IF TRUE → Write parquet file (ONLY SelectedTags from logging-config.json)
IF FALSE → Skip parquet write (pool already updated above)
```

### Database Write Decision Logic (RateControllerService.cs)
```csharp
// FOR EACH TAG FROM POOL:
var mapping = _mappingCache.GetMapping(tagId);

// RULE 1: First sample → always write
if (!lastWrittenTime.HasValue) return WRITE;

// RULE 2: Interval elapsed → check if value changed
if (timeSinceLastWrite >= intervalMs) {
    if (deadband_value > 0) {
        // Deadband configured → threshold check
        valueChanged = Math.Abs(current - last) > deadband_value;
    } else {
        // No deadband → exact comparison
        valueChanged = (current != last);
    }
    
    return valueChanged ? WRITE : FILTER;
}

// RULE 3: Deadband exceeded before interval (spike detection)
if (deadband_value > 0 && Math.Abs(current - last) > deadband_value) {
    return WRITE; // Immediate write on spike
}

// NO CONDITIONS MET → filter
return FILTER;
```

### Real-Time OPC Flow (summary)
`OpcServerConnection.ReadTagValues()` (timer 1000ms) → `OpcDaService` in-memory cache → three independent consumers:
1. **SignalR broadcast**: `TagValuesUpdated` event → `OpcDaHub` → `Clients.All.SendAsync("TagValuesUpdated")` → Web UI
2. **Historian DB**: `HistorianIngestHostedService.PrecisePollingLoopAsync()` calls `ReadAllTagValues()` \u2192 rate control \u2192 BINARY COPY \u2192 `historian_raw.historian_timeseries`
3. **MQTT**: `OpcMqttPublisherService` calls `ReadAllTagValues()` \u2192 changed-only publish \u2192 `opc/{serverId}/tags/bulk`

### Parquet Logging Flow (Separate)
`DataLoggingService` → reads **ONLY SelectedTags** from `logging-config.json` → writes parquet rotation (10MB threshold) → Python engines consume parquet; PostgresLogger importer watches `D:\OpcLogs\Data` → Timescale `sensor_data` hypertable.

### PLC Gateway Flow (VERIFIED — matches PlcConnectionManager.cs + MultiProtocolPublisherService.cs)
```
Physical PLCs (TCP/IP network)
    ↓
PlcDriverFactory.CreateDriver(protocol)  [S7/Rockwell/Modbus/Omron/ABB/Mitsubishi]
    ↓
PlcConnectionManager.PollingLoopAsync()  [one isolated Task per PLC]
    │   Exception in PLC-1 never reaches PLC-2 (try/catch at loop top)
    │   Reconnects automatically on failure
    ↓
PlcTagValuesPoolService  [ConcurrentDictionary<"PlcId:TagId", PlcTagValue>]
    ↓
PlcSampleBufferService  [buffers multiple samples per tag before publish]
    ↓
MultiProtocolPublisherService  [publishes every PublishIntervalMs to ALL protocols]
    ├── MqttPublisher → MQTT broker  topic: plc/{plcId}/tags  QoS 1  auto-reconnect
    ├── PlcController GET /api/plc/values  (REST — always available)
    └── LocalTcpBroadcastService → Port 5050  (newline-JSON, plant-floor HMIs, no internet)

PlcHistorianIngestService  [CURRENTLY STILL IN CODE — writes directly]
    → Rate control (deadband + interval, same logic as OPC historian)
    → BINARY COPY to plc_gateway.plc_timeseries  ← SEPARATE table from OPC historian
    NOTE: Architecture doc marks this for removal (Central MQTT Subscriber to replace it)
          but MqttSubscriberService does NOT yet exist. Do not delete until replacement built.
```

### PLC Config Loading
`PlcConfigLoaderService` loads from DB (`historian_meta.tag_master` WHERE `source_type='PLC'`) first, falls back to `appsettings.json → PlcGateway:Connections[]`. After loading, auto-registers MQTT topics (topic_name = PlcId). Runtime changes saved by `PlcConfigPersistenceService`.

### CRITICAL: Historian Tag Mapping Flow
**Problem**: Historian ingest ONLY processes tags in `historian_meta.tag_master` table. Empty table = no DB writes.
**Solution**:
1. Connect to OPC server via web UI (establishes main connection in `OpcDaService`)
2. Insert tag mappings into `historian_meta.tag_master` (use SQL — see example below)
3. `MappingCacheService` auto-refreshes via PostgreSQL NOTIFY channel (`mapping_updated`) — 30s polling fallback
4. `HistorianIngestHostedService.PrecisePollingLoopAsync()` calls `_opcDaService.ReadAllTagValues()` → matches against `MappingCacheService.GetAllEnabledMappings()` → `RateControllerService` → `BatcherService` → DB

⚠️ **PLC tags in tag_master**: If `server_progid` does not match any connected OPC server ProgID, the tag is skipped by the OPC historian (treated as PLC tag). PLC tags are handled by `PlcHistorianIngestService` writing to `plc_gateway.plc_timeseries` — separate table.

**SQL Example**:
```sql
INSERT INTO historian_meta.tag_master (tag_id, tag_name, data_type, deadband_value, db_logging_interval_ms, enabled, created_by)
VALUES ('Random.Real4', 'Random Value', 'double', 0.5, 1000, true, 'admin')
ON CONFLICT (tag_id) DO UPDATE SET enabled = true;
```

**Deadband Configuration**:
- `deadband_value = 0` or `NULL`: Exact comparison (write on any change)
- `deadband_value > 0`: Threshold comparison (write only if `|current - last| > deadband`)
- Applies to `double` and `int` data types only
- Boolean/String always use exact comparison

**SQL Example**:
```sql
INSERT INTO historian_meta.tag_master (tag_id, tag_name, data_type, deadband_value, db_logging_interval_ms, enabled, created_by)
VALUES ('Random.Real4', 'Random Value', 'double', 0.5, 1000, true, 'admin')
ON CONFLICT (tag_id) DO UPDATE SET enabled = true;
```

**Deadband Configuration**:
- `deadband_value = 0` or `NULL`: Exact comparison (write on any change)
- `deadband_value > 0`: Threshold comparison (write only if `|current - last| > deadband`)
- Applies to `double` and `int` data types only
- Boolean/String always use exact comparison

## Configuration Sources
Central: `logging-config.json` (paths, selected tags for parquet, **OpcPollingIntervalMs=1000ms**, parquet interval 5000ms).
Historian DB: `appsettings.json` → `Historian` section (PostgreSQL connection, batch config, spool settings).
OPC MQTT: `appsettings.json` → `OpcMqttTransport` section (Enabled, BrokerHost, BrokerPort, ClientId, TopicPrefix, PublishMode, QualityOfService).
PLC Gateway: `appsettings.json` → `PlcGateway` section (Connections[], Mqtt:Enabled/BrokerHost/BrokerPort, Transport:PublishIntervalMs/LocalTcpPort).
Historian Tag Mappings: `historian_meta.tag_master` table (tag_id, source_type, server_progid, data_type, deadband_value, db_logging_interval_ms, enabled).
PostgresLogger: `config/app_config.json` (DB creds, parquet source, web UI port 6001, tag mappings for sensor_data table).
Simulation: `ParquetDataGenerator/config.json` (interval, downtime probability).
BI: `derived_analytics_config.json`, `bi_engines/config/bi_config.yaml`.

## PostgresLogger Database Schema (TimescaleDB/PostgreSQL)
**sensor_data** (17 cols): id, timestamp, ingest_timestamp, plant, asset, subsystem, tag_name, tag_code, value, raw_value, unit, quality_code, status_flag, data_source, sensor_id, shift, batch_id. Hypertable partitioned by timestamp.

**tag_catalog** (7 cols): tag_id (PK), first_seen, last_seen, last_file, record_count (bigint), is_mapped (boolean), last_updated (timestamptz). Tracks ALL unique TagIds discovered from parquet files (mapped or unmapped). Updated during file import scan.

**tag_file_catalog** (8 cols): tag_id, file_path, file_hash, first_seen, last_seen, record_count, file_size_bytes, last_updated. Per-tag per-file tracking.

**file_imports** (19 cols): id, file_path, file_hash, file_size, import_timestamp, records_imported, status, error_message, worker_id, lock_acquired_at, started_at, completed_at, processing_time_ms, tags_imported, tags_skipped, file_format, total_tags_in_file, total_rows_in_file, enqueued_at. Status: PENDING → PROCESSING → SUCCESS/FAILED. Unique constraint on (file_path, file_hash) for idempotency.

**tag_files_view**: Aggregated view of tag_id, file_count, total_records, earliest_data, latest_data, files array.

## PostgresLogger Key Behaviors
QUICK_START outlines start scripts: `START_ALL.bat`, `start_server.bat`, `start_importer.bat`. Web UI tabs: Live (auto-refresh), Historical (date range), Tag Configuration (manual or auto-discover), Statistics. Importer populates `file_imports` with status + hash; trends endpoints cap results by `default_chart_points` & `max_chart_points`.

## Simulation Downtime Rules
Downtime sets `GENERATOR_LOAD_MW` & `TURBINE_SPEED` → 0; ~30% null sensors; thermals/pressures reduced 40–60%; vibrations drop to minimum. Use for resilience tests (check importer null handling).

## BI / Frontend Patterns
JavaScript modules under `HistoricalTrends/static/modules/` (e.g., `advanced_bi_engine.js` large single class with baseline/outlier methods). Prefer adding new analytics as separate Python engine files (stateless) coordinated via orchestrator.

## Typical Build / Run Workflows
Dotnet publish: `build.bat` (self-contained single-file). Distribution: `create-distribution.bat`. Run C# dev: `dotnet run` (ensure x86). Start PostgresLogger full stack: `START_ALL.bat`. Start simulation: `python app.py` (port 5004). BI FastAPI: `uvicorn bi_api:app --port 8000`. Flask viewer: `python app.py` (HistoricalTrends).

## Common Failure Checks
SignalR 404 → hub mapped after `UseRouting`. Remote discovery errors → confirm COM cast. Stalled tag updates → verify hub subscription intact. Python service silent → missing `logging-config.json`. No parquet files → check `DataLoggingService` enabled & `SelectedTags` array populated. **No DB inserts → verify `historian_meta.tag_master` table populated with enabled mappings** → check `HistorianIngestHostedService` logs for "No enabled tag mappings" warning → ensure OPC server connected first (historian reuses main connection). Large parquet backlog → adjust `check_interval_seconds` & batch size (`import_settings.batch_size`).

## Safe Modification Guidelines
Add new OPC features via new service class (singleton) raising events → hub broadcast. Extend PostgresLogger config by adding keys then using `config_manager.config[...]` & persisting `save_config()`. Add BI engine: create file in `bi_engines/`, stateless functions/classes, update orchestrator; avoid modifying existing engine method signatures.

## Files to Consult First
`README_WORKING_VERSION.md` (baseline stability). `OpcDaService.cs`, `OpcServerConnection.cs`, `OpcDaHub.cs` (real-time OPC path). `DataLoggingService.cs` (parquet + HMI cache). `OpcMqttPublisherService.cs` (OPC→MQTT). `Services/HistorianIngest/Services/HistorianIngestHostedService.cs` (DB write pipeline). `Services/HistorianIngest/Services/RateControllerService.cs` (deadband logic). `Services/PlcGateway/Services/PlcConnectionManager.cs` (PLC polling). `Services/PlcGateway/Transport/MultiProtocolPublisherService.cs` (PLC broadcast). `PostgresLogger/api/main.py` (DB API shape). `HistoricalTrends/BI_ENGINE_PYTHON_BACKEND_README.md` (analytics rationale). `OPC_PLC_DATAFLOW_AS_BUILT_24MAY2026.md` (verified as-built data flow reference).

## DO / DON'T Summary
DO preserve COM + event wiring; DO reuse singleton hosted pattern; DO respect lock/atomic write patterns; DO update config via managers not ad-hoc file writes; DON'T refactor large JS engine into multiple files without plan; DON'T switch platform target off x86; DON'T auto-apply tag discovery (endpoint intentionally disabled) – use manual mapping.

## When Adding New Code
Reference existing naming (e.g., `*Service`, `*Engine`, `*Manager`). Provide explicit event emissions for real-time paths. Keep parquet schema additions backward-compatible (append columns; consumers filter). Update instructions here if introducing new cross-cutting patterns.

---

## 🔄 HOW TO RESTART ALL SERVICES (EXACT PROCEDURE — DO NOT DEVIATE)

### Service Map
| # | Service | Port | Process | Exe / Command |
|---|---------|------|---------|---------------|
| 1 | C# OPC Backend | 5001 | `OpcDaWebBrowser.exe` | `bin\Release\net8.0\win-x86\OpcDaWebBrowser.exe` |
| 2 | Flask HMI Backend | 6001 | `python.exe` (app.py) | `WEB_HMI_MFA\HMI\app.py` |
| 3 | React Vite HMI | 8090 | `node.exe` (npm run dev) | `WEB_HMI_MFA\HMI\apex-hmi\` |

### ⚠️ CRITICAL WARNINGS BEFORE RESTART
1. **NEVER use `RESTART_SERVER.bat`** — it runs `dotnet build` which takes minutes and blocks.
2. **ALWAYS verify port ownership before assuming a service is running** — `WsToastNotification` or other Windows processes can steal port 8090. A port `LISTENING` does NOT mean the right process is there.
3. **ALWAYS check with `Get-Process -Id <PID>`** to confirm the correct process owns the port.
4. **Flask restart**: Kill by PID (from netstat), then `Start-Process python app.py`. Wait 4s before testing.
5. **Vite restart**: Kill the `node.exe` PID owning 8090, then run `npm run dev` in `apex-hmi\` folder. Wait 8s.
6. **C# restart**: Use the pre-built exe at `bin\Release\net8.0\win-x86\OpcDaWebBrowser.exe` — NOT `dotnet run`.

### Step-by-Step Restart (PowerShell — run as-is)

#### STEP 1 — Check what is actually running
```powershell
netstat -ano | findstr "5001 6001 8090" | findstr LISTENING
# Then verify each PID:
Get-Process -Id <PID_5001>, <PID_6001>, <PID_8090> | Select-Object Id, ProcessName
# Expected: OpcDaWebBrowser, python, node
```

#### STEP 2 — Kill all three (if restarting everything)
```powershell
# Kill C# (5001)
$p1 = (netstat -ano | Select-String ":5001.*LISTENING") -replace '.*\s+(\d+)$','$1'
Stop-Process -Id ([int]$p1.Trim()) -Force -ErrorAction SilentlyContinue

# Kill Flask (6001)
$p2 = (netstat -ano | Select-String ":6001.*LISTENING") -replace '.*\s+(\d+)$','$1'
Stop-Process -Id ([int]$p2.Trim()) -Force -ErrorAction SilentlyContinue

# Kill Vite (8090)
$p3 = (netstat -ano | Select-String ":8090.*LISTENING") -replace '.*\s+(\d+)$','$1'
Stop-Process -Id ([int]$p3.Trim()) -Force -ErrorAction SilentlyContinue

Start-Sleep -Seconds 2
```

#### STEP 3 — Start C# OPC Backend (port 5001)
```powershell
$ROOT = "c:\MQTT_Implemented_OPC\Copied_MQTT\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206"
Start-Process -FilePath "$ROOT\bin\Release\net8.0\win-x86\OpcDaWebBrowser.exe" `
              -WorkingDirectory "$ROOT\bin\Release\net8.0\win-x86" `
              -WindowStyle Minimized
Start-Sleep -Seconds 6
netstat -ano | findstr ":5001" | findstr LISTENING
# Must show a PID. Verify: Get-Process -Id <PID> → ProcessName = OpcDaWebBrowser
```

#### STEP 4 — Start Flask HMI Backend (port 6001)
```powershell
$ROOT = "c:\MQTT_Implemented_OPC\Copied_MQTT\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206"
Start-Process -FilePath python -ArgumentList "app.py" `
              -WorkingDirectory "$ROOT\WEB_HMI_MFA\HMI" `
              -WindowStyle Minimized
Start-Sleep -Seconds 4
netstat -ano | findstr ":6001" | findstr LISTENING
# Must show a PID. Test: Invoke-RestMethod "http://localhost:6001/api/alarms/active" -Headers @{"Authorization"="Bearer dummy"}
```

#### STEP 5 — Start React Vite HMI (port 8090)
```powershell
$ROOT = "c:\MQTT_Implemented_OPC\Copied_MQTT\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206"
Start-Process -FilePath "cmd.exe" -ArgumentList "/c npm run dev" `
              -WorkingDirectory "$ROOT\WEB_HMI_MFA\HMI\apex-hmi" `
              -WindowStyle Minimized
Start-Sleep -Seconds 10
netstat -ano | findstr ":8090" | findstr LISTENING
# Verify: Get-Process -Id <PID> → ProcessName = node  (NOT WsToastNotification or anything else)
```

#### STEP 6 — Final verification (all 3 must pass)
```powershell
netstat -ano | findstr "5001 6001 8090" | findstr LISTENING
# Should show 3 lines. Then spot-check responses:
Invoke-RestMethod "http://localhost:6001/api/alarms/active" -Headers @{"Authorization"="Bearer dummy"} | Select-Object success, count
Invoke-WebRequest "http://localhost:8090" -UseBasicParsing | Select-Object StatusCode
# 6001 → success=True; 8090 → StatusCode=200
```

### Login Credentials
- URL: `http://localhost:8090`
- Username: `Mustafa`
- Password: `Admin@123`

### Common Failure Patterns
| Symptom | Cause | Fix |
|---------|-------|-----|
| Port 8090 LISTENING but HMI blank/501 | `WsToastNotification` stole the port | `Stop-Process -Id <PID> -Force` then start Vite |
| Flask returns `{"error":"0"}` | Duplicate route registration in alarm_controller.py | Check for duplicate `@alarm_bp.route` decorators |
| C# port 5001 not listening | exe not started or crashed | Start `bin\Release\net8.0\win-x86\OpcDaWebBrowser.exe` directly |
| Vite starts but shows old code | HMR working but browser cached | Hard refresh `Ctrl+Shift+R` in browser |
| Flask starts but DB errors | PostgreSQL not running | Check `pg_ctl status` or Services panel |

---

## Long-Term Architecture Decisions (Approved May 2026)

These are **binding design decisions** for all future development. Every new feature must be evaluated against these rules.

### 1. OpcDaService is the Single OPC Truth Source
- `OpcDaService.ReadAllTagValues()` is the **only** entry point for OPC data into any consumer.
- HMI, historian, analytics, and any future service **must all read from the same in-memory snapshot**.
- `DataLoggingService` keeps its own OPC connection for Parquet only — it must **never** be in any historian or analytics write path.
- DO NOT create additional OPC connections for historian or analytics purposes.

### 2. Unified Historian Engine (Target Architecture)
```
Many acquisition sources (OPC, PLC-Modbus, PLC-Rockwell, PLC-Siemens, ...)
    ↓
One unified historian ingest engine
    ↓  (rate control, deadband, quality filter — applied once)
One optimized storage pipeline (BINARY COPY → TimescaleDB)
```
- Each source adapter produces `RawSample` objects.
- One shared `BatcherService` + `DbWriterService` handles all writes.
- Per-source isolation: one bad PLC **must never** affect OPC writes or other PLC writes.
- `PlcHistorianIngestService` long-term should be refactored to feed the shared `BatcherService`, not write its own COPY.

### 3. Spool Rules
- Hard maximum spool disk size configured in `appsettings.json` → `Historian.Spool.MaxSpoolSizeMB`.
- When spool exceeds limit: **drop oldest files first**, log warning, never crash.
- Spool replay must be **throttled** — never flood DB after recovery. Max replay rate: configurable (`Spool.ReplayBatchSize`, `Spool.ReplayIntervalMs`).
- Spool is last-resort only. If DB is healthy: **no spool files should exist**.

### 4. Graceful Degradation — What Drops First
| Priority | What | Behaviour |
|----------|------|-----------|
| NEVER drops | Per-source circuit isolation | One source failure must not block others |
| NEVER drops | Latest-value cache | Always keep most recent value per tag in RAM |
| Last resort | DB writes | Spool to disk, replay on recovery |
| Drops first | Parquet/analytics writes | Non-critical path — skip on resource pressure |
| Drops first | Spool replay | Throttled, paused during DB stress |
- **Latest-value philosophy**: never retain unbounded raw samples in RAM. Keep only the most recent value per tag.

### 5. Quality Codes
- Current: string codes `"G"` / `"B"` / `"U"` written to DB — keep for DB compatibility.
- Internal: replace string quality comparisons with internal enum `TagQuality { Good, Bad, Uncertain, Stale }` when refactoring.
- Stale detection: if a tag has not been updated for `StaleTagThresholdSeconds` (configurable, default 30s) → internally mark as `Stale` → write quality `"U"` to DB.

### 6. Watchdog Requirements
- Every polling loop (OPC, each PLC) must update a heartbeat timestamp on each cycle.
- A watchdog background task checks all heartbeats every 10s.
- If any loop has not updated in `WatchdogTimeoutMs` (default 15000ms) → log `[WATCHDOG] FROZEN: {sourceName}` at Error level → attempt loop restart.
- DO NOT silently let acquisition threads die.

### 7. Metrics — Per-Source, Always
Every source must expose independently:
- `writes_per_sec` — successful DB rows written
- `skipped_per_sec` — filtered by rate control or deadband
- `copy_duration_ms` — last COPY operation time
- `queue_depth` — pending samples in batcher channel
- `spool_file_count` — current spool backlog
- `db_latency_ms` — round-trip from sample ready to DB ack
- `last_write_time` — UTC timestamp of last successful write

### 8. Config Validation at Startup
- On startup, before any service starts polling, validate:
  - DB connection reachable
  - `historian_raw.historian_timeseries` table exists
  - `historian_meta.tag_master` table exists and has enabled rows
  - Spool directory exists and is writable
  - All required config keys present in `appsettings.json`
- On any validation failure: log `[STARTUP-CHECK] FAILED: {reason}` at Fatal level, **do not crash** — continue with degraded mode and surface in health endpoint.

### 9. Health Dashboard
The `/health` or `/historian/dashboard` endpoint must show in real time:
- OPC connected (Y/N) + last tag update time
- Per-PLC: connected (Y/N) + last tag update time
- DB healthy (Y/N) + last successful write time
- Spool active (Y/N) + spool file count + disk usage MB
- Per-source: writes/sec, skipped/sec, queue depth
- Watchdog status per loop

### 10. Source Isolation Rule
- Each acquisition source runs in its own isolated loop with its own error boundary.
- An unhandled exception in PLC-1 polling must not propagate to PLC-2 or OPC polling.
- Use `try/catch` at the top of every polling loop iteration — log and continue, never rethrow from a polling loop.

---

Request clarifications if any pattern above is ambiguous or missing.

---
Request clarifications if any pattern above is ambiguous or missing.
