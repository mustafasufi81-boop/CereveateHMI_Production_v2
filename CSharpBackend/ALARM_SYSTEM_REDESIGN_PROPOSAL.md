# Alarm System Redesign Proposal — v5.1
## Based on ISA-18.2 / EEMUA 191 — Practical Industrial Architecture

---

## 1. Core Philosophy

```
LIVE OPC VALUES
      ↓
AlarmEvaluationEngine
      ↓
AlarmStateManager
      ↓
Database (visible operator state)
      ↓
HMI/API
```

MQTT is:
- notification transport only
- NOT source-of-truth
- NOT runtime authority

HMI always reads alarm state from DB.

---

## 2. Main Problems Solved

| Problem | Solution |
|---------|----------|
| Startup stale ACTIVE rows block tags forever | Live-value reconciliation |
| Alarm chatter near threshold | Asymmetric hysteresis |
| Alarm flooding | HH→H and LL→L suppression |
| DB overload | Write only on transition |
| Restart corruption | Runtime rebuild from live OPC |
| Race conditions | Per-tag serialization lock |
| Ambiguous alarm history | `occurrence_id` per instance |
| MQTT dependency | DB remains operator truth |

---

## 3. Architecture Overview

```
OPC / PLC
    ↓
TagValuesPoolService
    ↓
AlarmEvaluationService
    ↓
AlarmStateManager
    ↓
PostgreSQL
 ├── alarm_active
 └── historian_events
    ↓
HMI/API

Optional:
AlarmStateManager → MQTT Publisher
```

---

## 4. Runtime Rules

### Core Rules
1. Pool update triggers evaluation.
2. No state change → **NO DB write**.
3. DB is visible runtime state.
4. MQTT failure never affects alarm correctness.
5. HMI reads DB periodically.
6. Alarm engine owns runtime state.

---

## 5. Alarm Lifecycle (Phase 1)

Only 4 states.

```
NORMAL
   ↓
ACTIVE_UNACK
   ↓
ACTIVE_ACK
   ↓
RTN_UNACK
   ↓
CLEARED
```

**Valid paths:**

| From | To | Trigger |
|------|----|---------|
| *(new)* | ACTIVE_UNACK | raise |
| ACTIVE_UNACK | ACTIVE_ACK | operator ACK |
| ACTIVE_UNACK | RTN_UNACK | value RTN |
| ACTIVE_ACK | RTN_UNACK | value RTN |
| RTN_UNACK | CLEARED | operator ACK |
| RTN_UNACK | ACTIVE_UNACK | re-raise (new occurrence_id) |
| CLEARED | ACTIVE_UNACK | re-raise |

Invalid transitions are rejected. `AlarmStateManager.TryTransition(from, to)` throws `InvalidAlarmTransitionException` on violation.

**No additional states in Phase 1.**

**Deferred:**
- `RTN_ACK`
- `SHELVED`
- `DISABLED`
- `SUPPRESSED`

---

## 6. Startup Reconciliation

```
System Start
    ↓
Connect OPC
    ↓
Wait for first live values
    ↓
Load alarm_active rows
    ↓
Re-evaluate using LIVE values
```

- If condition **still true** → restore runtime state
- If condition **no longer true** → move to `RTN_UNACK`, do NOT restore runtime state

All `RTN_UNACK` updates are committed in a **single transaction**. MQTT is suppressed during reconciliation. One summary event is published at the end:

```json
{
  "event": "ALARM_SYSTEM_RECONCILED",
  "restored_active": 3,
  "auto_cleared_stale": 47,
  "opc_offline_kept": 2,
  "timestamp": "2026-05-08T10:00:00Z"
}
```

This completely removes:
- stale alarm resurrection
- permanent tag blocking
- fake ACTIVE states

No time-based cleanup required.

---

## 7. Alarm Levels

Evaluated independently.

