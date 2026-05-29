# Cereveate HMI — Alarm System Complete Reference
**Last Updated:** 2026-05-28  
**Session Author:** GitHub Copilot  
**Status:** Production — AlarmEvaluationService RUNNING ✅

---

## 1. Architecture Overview

```
OPC DA Server (COM)
      │  500ms poll
      ▼
LiveTagCacheService         PlcWorker (Rockwell EtherNet/IP)
      │                            │
      ▼                            ▼
TagValuesPoolService    PlcTagValuesPoolService
      │                            │
      └─────────┬─────────────────┘
                ▼ 1000ms eval
        AlarmEvaluationService  (BackgroundService - Phase 1 orchestrator)
                │
                ├──► AlarmSetpointCacheService  (reads tag_master every 60s)
                ├──► AlarmDelayTracker           (onset delay / anti-spike)
                ├──► AlarmStateManager           (sole DB writer — historian_events + alarm_active)
                ├──► AlarmReconciliationService  (startup stale-alarm cleanup)
                └──► MqttPublisher               (fire-and-forget MQTT on each transition)
                         │
                         ▼
                  historian_raw.historian_events  (append-only journal — NEVER mutated)
                  historian_raw.alarm_active      (runtime operational state)
                  historian_raw.alarm_audit_trail (operator action notes — Python/Flask owns)

Flask HMI (Python :8090)
  ├── GET  /api/alarms/active   → reads alarm_active (polls C# every 5s)
  ├── GET  /api/alarms/history  → reads historian_events (paginated)
  ├── POST /api/alarms/{key}/ack   → proxies to C# :5001
  ├── POST /api/alarms/{key}/clear → proxies to C# :5001
  └── alarm_audit_trail           → Flask writes directly (ACK reason/notes)

React Frontend (Vite, served by Flask)
  ├── AlarmPanel.tsx      — active alarms, polls /api/alarms/active every 5s
  └── AlarmHistoryModal.tsx — history, reads /api/alarms/history paginated
```

---

## 2. Database Tables

### `historian_raw.historian_events` — Immutable Journal
| Column | Type | Description |
|--------|------|-------------|
| event_id | bigserial PK | Auto-increment |
| time | timestamptz | Event timestamp (UTC) |
| tag_id | text | OPC tag identifier |
| event_type | text | `ALARM_RAISED_H`, `ALARM_RAISED_HH`, `ALARM_RAISED_L`, `ALARM_RAISED_LL`, `ALARM_RTN`, `ALARM_ACK`, `ALARM_CLEARED` |
| alarm_state | text | `ACTIVE_UNACK`, `ACTIVE_ACK`, `RTN_UNACK`, `CLEARED` |
| alarm_level | text | `High`, `HighHigh`, `Low`, `LowLow` |
| alarm_actual_value | float8 | **PV at event time** — filled for ALL event types including ACK/CLEARED (fixed 2026-05-28) |
| alarm_setpoint | float8 | **Setpoint at event time** — filled for ALL event types (fixed 2026-05-28) |
| acknowledged_by | text | Operator name — filled for ALARM_ACK/ALARM_CLEARED rows (fixed 2026-05-28) |
| acknowledged_at | timestamptz | ACK timestamp — filled for ALARM_ACK rows (fixed 2026-05-28) |
| cleared_by | text | Operator name — filled for ALARM_CLEARED rows (fixed 2026-05-28) |
| cleared_at | timestamptz | Clear timestamp — filled for ALARM_CLEARED rows (fixed 2026-05-28) |
| occurrence_id | uuid | Groups all events for one alarm occurrence |
| instance_seq | int | Monotonic raise counter per tag+level pair |
| transition_seq | bigint | Global monotonic seq (from `alarm_transition_seq`) — used by HMI for gap detection |
| message | text | Human-readable C# message e.g. `"PY1105G:High acknowledged by Sanjeev Saxena"` |
| severity | int | 1-5 |
| alarm_priority | int | 1-5 |

