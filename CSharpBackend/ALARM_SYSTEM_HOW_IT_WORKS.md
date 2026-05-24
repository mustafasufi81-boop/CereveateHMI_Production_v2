# Alarm System — How It Actually Works
## Implementation Reality (Phase 1 — Built & Running)
### Last updated: May 2026

This document describes the **actual implemented system** — not the proposal.
For the design spec see `ALARM_SYSTEM_REDESIGN_PROPOSAL.md`.

---

## 1. System Components

| Component | Technology | Port | Role |
|-----------|-----------|------|------|
| **C# OpcDaWebBrowser** | ASP.NET Core x86 | 5001 | Alarm state machine + DB writer |
| **Flask HMI Backend** | Python Flask | 6001 | HMI API gateway + audit trail |
| **React HMI** | React + SignalR | browser | Operator display |
| **PostgreSQL** | `Automation_DB` | 5432 | Persistent state |

**Database**: `Automation_DB` · user: `cereveate` · password: `cereveate@222`
**psql path**: `C:\Program Files\PostgreSQL\17\bin\psql.exe`
**Schema**: `historian_raw`

---

## 2. Authority Boundaries — Who Writes What

```
C# AlarmStateManager
    ├── historian_raw.alarm_active     ← SOLE WRITER (UPSERT + DELETE)
    └── historian_raw.historian_events ← SOLE WRITER (INSERT, never UPDATE)

Flask alarm_controller.py
    └── historian_raw.alarm_audit_trail ← SOLE WRITER

Flask NEVER touches alarm_active or historian_events directly.
```

**Rule**: Flask proxies all alarm mutations to C# via REST. C# is the only authority over alarm state.

---

## 3. Data Flow

```
OPC Server (Matrikon / PLC)
    ↓
TagValuesPoolService (in-memory cache, updated every 1000ms)
    ↓
AlarmEvaluationService (event-driven, fires on pool update)
    ↓
AlarmStateManager (4-state machine, per-tag SemaphoreSlim lock)
    ↓  on transition only
    ├── UPSERT historian_raw.alarm_active   (current visible state)
    ├── INSERT historian_raw.historian_events (immutable journal)
    └── fire TransitionOccurred event → optional MQTT publish

React HMI
    ↓  polls every 2-5s
Flask GET /api/alarms/active
    ↓  proxies to
C# GET /api/alarms/active
    ↓  reads
historian_raw.alarm_active
```

---

## 4. The 4 Alarm States (ISA-18.2)

```
NORMAL (no row in alarm_active)
   ↓ value crosses threshold
ACTIVE_UNACK
   ↓ operator ACK            ↓ value returns to normal
ACTIVE_ACK              RTN_UNACK
   ↓ value returns normal    ↓ operator ACK
RTN_UNACK               CLEARED (row DELETED from alarm_active)
```

### Valid Transitions

| From | To | Trigger |
|------|----|---------|
| *(none)* | `ACTIVE_UNACK` | value crosses threshold |
| `ACTIVE_UNACK` | `ACTIVE_ACK` | operator ACK |
| `ACTIVE_UNACK` | `RTN_UNACK` | value returns to normal |
| `ACTIVE_ACK` | `RTN_UNACK` | value returns to normal |
| `RTN_UNACK` | `CLEARED` | operator ACK ← **row deleted** |
| `RTN_UNACK` | `ACTIVE_UNACK` | value crosses threshold again (new `occurrence_id`) |
| `CLEARED` | `ACTIVE_UNACK` | value crosses threshold again |

Invalid transitions are rejected. `AlarmStateManager` logs Warning and returns `false`.

---

## 5. Alarm Identity

Every alarm occurrence is identified by:

| Field | Type | Meaning |
|-------|------|---------|
| `alarm_key` | `TEXT PRIMARY KEY` | `"{tag_id}:{level}"` e.g. `"Random.Real4:High"` |
| `occurrence_id` | `UUID` | Unique per raise event. New UUID on every raise. |
| `instance_seq` | `INTEGER` | Global counter — increments each raise across all alarms |

```
09:00 → raises   → occurrence_id = abc-123, instance_seq = 47
09:02 → ACK      → same abc-123
09:10 → RTN      → same abc-123
09:10 → ACK      → same abc-123, CLEARED (row deleted)

14:00 → raises again → NEW occurrence_id = def-456, instance_seq = 48
```

---

## 6. C# REST API (`AlarmsController`)