| Level | Condition |
|-------|-----------|
| HH | Very High |
| H  | High |
| L  | Low |
| LL | Very Low |

---

## 8. Suppression Logic

| Active | Suppresses |
|--------|-----------|
| HH | H (same tag) |
| LL | L (same tag) |

**Phase 1 behavior**: suppressed level is not raised, not written to DB, not published to MQTT. Silently blocked in evaluation engine.

When HH clears — if H condition is still valid → H raises immediately as `ACTIVE_UNACK`.

**Phase 2**: `SUPPRESSED` DB state added so suppressed alarms are historized.

---

## 9. Asymmetric Hysteresis

Prevents chatter. Raise and clear thresholds are independent.

| Alarm | Raise | Clear |
|-------|-------|-------|
| H  | `value >= h_limit` | `value < h_limit − deadband` |
| HH | `value >= hh_limit` | `value < hh_limit − deadband` |
| L  | `value <= l_limit` | `value > l_limit + deadband` |
| LL | `value <= ll_limit` | `value > ll_limit + deadband` |

**Example** — H with `h_limit = 90`, `deadband = 2`:
- Raises at **≥ 90**
- Does NOT clear until **< 88**
- Value bouncing 89–91 → zero chatter, zero DB writes

Deadband stored in `historian_meta.tag_master.alarm_deadband` (existing column).

---

## 10. Onset Delay (Phase 1)

Configured per tag via `historian_meta.tag_master.alarm_onset_delay_s` (default `0` = immediate).

```
value crosses threshold
↓
AlarmDelayTracker starts per-tag timer
↓
still valid at expiry?
↓
raise ACTIVE_UNACK
```

If value returns to normal before timer expires:
- cancel timer
- no alarm raised

Purpose: spike filtering, anti-noise protection.

**`AlarmDelayTracker.cs`** is a Phase 1 service — onset delay is core evaluation behavior.

---

## 11. OPC Quality Gating

| Quality | Action |
|---------|--------|
| `Good` | Evaluate normally — raise / RTN as normal |
| `Uncertain` | Block raise and RTN; keep current state if active |
| `Bad` | Block raise and RTN; keep current state if active |
| `Stale` | Same as Bad |

Bad quality **NEVER**:
- raises false alarms
- clears active alarms

Quality is read from `TagValueCacheEntry.Quality` — existing field, no changes needed.

---

## 12. Communication Alarms

| Event | Meaning | Priority |
|-------|---------|----------|
| `COMM_OPC_DISCONNECTED` | OPC server offline | 2 (High) |
| `COMM_OPC_RECONNECTED` | OPC restored | 4 (Info) |
| `COMM_TAG_STALE` | Tag stopped updating | 3 (Medium) |
| `COMM_TAG_QUALITY_BAD` | OPC quality = Bad | 3 (Medium) |

Communication alarms are:
- written to `historian_events`
- published to `opc/alarms/comm`
- visible to operators

During disconnect: all active process alarms **keep their current state** (no auto-clear).

> **`AlarmCommMonitor.cs`** implementing these alarms is Phase 2. The `COMM_TAG_QUALITY_BAD` event type is defined now (referenced in section 11) so it is not invented later.

---

## 13. Runtime State Authority

`AlarmStateManager` = **ONLY writer**.

Only this service may:
- modify `_runtimeStates` (memory)
- write `alarm_active` (DB)
- insert `historian_events`
- publish MQTT

HMI/API **never** writes DB directly. ACK endpoint calls `AlarmStateManager.AcknowledgeAsync()`.

DB write happens inside the per-tag lock scope, after memory is updated. If DB write fails: log the error, leave memory state as-is, retry next evaluation cycle. Full rollback is not required — the next successful write will correct any transient mismatch.

---

## 14. Per-Tag Serialization

Three concurrent operations can touch the same tag simultaneously:
1. Pool update → evaluation
2. Operator ACK → HTTP request
3. Startup reconciliation