> ⚠️ **NEVER UPDATE** rows in this table. It is append-only by design.

### `historian_raw.alarm_active` — Runtime State
| Column | Type | Description |
|--------|------|-------------|
| alarm_key | text PK | `"{tag_id}:{level}"` e.g. `"PY1105G:High"` |
| tag_id | text | |
| level | text | `High`, `HighHigh`, `Low`, `LowLow` |
| alarm_state | text | `ACTIVE_UNACK`, `ACTIVE_ACK`, `RTN_UNACK` (rows deleted on CLEARED) |
| raised_value | float8 | PV when alarm was first raised — **static, trip-time value** |
| setpoint_value | float8 | Setpoint at raise time |
| raised_at | timestamptz | |
| ack_at | timestamptz | Null until ACK'd |
| ack_by | text | Null until ACK'd |
| rtn_at | timestamptz | Null until RTN |
| current_event_id | bigint | FK → historian_events.event_id of RAISE event |
| occurrence_id | uuid | |
| instance_seq | int | |
| transition_seq | bigint | Last transition sequence |
| priority | int | |
| updated_at | timestamptz | |

> **Row lifecycle:** Created on RAISE → updated on RTN/ACK → **deleted** on CLEARED.

### `historian_raw.alarm_audit_trail` — Operator Action Notes
Owned exclusively by **Flask HMI Python**. Written when operator ACKs/CLEARs with reason/notes via the UI.
| Column | Type | Description |
|--------|------|-------------|
| audit_id | bigserial PK | |
| event_id | bigint | FK → historian_events.event_id |
| tag_id | text | |
| action_type | text | `ACKNOWLEDGED`, `CLEARED`, `SUPPRESSED`, `UNSUPPRESSED` |
| action_timestamp | timestamptz | |
| performed_by | text | Operator name |
| performed_by_display_name | text | |
| previous_state | text | |
| new_state | text | |
| alarm_actual_value | float8 | |
| alarm_setpoint | float8 | |
| action_reason | text | Free text reason |
| action_notes | text | Free text notes |
| metadata | jsonb | Contains `alarm_key`, `suppress_until`, etc. |

---

## 3. C# Backend Services — AlarmEvaluation System