Base URL: `http://localhost:5001/api/alarms`

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/alarms/active` | All rows from `alarm_active` (non-cleared). HMI polls this. |
| `GET` | `/api/alarms/history` | `historian_events` journal. Query: `?limit=200&tagId=X&fromDate=&toDate=` |
| `POST` | `/api/alarms/{key}/ack` | Acknowledge. Body: `{"operator":"john","notes":"..."}` |
| `POST` | `/api/alarms/{key}/clear` | Manually clear from `ACTIVE_ACK`. Body: `{"operator":"john","reason":"..."}` |

### ACK Response — Two Paths

| Pre-ACK state | `event_type` returned | `new_state` returned | `alarm_active` row |
|---------------|----------------------|---------------------|--------------------|
| `ACTIVE_UNACK` | `ALARM_ACKNOWLEDGED` | `ACTIVE_ACK` | **updated** |
| `RTN_UNACK` | `ALARM_CLEARED` | `CLEARED` | **deleted** |

> This is ISA-18.2 behaviour. ACK on `RTN_UNACK` → alarm is gone. React must **remove** the alarm card, not update it.

### CLEAR Endpoint

- Only valid from `ACTIVE_ACK` state.
- `RTN_UNACK` → `CLEARED` is handled via ACK, not CLEAR.
- Returns `event_type: "ALARM_CLEARED"`, `new_state: "CLEARED"`.

### URL Encoding

`alarm_key` contains `:` — must be URL-encoded in the path:
```
POST /api/alarms/Random.Real4%3AHigh/ack
```
C# decodes it: `Uri.UnescapeDataString(key)` → `"Random.Real4:High"`.

---

## 7. Flask HMI Proxy (`alarm_controller.py`)

Flask sits between React and C#. It:
1. Receives operator action from React
2. Proxies the mutation to C# (`POST /api/alarms/{key}/ack` or `clear`)
3. Writes an audit record to `alarm_audit_trail` (non-fatal if it fails)
4. Returns C#'s response back to React

### Flask Alarm Routes

| Flask Route | Proxies To | Writes Audit |
|-------------|-----------|--------------|
| `GET /api/alarms/active` | `C# GET /api/alarms/active` | No |
| `GET /api/alarms/history` | `C# GET /api/alarms/history` | No |
| `POST /api/alarms/<key>/acknowledge` | `C# POST /api/alarms/{key}/ack` | Yes — `action_type='ACKNOWLEDGED'` |
| `POST /api/alarms/<key>/clear` | `C# POST /api/alarms/{key}/clear` | Yes — `action_type='CLEARED'` |

### ACK Audit — Two Paths (Flask)

Flask computes `new_state` and `event_type` based on the alarm state **before** proxying:

```python
# Before calling C#:
alarm_state = current_alarm['alarm_state']   # read from alarm_active

new_state  = 'CLEARED'          if alarm_state == 'RTN_UNACK' else 'ACTIVE_ACK'
event_type = 'ALARM_CLEARED'    if alarm_state == 'RTN_UNACK' else 'ALARM_ACKNOWLEDGED'

# Then write audit:
AlarmAuditDAO(db_service).insert_audit_record(
    action_type     = 'ACKNOWLEDGED',
    previous_state  = alarm_state,
    new_state       = new_state,
    event_type      = event_type,
    ...
)
```

### CLEAR Audit (Flask)

```python
AlarmAuditDAO(db_service).insert_audit_record(
    action_type    = 'CLEARED',
    previous_state = 'ACTIVE_ACK',
    new_state      = 'CLEARED',
    action_reason  = clear_reason,
    ...
)
```

> ⚠️ `AlarmAuditDAO.log_alarm_action()` static method does **NOT exist**. Always use `AlarmAuditDAO(db_service).insert_audit_record(...)`.

---

## 8. Database Tables

### `historian_raw.alarm_active`

Runtime state table. Contains **only non-cleared alarms**.
Row is **DELETED** (not updated to CLEARED) when alarm is resolved.

Key columns: `alarm_key` (PK), `tag_id`, `level`, `alarm_state`, `occurrence_id`, `instance_seq`, `raised_at`, `raised_value`, `setpoint_value`, `ack_at`, `ack_by`, `rtn_at`, `priority`, `updated_at`

### `historian_raw.historian_events`

Immutable journal. One `INSERT` per transition. Never updated.

Key columns: `event_id`, `time`, `tag_id`, `event_type`, `alarm_state`, `alarm_level`, `occurrence_id`, `instance_seq`, `alarm_actual_value`, `alarm_setpoint`, `alarm_priority`, `message`