**Solution — `SemaphoreSlim` per `tag + level`:**

```csharp
private readonly ConcurrentDictionary<string, SemaphoreSlim> _tagLocks = new();

private SemaphoreSlim GetLock(string alarmKey) =>
    _tagLocks.GetOrAdd(alarmKey, _ => new SemaphoreSlim(1, 1));

await GetLock(alarmKey).WaitAsync(ct);
try { /* evaluate / ACK / reconcile */ }
finally { GetLock(alarmKey).Release(); }
```

---

## 15. No Write Unless State Changes

```
same state?
→ do nothing

new transition?
→ UPSERT alarm_active
→ INSERT historian_events
→ publish MQTT
```

Benefits: low DB load, low MQTT traffic, stable scaling.

---

## 16. Database Design

### Table 1 — `historian_raw.alarm_active`

Contains **ONLY non-cleared alarms**. Row is **DELETED** when alarm reaches `CLEARED`.

```sql
CREATE TABLE historian_raw.alarm_active (
    alarm_key        TEXT PRIMARY KEY,          -- '{tag_id}:{level}'
    tag_id           TEXT NOT NULL,
    level            TEXT NOT NULL,
    alarm_state      TEXT NOT NULL,             -- never 'CLEARED'
    current_event_id BIGINT,
    occurrence_id    UUID NOT NULL,
    instance_seq     INTEGER NOT NULL DEFAULT 1,
    raised_at        TIMESTAMPTZ NOT NULL,
    raised_value     DOUBLE PRECISION,
    setpoint_value   DOUBLE PRECISION,
    ack_at           TIMESTAMPTZ,
    ack_by           TEXT,
    rtn_at           TIMESTAMPTZ,
    priority         INTEGER,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
    -- Phase 2 adds: shelved_until, shelved_by, alarm_class
    -- Phase 3 adds: first_out, first_out_seq, first_out_group
);

CREATE INDEX idx_alarm_active_tag ON historian_raw.alarm_active(tag_id);
```

Purpose: fast HMI lookup, startup reconciliation, runtime active state.

### Table 2 — `historian_raw.historian_events`

Immutable journal. One INSERT per transition. Never updated.

```sql
-- New columns to add:
ALTER TABLE historian_raw.historian_events
    ADD COLUMN IF NOT EXISTS alarm_level       TEXT,
    ADD COLUMN IF NOT EXISTS onset_delay_ms    INTEGER,
    ADD COLUMN IF NOT EXISTS suppressed_by     TEXT,
    ADD COLUMN IF NOT EXISTS rtn_time          TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS ack_time          TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS ack_by            TEXT,
    ADD COLUMN IF NOT EXISTS occurrence_id     UUID DEFAULT gen_random_uuid(),
    ADD COLUMN IF NOT EXISTS instance_seq      INTEGER;

-- Phase 1 alarm_state constraint (4 states only):
ALTER TABLE historian_raw.historian_events
    DROP CONSTRAINT IF EXISTS historian_events_alarm_state_check,
    ADD  CONSTRAINT historian_events_alarm_state_check
         CHECK (alarm_state IS NULL OR alarm_state IN (
             'ACTIVE_UNACK','ACTIVE_ACK','RTN_UNACK','CLEARED'
             -- Phase 2: ,'RTN_ACK','SHELVED','DISABLED','SUPPRESSED'
         ));
```

Used for: history, audit, analytics, MTTR.

### `historian_meta.tag_master` — New Columns

```sql
ALTER TABLE historian_meta.tag_master
    ADD COLUMN IF NOT EXISTS alarm_onset_delay_s   INTEGER DEFAULT 0;
-- Note: alarm_deadband already exists (hysteresis clear threshold)
-- Note: alarm_priority already exists
-- Phase 2 adds: alarm_shelve_allowed, alarm_max_shelve_min, alarm_class
```

---

## 17. Alarm Identity