### Location
`d:\CereveateHMI_Production\CSharpBackend\Services\AlarmEvaluation\`

### 3.1 `AlarmEvaluationService.cs` — Main Orchestrator
**Type:** `BackgroundService` (singleton, hosted)  
**Loop interval:** `AlarmEvaluation:EvaluationIntervalMs` (default 1000ms)  
**Key methods:**
- `ExecuteAsync(ct)` — main loop: calls `EvaluateCycleAsync()` every interval
- `EvaluateCycleAsync()` — fetches all tag values from both pools, evaluates each tag+level
- `EvaluateTagAsync(tagId, entry, setpoint)` — checks suppression → onset delay → delegates to `AlarmStateManager`
- `IsInAlarmZone(value, setpoint, level)` — returns true if value crosses the given level's limit
- `IsGoodQuality(quality)` — only `"Good"` and `"Good_"` prefix qualities are evaluated
- `GetDiagnostics()` — returns cycle count, last eval time, etc.
- **Startup sequence:**
  1. `UpdateDbSchemaAsync()` — ensures sequences exist
  2. `_setpointCache.InitializeAsync()` — loads limits from tag_master
  3. `_reconciliation.ReconcileAsync()` — clears stale alarm_active rows
  4. Subscribes `_stateManager.TransitionOccurred` → MQTT publish

**Critical rule:** Line 179 — skips stale or bad-quality tags:
```csharp
if (entry.IsStale || !IsGoodQuality(entry.Quality)) continue;
```

### 3.2 `AlarmStateManager.cs` — Sole DB Authority
**Type:** Singleton  
**Responsibility:** Only class that writes to `historian_events` and `alarm_active`.  
**In-memory state:** `ConcurrentDictionary<string, AlarmRuntimeState>` keyed by `alarm_key`  
**Per-key locking:** `SemaphoreSlim` per alarm key prevents race conditions  

**Key methods:**

| Method | Signature | Action |
|--------|-----------|--------|
| `RaiseAsync` | `(tagId, level, value, setpoint, alarmKey, ct)` | NONE→ACTIVE_UNACK. Inserts RAISE row + upserts alarm_active |
| `MarkRtnAsync` | `(alarmKey, value, ct)` | ACTIVE_UNACK→RTN_UNACK or ACTIVE_ACK→CLEARED. Updates alarm_active |
| `AcknowledgeAsync` | `(alarmKey, operatorName, ct, notes?)` | ACTIVE_UNACK→ACTIVE_ACK or RTN_UNACK→CLEARED. Inserts ACK row |
| `ClearAsync` | `(alarmKey, operatorName, ct, reason?, notes?, forceAck?)` | ACTIVE_ACK→CLEARED. Inserts CLEAR row, deletes alarm_active |
| `LoadRuntimeStateAsync` | `(ct)` | On startup: loads alarm_active into memory |
| `GetRuntimeState` | `()` | Returns snapshot of in-memory state dict |
| `TransitionOccurred` | `event` | Emits `AlarmTransitionEvent` after each successful DB write |

**ISA-18.2 state machine:**
```
              ┌──────────────────────────────────────────────┐
              │                                              │
  Value OK ───┤  NONE                                        │
              │   │                                          │
              │   │ value crosses limit                      │
              │   ▼                                          │
              │  ACTIVE_UNACK ──── value returns ───► RTN_UNACK ──── operator ACK ───► CLEARED (deleted)
              │   │                                          │
              │   │ operator ACK                             │
              │   ▼                                          │
              │  ACTIVE_ACK ──── value returns + ACK ───────► CLEARED (deleted)
              │   │
              │   │ operator CLEAR
              │   ▼
              │  CLEARED (row deleted from alarm_active)
              └──────────────────────────────────────────────┘