`alarm_state` CHECK constraint — Phase 1 states only:
```sql
CHECK (alarm_state IS NULL OR alarm_state IN (
    'ACTIVE_UNACK', 'ACTIVE_ACK', 'RTN_UNACK', 'CLEARED'
))
```

### `historian_raw.alarm_audit_trail`

Operator action log. Written by Flask only. Records every ACK, CLEAR, shelve etc.
Read via `historian_raw.v_alarm_audit_trail` (27-column view).

### `historian_raw.v_alarm_audit_trail` (View)

27 columns including:
- col 25 (index 24): `minutes_since_previous_action`
- col 26 (index 25): `minutes_since_raised`
- col 27 (index 26): `response_time_seconds`

> View was recreated in May 2026 to add the two missing computed columns. Script: `WEB_HMI_MFA/mqtt_subscriber_service/sql/update_alarm_audit_view.sql`

---

## 9. Per-Tag Serialization

`AlarmStateManager` uses one `SemaphoreSlim(1,1)` per `alarm_key` to prevent:
- Evaluation racing against operator ACK
- Startup reconciliation racing against evaluation
- Concurrent ACKs on the same alarm

```csharp
private readonly ConcurrentDictionary<string, SemaphoreSlim> _keyLocks = new(...);

await GetLock(alarmKey).WaitAsync(ct);
try { /* evaluate / ACK / reconcile */ }
finally { GetLock(alarmKey).Release(); }
```

---

## 10. DB Write Policy

```
Same state as before?  →  NO DB write, NO MQTT, NO audit
New transition?        →  UPSERT alarm_active
                          INSERT historian_events
                          fire TransitionOccurred event (→ MQTT)
```

If DB write fails: log error, leave memory state unchanged, retry on next evaluation cycle.
Memory is updated **only after** successful DB write.

---

## 11. Startup Reconciliation (`AlarmReconciliationService`)

```
System Start
    ↓
Connect OPC, wait for first live values
    ↓
Load all rows from alarm_active
    ↓
For each row: re-evaluate using LIVE values
    ↓
If condition still true  → restore runtime state in AlarmStateManager memory
If condition cleared     → transition to RTN_UNACK (batch, single transaction)
```

All RTN_UNACK updates committed in a single transaction.
MQTT is suppressed during reconciliation.
One summary event published after reconciliation completes.

---

## 12. Key Rules (Non-Negotiable)

1. **C# is sole authority** — Flask never writes `alarm_active` or `historian_events`.
2. **CLEARED = row deleted** — `alarm_active` never contains a row with `alarm_state = 'CLEARED'`.
3. **RTN_UNACK + ACK = CLEARED** — React must remove the alarm card, not update its state.
4. **No write unless state changes** — same state = zero DB activity.
5. **Audit trail failure is non-fatal** — Flask logs and continues; alarm state is unaffected.
6. **OPC quality gating** — Bad/Uncertain quality blocks raise AND RTN; active alarm state is preserved.
7. **alarm_key format** — always `"{tag_id}:{level}"` e.g. `"Random.Real4:High"`.
8. **URL-encode alarm_key** in REST paths — `:` → `%3A`.
9. **MQTT is optional** — broker failure never affects alarm correctness; HMI reads DB.

---

## 13. Blocking Fix (If Needed)

If stale test rows block a tag from raising new alarms:

```sql
UPDATE historian_raw.historian_events
SET alarm_state = 'CLEARED'
WHERE event_id IN (32654, 32655, 32656);
```

---

## 14. Files Reference

| File | Purpose |
|------|---------|
| `Services/AlarmEvaluation/Services/AlarmStateManager.cs` | 4-state machine, DB writes, per-tag locks |
| `Services/AlarmEvaluation/Services/AlarmEvaluationService.cs` | Evaluates pool updates, calls AlarmStateManager |
| `Services/AlarmEvaluation/Services/AlarmReconciliationService.cs` | Startup live-value reconciliation |
| `Controllers/AlarmsController.cs` | REST API — ACK, CLEAR, GET active/history |
| `WEB_HMI_MFA/HMI/controllers/alarm_controller.py` | Flask proxy + audit trail writes |
| `WEB_HMI_MFA/mqtt_subscriber_service/src/database/alarm_audit_dao.py` | DAO for alarm_audit_trail |
| `WEB_HMI_MFA/mqtt_subscriber_service/sql/create_alarm_audit_trail.sql` | Original table + view DDL |
| `WEB_HMI_MFA/mqtt_subscriber_service/sql/update_alarm_audit_view.sql` | Migration: adds 2 missing view columns (applied May 2026) |