Every occurrence gets a unique UUID at raise time. All transitions reference the same UUID.

```
09:00 → Temperature High
        occurrence_id = abc-123, instance_seq = 47

09:02 → ACK               → same occurrence_id abc-123
09:10 → RTN               → same occurrence_id abc-123
09:10 → operator ACK      → same occurrence_id abc-123, CLEARED

14:00 → High again        → NEW occurrence_id def-456, instance_seq = 48
```

---

## 18. MQTT Strategy

MQTT is an **optional notification layer only**.

### Phase 1 Rules
- QoS 1
- Fire-and-forget
- **No retained messages**
- **No replay engine**
- **No runtime authority**

MQTT publishes only on transitions. Minimal payload:

```json
{ "alarm_key": "Random.Real4:High", "occurrence_id": "abc-123", "transition": "ACTIVE_UNACK" }
```

| Topic | Trigger | QoS | Retained |
|-------|---------|-----|----------|
| `opc/alarms/raised`  | ACTIVE_UNACK | 1 | No |
| `opc/alarms/ack`     | ACTIVE_ACK   | 1 | No |
| `opc/alarms/rtn`     | RTN_UNACK    | 1 | No |
| `opc/alarms/cleared` | CLEARED      | 1 | No |
| `opc/alarms/comm`    | COMM_*       | 1 | No |

If broker fails: alarm engine continues normally. HMI still works because HMI reads DB.

QoS 1 duplicate delivery is harmless — HMI deduplicates on `occurrence_id + transition`.

---

## 19. HMI Architecture

HMI polls DB via REST API. No MQTT dependency for correctness.

| API | Purpose |
|-----|---------|
| `GET /api/alarms/active` | All current non-cleared alarms from `alarm_active` |
| `GET /api/alarms/history` | Transition journal from `historian_events` |
| `POST /api/alarms/{key}/ack` | Acknowledge → calls `AlarmStateManager.AcknowledgeAsync()` |

HMI refresh interval: 2–5 seconds.

On reconnect: HMI calls `GET /api/alarms/active` — immediately receives full current state from DB. Zero MQTT broker dependency.

---

## 20. ACK Flow

```
Operator ACK
    ↓
POST /api/alarms/{alarm_key}/ack  { operator: "john" }
    ↓
AlarmStateManager.AcknowledgeAsync(alarmKey, operator)
    ↓
Acquire per-tag SemaphoreSlim
    ↓
Validate transition
  ACTIVE_UNACK → ACTIVE_ACK
  RTN_UNACK    → CLEARED
    ↓
Update _runtimeStates (memory)
    ↓
UPSERT alarm_active + INSERT historian_events
    ↓
[optional] MQTT publish QoS 1 fire-and-forget
    ↓
HMI re-reads GET /api/alarms/active
```

---

## 21. Timestamp Source

Use OPC server timestamp — **not** C# wall clock.

```csharp
// Correct:
var eventTime = new DateTimeOffset(entry.Timestamp, TimeSpan.Zero);

// Wrong:
var eventTime = DateTimeOffset.UtcNow;
```

Reason: accurate sequence, root-cause analysis, industrial timing consistency.

---

## 22. Scan Timing

| Layer | Interval | Notes |
|-------|----------|-------|
| OPC polling | 1000ms | `OpcPollingIntervalMs` |
| Alarm evaluation | Event-driven | Fires on pool update |
| Alarm DB write | On transition only | — |
| Historian batch flush | 5000ms | `HistorianBatchFlushMs` |
| HMI refresh | 2–5s | Client-side poll |

---

## 23. Runtime Consistency Audit

Optional verification only. Runs every 30s (`RuntimeStateRefreshIntervalSeconds`).

**NOT**: DB refreshes runtime state.

**Instead**: audit compares `_runtimeStates` (memory) against `alarm_active` (DB) and logs any mismatch for diagnostics. Re-syncs memory from DB only if silent divergence is detected (e.g. DB write failed, mid-transition crash).