```

**Circuit breaker:** After 3 consecutive DB failures, stops writing for `CircuitCooldownSeconds` (default 30s).

### 3.3 `AlarmSetpointCacheService.cs` — Setpoint Cache
**Type:** Singleton  
**Source:** `historian_meta.tag_master WHERE alarm_enabled = true`  
**Refresh:** Every `AlarmEvaluation:SetpointCacheRefreshIntervalSeconds` (default 60s)  
**Key method:** `GetSetpoint(tagId)` → returns `AlarmSetpoint?`  
**DB columns read:**  
`alarm_hh_limit`, `alarm_h_limit`, `alarm_l_limit`, `alarm_ll_limit`, `alarm_deadband`, `alarm_priority`, `alarm_onset_delay_s`, `interlock_type`, `is_trip_initiator`, `causes_trip_on_tag`, `trip_category`

**Current counts (2026-05-28):** 116 tags with `alarm_enabled=true`, 116 with H limits, 113 with HH limits.

### 3.4 `AlarmDelayTracker.cs` — Onset Delay / Anti-Spike
**Type:** Singleton  
**Purpose:** Prevents false alarms from short-lived spikes.  
**In-memory:** `ConcurrentDictionary<string, PendingOnset>` keyed by `alarm_key`  
**Key method:** `TryStartOrCheck(alarmKey, level, value, onsetDelaySeconds)`  
- `onsetDelaySeconds == 0` → returns `true` immediately (raise now)
- First call with delay > 0 → starts timer, returns `false`
- Subsequent calls → checks elapsed time; returns `true` when expired
- `CancelOnset(alarmKey)` → called when value returns to normal before timer expires

### 3.5 `AlarmReconciliationService.cs` — Startup Cleanup
**Type:** Singleton  
**Purpose:** On service startup, reconciles `alarm_active` against current tag values.  
**Action:** Clears stale `alarm_active` rows for alarms that no longer correspond to active conditions.  
**Previous session:** Cleared 222 stale alarm records on 2026-05-27.

### 3.6 `AlarmSuppressionEngine.cs` — Static Suppression Helper
**Type:** `static class`  
**Key method:** `IsSuppressed(alarmKey, auditTrail)` — checks if an alarm key has an active suppression record in `alarm_audit_trail`.

### 3.7 `InterlockEvaluationService.cs` — PARKED
**Status:** ⛔ **Commented out in Program.cs** — not in current development scope.  
**Writes to:** `historian_raw.interlock_state_tracking` only — **zero impact on alarms**.

---

## 4. Models

### `AlarmRuntimeState`
```csharp
// In-memory state, one per active alarm, keyed by alarm_key
string    AlarmKey        // "{tag_id}:{level}"
string    TagId
AlarmLevel Level          // None=0, Low=1, LowLow=2, High=3, HighHigh=4
AlarmState4 State         // ActiveUnack=1, ActiveAck=2, RtnUnack=3
Guid      OccurrenceId
int       InstanceSeq
long?     CurrentEventId
DateTimeOffset RaisedAt
double?   RaisedValue     // PV at trip — used for ACK/CLEAR row values
double?   SetpointValue   // Setpoint at trip
DateTimeOffset? AckAt
string?   AckBy
DateTimeOffset? RtnAt
long      TransitionSeq
```

### `AlarmSetpoint`
```csharp
string  TagId
double? HhLimit, HLimit, LLimit, LlLimit
double  AlarmDeadband
int     AlarmPriority
string? InterlockType
bool    IsTripInitiator
string? CausesTripOnTag
string? TripCategory
int     OnsetDelaySeconds
```

### `AlarmTransitionEvent` (emitted by AlarmStateManager after each DB write)
```csharp
string         AlarmKey, TagId
AlarmLevel     Level
AlarmState4    ToState
Guid           OccurrenceId
int            InstanceSeq
long           EventId, TransitionSeq
DateTimeOffset Timestamp
double?        Value, SetpointValue
string?        Operator
string         EventType  // "ALARM_RAISED", "ALARM_ACKNOWLEDGED", "ALARM_RTN", "ALARM_CLEARED"
```

---

## 5. DI Registration in `Program.cs`

```csharp
// ===== ALARM EVALUATION SYSTEM =====
builder.Services.AddSingleton(sp => {
    var cfg = new AlarmEvaluationConfig();
    builder.Configuration.GetSection(AlarmEvaluationConfig.SectionName).Bind(cfg);
    return cfg;
});
builder.Services.AddSingleton(sp => {
    var cfg = new OpcMqttTransportConfig();
    builder.Configuration.GetSection("OpcMqttTransport").Bind(cfg);
    return cfg;
});
builder.Services.AddSingleton<AlarmSetpointCacheService>();
builder.Services.AddSingleton<AlarmStateManager>();
builder.Services.AddSingleton<AlarmDelayTracker>();
builder.Services.AddSingleton<AlarmReconciliationService>();
builder.Services.AddSingleton<AlarmEvaluationService>();
builder.Services.AddHostedService(sp => sp.GetRequiredService<AlarmEvaluationService>());
// InterlockEvaluationService PARKED — not in current development scope
// builder.Services.AddHostedService<InterlockEvaluationService>();
// ===== END ALARM EVALUATION SYSTEM =====
```

---

## 6. C# REST API — `AlarmsController.cs`

Base path: `/api/alarms`  
Auth: `[AllowAnonymous]` (Flask handles auth before proxying)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/alarms/active` | GET | All rows from alarm_active ordered by state priority |
| `/api/alarms/history` | GET | historian_events paginated, params: `limit`, `tagId`, `fromDate`, `toDate` |
| `/api/alarms/{key}/ack` | POST | Body: `{operator, notes}` → calls `AlarmStateManager.AcknowledgeAsync` |
| `/api/alarms/{key}/clear` | POST | Body: `{operator, reason, notes, forceAck}` → calls `AlarmStateManager.ClearAsync` |
| `/api/alarms/audit/{id}` | GET | Audit trail for a specific alarm event_id |

**Active alarms response fields:**
```json
{
  "alarm_key": "PY1105G:High",
  "tag_id": "PY1105G",
  "level": "High",
  "alarm_state": "ACTIVE_UNACK",
  "raised_at": "2026-05-28T05:21:10Z",
  "raised_value": 0.52486,
  "setpoint_value": 0.4,
  "ack_at": null,
  "ack_by": null,
  "rtn_at": null,
  "priority": 3,
  "occurrence_id": "uuid...",
  "instance_seq": 1
}
```

---

## 7. Flask HMI Python — `alarm_controller.py`

Location: `d:\CereveateHMI_Production\HMI\controllers\alarm_controller.py`  
C# backend base: `http://localhost:5001` (constant `_OPC_BASE`)

### Key Endpoints

| Route | Function | Description |
|-------|----------|-------------|
| `/api/alarms/active` | `get_active_alarms()` | Reads `alarm_active` + joins `tag_master`, `historian_events` |
| `/api/alarms/history` | `get_alarm_history()` | Paginated `historian_events` with audit trail JOINs |
| `/api/alarms/<key>/ack` | `acknowledge_alarm()` | Proxies to C# :5001, then writes to audit_trail |
| `/api/alarms/<key>/clear` | `clear_alarm()` | Proxies to C# :5001, then writes to audit_trail |
| `/api/alarms/suppressed` | `get_suppressed_alarms()` | Active suppressions from audit_trail |
| `/api/alarms/<key>/suppress` | `suppress_alarm()` | Writes SUPPRESSED to audit_trail |
| `/api/alarms/<key>/unsuppress` | `unsuppress_alarm()` | Writes UNSUPPRESSED to audit_trail |

### `get_active_alarms()` Query
- Source: `historian_raw.alarm_active aa`
- Joins: `historian_meta.tag_master tm`, `historian_raw.historian_events he`
- Returns `alarm_actual_value = aa.raised_value` (static trip-time value)
- Excludes suppressed alarms via `alarm_audit_trail` NOT EXISTS check
- States returned: `ACTIVE_UNACK`, `ACTIVE_ACK`, `RTN_UNACK`
- Extra computed fields: `occurrence_count`, `recent_raise_times`, `last_cleared_at/by`

### `get_alarm_history()` Query
- Source: `historian_raw.historian_events he`
- LEFT JOIN LATERAL: `ack_at` (from audit_trail), `clr_at` (from audit_trail)
- Falls back to `he.acknowledged_by` / `he.cleared_by` columns if audit_trail empty
- **Fallback parser** (added 2026-05-28): extracts operator from `message` field for old rows
- `alarm_actual_value` uses `COALESCE(he.alarm_actual_value, orig_event.alarm_actual_value)` — falls back to originating RAISE event

---

## 8. Frontend — `AlarmPanel.tsx`

Location: `d:\CereveateHMI_Production\HMI\apex-hmi\src\components\hmi\AlarmPanel.tsx`

### State
```typescript
alarms: Alarm[]              // active alarms from /api/alarms/active
tagValues: Record<string, number | null>  // live tag values from /api/tags/latest (added 2026-05-28)
suppressedAlarms: SuppressedAlarm[]
pendingOps: Set<number>      // per-alarm in-flight ops
isDegraded: boolean          // circuit breaker
```

### Data Fetching
- `fetchSnapshot()` — polls every 5s:
  1. `GET /api/alarms/active` → updates `alarms`
  2. `GET /api/alarms/suppressed` → updates `suppressedAlarms`
  3. `GET /api/tags/latest` → updates `tagValues` map `{ tag_id → current_value }` (added 2026-05-28)
- Socket.IO live MQTT events for instant new-alarm push (delta only)
- `mergeDbWithTemporaryMqtt()` — merges DB snapshot with in-flight MQTT alarms