Runtime memory remains **authoritative**. DB is the audit reference. This is a safety net, not a state driver.

---

## 24. Service Structure

```
Services/AlarmEvaluation/
    Services/
        AlarmEvaluationService.cs        ← REWRITE (Phase 1): event-driven orchestrator
        AlarmStateManager.cs             ← NEW (Phase 1): 4-state machine + per-tag lock
        AlarmReconciliationService.cs    ← NEW (Phase 1): startup live-value reconciliation
        AlarmSuppressionEngine.cs        ← NEW (Phase 1): HH/LL raise suppression
        AlarmDelayTracker.cs             ← NEW (Phase 1): per-tag onset delay timers
        AlarmSetpointCacheService.cs     ← EXISTS (Phase 1): add onset_delay_s field
        AlarmCommMonitor.cs              ← NEW (Phase 2): COMM_OPC_* / COMM_TAG_* alarms
        AlarmFloodDetector.cs            ← NEW (Phase 3): flood detection
    Models/
        AlarmRuntimeState.cs             ← UPDATE (Phase 1): 4-state enum, occurrence_id
        AlarmTransitionEvent.cs          ← NEW (Phase 1): typed transition event record
        AlarmLevel.cs                    ← NO CHANGE
        AlarmSetpoint.cs                 ← UPDATE (Phase 1): onset_delay_s
        AlarmFloodStatus.cs              ← NEW (Phase 3)
    Config/
        AlarmEvaluationConfig.cs         ← UPDATE (Phase 1): basic config
```

---

## 25. Phase 1 Scope

Build ONLY:

- [ ] 4-state lifecycle (`AlarmStateManager`)
- [ ] Startup reconciliation (`AlarmReconciliationService`)
- [ ] Asymmetric hysteresis (raise/clear thresholds)
- [ ] HH→H, LL→L suppression (`AlarmSuppressionEngine`)
- [ ] Onset delay (`AlarmDelayTracker`)
- [ ] OPC quality gating (Bad/Uncertain blocks raise and RTN)
- [ ] `alarm_active` table (DELETE on CLEARED)
- [ ] `historian_events` journal (INSERT per transition)
- [ ] `occurrence_id` UUID + `instance_seq`
- [ ] Per-tag `SemaphoreSlim` lock
- [ ] DB-driven HMI (REST API)
- [ ] MQTT transition notifications (QoS 1, no retained, no replay)

---

## 26. Phase 2 (Deferred)

- `AlarmCommMonitor` — COMM_OPC_* / COMM_TAG_* full implementation
- `SHELVED` state + shelving API
- `DISABLED` state for maintenance bypass
- `RTN_ACK` state distinction
- `SUPPRESSED` state written to DB (historized)
- Alarm classification model (`alarm_class` column)

---

## 27. Phase 3 (Deferred)

- `AlarmFloodDetector` — N alarms in M minutes
- First-out tracking (`first_out`, `first_out_seq`, `first_out_group`)
- KPI engine (MTTR, nuisance count, top-10 bad actors)
- Nuisance alarm analysis
- Alarm rationalization metadata

---

## 28. What Does NOT Change

- `TagValuesPoolService` — no changes
- OPC connection / DCOM layer — no changes
- Parquet logging — no changes
- Historian ingest pipeline — no changes
- MQTT transport layer — no changes
- `appsettings.json` structure — additions only, backward compatible

---

## 29. Final Core Principles

### DO
- Evaluate from LIVE values
- Rebuild runtime on startup via reconciliation
- Separate runtime state (`alarm_active`) from history (`historian_events`)
- Use asymmetric hysteresis
- Suppress HH→H, LL→L
- Write only on transitions
- Keep DB as visible operator truth

### DO NOT
- Trust stale ACTIVE rows on startup
- Use MQTT as runtime authority
- Write every scan
- Tightly couple HMI to MQTT
- Over-engineer analytics in Phase 1