### `Alarm` Interface Fields
```typescript
id: number               // event_id
alarm_key?: string       // "tag_id:level"
tag_id: string
alarm_level?: string     // "High", "HighHigh", "Low", "LowLow"
alarm_state: "ACTIVE_UNACK" | "ACTIVE_ACK" | "RTN_UNACK" | "CLEARED" | "SUPPRESSED" | null
alarm_priority: number   // 1=Low … 5=Critical
alarm_setpoint?: number
alarm_actual_value?: number  // trip-time PV (static)
raised_at: string
acknowledged_by?: string
acknowledged_at?: string
```

### PV Display on Alarm Card (updated 2026-05-28)
- Shows **live PV** (`tagValues[alarm.tag_id]`) when available from `/api/tags/latest`
- Label: **`PV:`** (live) or **`PV@Trip:`** (static fallback)
- Tooltip on live shows trip value for reference: `"Live PV (trip value: 0.52)"`

---

## 9. Fixes Applied in Session 2026-05-28

### ✅ FIX 1 — AlarmEvaluationService Never Started (ROOT CAUSE of zero alarms since May 22)
**File:** `CSharpBackend/Program.cs`  
**Problem:** `AlarmEvaluationService` and all 5 dependencies were compiled but **never registered** in DI. The evaluation loop never started — zero alarm events for 6 days.  
**Fix:** Added full alarm evaluation system DI registration block (see Section 5).  
**Verified:** 244 new alarm events + 162 active alarms written within 20 seconds of restart.

### ✅ FIX 2 — ACK/CLEARED Rows Missing Value/SP in History
**File:** `CSharpBackend/Services/AlarmEvaluation/Services/AlarmStateManager.cs`  
**Problem:** `AcknowledgeAsync()` and `ClearAsync()` inserted into `historian_events` without `alarm_actual_value` and `alarm_setpoint` columns → showed "–" in history for all ACK/CLEARED rows.  
**Fix:** Added `alarm_actual_value = state.RaisedValue` and `alarm_setpoint = state.SetpointValue` to both INSERT statements.  
**Code location:** Lines ~480 (ACK) and ~690 (CLEAR) in AlarmStateManager.cs

### ✅ FIX 3 — ACK/CLEARED Rows Missing Operator Name in History
**File:** `CSharpBackend/Services/AlarmEvaluation/Services/AlarmStateManager.cs`  
**Problem:** `acknowledged_by`, `acknowledged_at`, `cleared_by`, `cleared_at` columns in `historian_events` were never populated — columns always NULL. History showed "Not ACK'd" for all rows.  
**Fix:**  
- ACK INSERT: added `acknowledged_by = @ackBy` (`operatorName`) and `acknowledged_at = @ackAt2`
- CLEAR INSERT: added `cleared_by = @clearedBy` (`operatorName`) and `cleared_at = @clearedAt2`

**File:** `HMI/controllers/alarm_controller.py`  
**Additional fix:** Added `_extract_operator_from_message()` fallback parser for **old rows** where columns are still NULL — extracts operator name from the C# `message` field (e.g. `"PY1105G:High acknowledged by Sanjeev Saxena"`).

### ✅ FIX 4 — Active Alarm Cards Showing Stale Trip-Time PV (Never Updated)
**File:** `HMI/apex-hmi/src/components/hmi/AlarmPanel.tsx`  
**Problem:** `alarm_actual_value` in `alarm_active.raised_value` is set once at trip time and never updated. Cards showed the same frozen value for 20+ minutes even as the oscillating process value changed.  
**Fix:** `fetchSnapshot()` now also fetches `/api/tags/latest` and stores a `tagValues` map. The card renders `tagValues[tag_id]` (live) with label `PV:` instead of the frozen `alarm_actual_value` with label `PV@Trip:`. Falls back to trip value if live value unavailable.

### ✅ FIX 5 — InterlockEvaluationService Parked
**File:** `CSharpBackend/Program.cs`  
**Action:** `InterlockEvaluationService` registration commented out per business decision — not in current development scope.  
**Impact:** Zero — interlock service only writes to `interlock_state_tracking` table, never touches alarms.