---

## Blocking Fix (Before Phase 1 Start)

Three Python test rows are blocking `Random.Real4` from raising new alarms:

```sql
UPDATE historian_raw.historian_events
SET alarm_state = 'CLEARED'
WHERE event_id IN (32654, 32655, 32656);
```

Run this as the first DB step.

---

**v5.1 — C# backend complete. DB migration pending. React frontend pending (see Section 30).**

---

## 30. React Frontend — What Needs To Be Built

### 30.1 Alarm Panel (Phase 1 — Must Have)

- [ ] **Poll `GET /api/alarms/active` every 2–5 seconds** — render all rows from `alarm_active`
- [ ] **Alarm card per row** — show: `tag_id`, `level`, `alarm_state`, `raised_value`, `setpoint_value`, `raised_at`, `ack_by`
- [ ] **ISA-18.2 colour + blink rules** (non-negotiable):
  - `ACTIVE_UNACK` → red background, blinking
  - `ACTIVE_ACK` → red background, steady (no blink)
  - `RTN_UNACK` → green background, blinking
- [ ] **ACK button** on each card → `POST /api/alarms/{alarm_key}/acknowledge` via Flask
- [ ] **On ACK response `new_state = CLEARED`** → **remove card entirely** (do NOT update it)
- [ ] **On ACK response `new_state = ACTIVE_ACK`** → update card state, stop blinking
- [ ] **URL-encode `alarm_key`** in request path — `:` → `%3A` (e.g. `Random.Real4%3AHigh`)
- [ ] **Alarm count badge** in nav — shows number of `ACTIVE_UNACK` alarms

### 30.2 Alarm History Page (Phase 1 — Must Have)

- [ ] **Call `GET /api/alarms/history?limit=200`** on page load
- [ ] **Table view** — columns: `time`, `tag_id`, `alarm_level`, `alarm_state`, `event_type`, `alarm_actual_value`, `alarm_setpoint`, `occurrence_id`
- [ ] **Filter by tag** — `?tagId=xxx`
- [ ] **Filter by date range** — `?fromDate=&toDate=`

### 30.3 Race Condition Prevention (Phase 1 — Must Have)

- [ ] **Disable ACK button immediately on click** — re-enable only on API response
- [ ] **Do NOT use Socket.IO and polling simultaneously for alarm state** — pick one (polling recommended for Phase 1)
- [ ] **On reconnect** — immediately call `GET /api/alarms/active` to rebuild full state from DB
- [ ] **Track `transition_seq`** from responses — on reconnect request only events with `transition_seq > last_seen`

### 30.4 Known Open Issues (Not Phase 1 Blockers)

- [ ] **Suppression visibility** — operators cannot see why an alarm is suppressed (Phase 2 when `SUPPRESSED` state added to DB)
- [ ] **RTN_UNACK colour confusion** — green blink may confuse operators unfamiliar with ISA-18.2; add tooltip explaining "value returned to normal — acknowledge to close"
- [ ] **Bulk ACK** — no bulk ACK endpoint exists yet; each alarm must be acknowledged individually
- [ ] **Flood indicator** — no alarm flood warning in UI yet (Phase 3)

### 30.5 Backend Gaps Still To Fix (Before React Can Complete)

- [x] **Flask proxy timeout** — ✅ Already done: `_OPC_CONNECT_TIMEOUT=3s`, `_OPC_READ_TIMEOUT=5s` on all proxy calls in `alarm_controller.py`
- [x] **Health endpoint** — ✅ Added: `GET /api/alarms/health` returns `{status, active_count, unack_count, timestamp}` — React uses this to show "alarm engine offline" banner
- [ ] **Run DB migration scripts** in pgAdmin (in order):
  1. `phase1_migration.sql`
  2. `alarm_sequence_migration.sql`
  3. `create_alarm_audit_trail.sql` (stop before the view section — view already applied)