---

## 10. Configuration — `appsettings.json`

```json
"AlarmEvaluation": {
  "Enabled": true,
  "EvaluationIntervalMs": 1000,
  "SetpointCacheRefreshIntervalSeconds": 60,
  "MaxConcurrentEvaluations": 50,
  "CircuitBreakerThreshold": 3,
  "CircuitCooldownSeconds": 30
},
"Historian": {
  "Database": {
    "ConnectionString": "Host=localhost;Port=5432;Database=Automation_DB;Username=cereveate;Password=cereveate@222",
    "CommandTimeout": 30
  }
}
```

---

## 11. Build & Deploy Reference

### C# Backend
```powershell
# Stop running process
Stop-Process -Name "OpcDaWebBrowser" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# Build + publish
cd d:\CereveateHMI_Production\CSharpBackend
dotnet publish -c Release /p:Platform=x86 -o bin\Release\net8.0\win-x86\publish

# Start
cd bin\Release\net8.0\win-x86\publish
Start-Process -FilePath ".\OpcDaWebBrowser.exe" -WindowStyle Minimized
```

### HMI Frontend (React)
```powershell
cd d:\CereveateHMI_Production\HMI\apex-hmi
npm run build
# Output goes to dist/ — Flask serves it
```

### Flask HMI (Python)
```powershell
cd d:\CereveateHMI_Production\HMI
python app.py  # or restart via START_ALL.bat
```

### Full Restart
```bat
d:\CereveateHMI_Production\START_ALL.bat
```

---

## 12. Pending / Known Issues

| # | Issue | Status | Notes |
|---|-------|--------|-------|
| 1 | Live PV on active alarm cards | ✅ Fixed 2026-05-28 | Frontend fetches `/api/tags/latest` alongside active alarms |
| 2 | Operator name in ACK/CLEAR history rows | ✅ Fixed 2026-05-28 | C# now writes `acknowledged_by`/`cleared_by` columns; Python falls back to message parser for old rows |
| 3 | Value/SP blank in history for ACK/CLEARED | ✅ Fixed 2026-05-28 | C# now writes `alarm_actual_value`/`alarm_setpoint` for ACK and CLEAR events |
| 4 | Frontend build not run after AlarmPanel.tsx changes | ⏳ Pending | Need to run `npm run build` in `HMI/apex-hmi` then restart Flask |
| 5 | InterlockEvaluationService | ⛔ Parked | Registered when ready to develop |

---

## 13. Key File Locations Quick Reference

| Component | File |
|-----------|------|
| DI Registration | `CSharpBackend/Program.cs` |
| Main eval loop | `CSharpBackend/Services/AlarmEvaluation/Services/AlarmEvaluationService.cs` |
| DB writer | `CSharpBackend/Services/AlarmEvaluation/Services/AlarmStateManager.cs` |
| Setpoint cache | `CSharpBackend/Services/AlarmEvaluation/Services/AlarmSetpointCacheService.cs` |
| Onset delay | `CSharpBackend/Services/AlarmEvaluation/Services/AlarmDelayTracker.cs` |
| Startup reconcile | `CSharpBackend/Services/AlarmEvaluation/Services/AlarmReconciliationService.cs` |
| Suppression check | `CSharpBackend/Services/AlarmEvaluation/Services/AlarmSuppressionEngine.cs` |
| REST API (C#) | `CSharpBackend/Controllers/AlarmsController.cs` |
| Python alarms API | `HMI/controllers/alarm_controller.py` |
| Active alarm panel | `HMI/apex-hmi/src/components/hmi/AlarmPanel.tsx` |
| Alarm history modal | `HMI/apex-hmi/src/components/hmi/AlarmHistoryModal.tsx` |
| Config | `CSharpBackend/appsettings.json` |
| Published binary | `CSharpBackend/bin/Release/net8.0/win-x86/publish/OpcDaWebBrowser.exe` |
