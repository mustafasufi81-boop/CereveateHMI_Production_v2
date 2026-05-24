# Cereveate HMI — Alarm System Complete Guide
**ISA-18.2 Compliant | May 2026**

---

## 1. Architecture Overview

```
OPC DA Server (Matrikon)
    ↓ Tag values polled every 1000ms
C# AlarmStateManager (OpcDaWebBrowser.exe — port 5001)
    ↓ Evaluates limits, manages alarm lifecycle
    ├── historian_raw.alarm_active        ← Runtime operational table (1 row per card)
    └── historian_raw.historian_events    ← Immutable append-only journal (every transition)
         ↓
Flask HMI Backend (app.py — port 6001)
    ├── Reads alarm_active for active panel
    ├── Proxies ACK/CLEAR to C# (C# is sole state authority)
    ├── Writes alarm_audit_trail (ACK/CLEAR/SUPPRESS audit)
    └── Reads historian_events for history modal
         ↓
React Vite HMI (apex-hmi — port 8090)
    ├── AlarmPanel.tsx     ← Active alarm cards
    └── AlarmHistoryModal  ← Full history with filters
```

---

## 2. Database Tables

### `historian_raw.alarm_active` — Runtime State (C# owns this)
| Column | Description |
|--------|-------------|
| `alarm_key` | Stable card identity = `tag_id + level` (e.g. `Random.Real4_LOWLOW`) |
| `current_event_id` | FK to latest historian_events row (changes on oscillation) |
| `alarm_state` | `ACTIVE_UNACK` / `ACTIVE_ACK` / `RTN_UNACK` |
| `raised_at` | First-hit timestamp (frozen — never overwritten) |
| `raised_value` | PV value at first hit (frozen — never overwritten) |
| `setpoint_value` | Alarm limit (SP) |
| `level` | `HIGH` / `HIGHHIGH` / `LOW` / `LOWLOW` |
| `priority` | 1–5 |
| `ack_at` / `ack_by` | Who acknowledged and when |
| `rtn_at` | When value returned to normal |
| `occurrence_id` | Increments on every re-fire (oscillation count) |
| `instance_seq` / `transition_seq` | Sequence numbers for ordering |

### `historian_raw.historian_events` — Immutable Journal (C# owns this)
One row per state transition. Never updated — only appended.

### `historian_raw.alarm_audit_trail` — Operator Actions (Flask owns this)
| Column | Used for |
|--------|---------|
| `action_type` | `RAISED` / `ACKNOWLEDGED` / `CLEARED` / `SUPPRESSED` / `UNSUPPRESSED` |
| `performed_by` | Operator username |
| `action_timestamp` | When the action happened |
| `action_reason` | Clear/suppress reason |
| `action_notes` | Optional notes |
| `metadata` (jsonb) | For suppression: `{alarm_key, alarm_level, suppress_until, duration_hours}` |

---

## 3. Alarm Lifecycle (ISA-18.2 State Machine)

```
                    ┌─────────────────────────────────────┐
                    │           PROCESS LIMIT HIT          │
                    └──────────────┬──────────────────────┘
                                   ↓
                          ┌─────────────────┐
                          │  ACTIVE_UNACK   │  ← Card appears (red/orange border)
                          │  [ACK] [SUPP]   │    PV@Trip frozen, raised_at frozen
                          └────┬────────────┘
                               │ Operator presses ACK
                               ↓
                 ┌─────────────────────────────┐
                 │        ACTIVE_ACK           │  ← Card shows ✓ACK + operator name + time
                 │  [CLEAR]                    │    CLEAR button now available
                 └────┬──────────────┬─────────┘
                      │              │ Value returns to normal
                      │              ↓
                      │      ┌───────────────┐
                      │      │  RTN_UNACK    │  ← "RTN" badge, ACK button re-appears
                      │      │  [ACK]        │    ACKing RTN → auto CLEARED
                      │      └───────────────┘
                      │ Operator presses CLEAR
                      ↓
              ┌──────────────────┐
              │     CLEARED      │  ← Card grayed, ✓ACK + ✓CLR shown
              │  (removed from   │    Removed from active panel on next poll
              │   active panel)  │    Remains in history forever
              └──────────────────┘

SUPPRESS path (parallel — does NOT change alarm_state):
  ACTIVE_UNACK/RTN_UNACK → [SUPP] → card hidden from panel
  After duration expires → card reappears automatically
  OR operator presses [Restore] in suppressed section → immediate restore
```

---

## 4. Alarm Card — What It Shows

```
┌─────────────────────────────────────────────────────┐
│ 🔔  Triangle Waves.Real4                           │
│                                                     │
│ Triangle Waves.Real4 exceeded Low-Low limit: 2.54  │
│ (setpoint: 5)                                       │
│                                                     │
│  SP: 5.00   PV@Trip: 2.54 ↘                       │
│                                                     │
│  🕐 03:40:47 AM   +19m   ×2   [spacer]  RTN  LL P2 │
│                                                     │
│  [✓ACK]  [SUPP]                                    │
└─────────────────────────────────────────────────────┘
```

| Element | Description |
|---------|-------------|
| **Tag name** (amber) | OPC tag identifier |
| **Message** | Auto-generated: `tag exceeded level limit: value (setpoint: SP)` |
| **SP** | Alarm setpoint (limit configured in C#) |
| **PV@Trip** | ⚠️ **FROZEN** — exact PV value at first-hit moment. Never changes even if tag oscillates |
| **🕐 HH:MM:SS** | ⚠️ **FROZEN** — absolute time of first hit. Never changes |
| **+Nm** | Live elapsed time computed in browser from frozen raised_at (updates every 60s) |
| **×N** | Occurrence count — how many times this limit has fired since card raised |
| **RTN badge** | Value has returned to normal but not yet acknowledged |
| **✓ ACK badge** | Alarm has been acknowledged (shows on ACTIVE_ACK and CLEARED) |
| **LL/HH/H/L** | Which limit was crossed (level badge) |
| **P1–P5** | Priority (P5=Critical, P4=Urgent, P3=High, P2=Medium, P1=Low) |
| **ACK button** | Acknowledge the alarm |
| **SUPP button** | Suppress (hide temporarily) |
| **CLEAR button** | Appears after ACK — permanently closes the alarm lifecycle |

### After ACK (ACTIVE_ACK state):
```
✓ ACK: Mustafa
@ 03:45:12 AM          [CLEAR button]
```

### After CLEAR (CLEARED state — grayed card):
```
✓ ACK: Mustafa @ 03:45:12 AM
✓ CLR: Mustafa @ 03:47:33 AM
```

---

## 5. One Card Per Alarm Type Rule

**Key invariant:** `alarm_active` has ONE row per `alarm_key` (`tag_id + level`).

- `Triangle.Waves.Real4` crossing LL = 1 card
- `Triangle.Waves.Real4` crossing L = 1 different card
- If LL fires, returns to normal, fires again → **same card** (occurrence_count increments)
- Only after CLEAR does the next LL hit create a fresh card

**Why PV@Trip is frozen:** The first value that triggered the alarm is what matters for diagnosis. Subsequent oscillations would overwrite it — this is prevented by the `alarm_key`-based merge lock in the React state.

---

## 6. Suppression System

### How it works:
1. Operator clicks **[SUPP]** on any `ACTIVE_UNACK` or `RTN_UNACK` card
2. Suppression modal opens — select duration + reason (required)
3. Flask writes `action_type='SUPPRESSED'` to `alarm_audit_trail` with metadata:
   ```json
   {
     "alarm_key": "Triangle.Waves.Real4_LOWLOW",
     "alarm_level": "LOWLOW",
     "suppress_until": "2026-05-13T05:40:47Z",
     "duration_hours": 1
   }
   ```
4. Active alarm query excludes this `alarm_key` until `suppress_until` expires
5. Card disappears from active panel
6. **⊘ Suppressed (1)** section appears at bottom of alarm panel

### Suppressed section shows:
- Tag name + level badge
- Reason · by `Mustafa` · suppressed at `03:40:47`
- `→ until 04:40:47` (or `→ indefinite`)
- **[Restore]** button — instantly lifts suppression

### Duration options:
| Duration | Use case |
|----------|---------|
| 1h | Short maintenance task |
| 4h | Half-shift maintenance |
| 8h | Full shift |
| 24h | Day-long outage |
| Indefinite | Permanent sensor fault, engineer to review |

### Suppression reasons (ISA-18.2 documented):
- Engineering Test
- Planned Maintenance
- Sensor Fault
- Process Upset
- Nuisance Alarm
- Other

### What suppression does NOT do:
- ❌ Does NOT stop historian_events writes — C# still logs every tag value change
- ❌ Does NOT stop alarm_active updates — C# still tracks alarm state
- ❌ Does NOT acknowledge the alarm — it's still ACTIVE_UNACK in DB
- ✅ Only hides it from the HMI operator panel

---

## 7. Database Logging — Always On

**This is critical:** Suppression, ACK, CLEAR are **HMI-layer actions only**.
The C# data pipeline never stops:

```
OPC Tag Value Changes
    ↓ Always
historian_raw.historian_timeseries    ← Every value, every second (deadband controlled)
    ↓
historian_raw.historian_events        ← Every alarm state transition (RAISED/RTN/etc.)
    ↓
historian_raw.alarm_active            ← Current card state

HMI operator actions (Flask) only write:
    → alarm_audit_trail  (ACK/CLEAR/SUPPRESS records)
    → alarm_active.ack_at, ack_by (via C# proxy)
```

Even if an alarm is:
- ✅ Suppressed → historian_events still logs RTN, re-fires, etc.
- ✅ Cleared → next re-fire still creates new historian_events row
- ✅ HMI is disconnected → C# keeps logging everything

---

## 8. History Modal

Access via **[History]** button in alarm panel header.

### Filters available:
| Filter | Options |
|--------|---------|
| Date From / To | Date range picker |
| Tag ID | Dropdown of all seen tags |
| Search | Free text on tag_id or message |
| Alarm Level | HIGH / HIGHHIGH / LOW / LOWLOW |
| Alarm State | ACTIVE_UNACK / ACTIVE_ACK / CLEARED / RTN_UNACK |
| Priority | P1–P5 |
| Sort | Time / Tag / Level / Priority (asc/desc) |

### Each history row shows:
| Column | Source |
|--------|--------|
| Raised At | `historian_events.time` (first hit) |
| Tag | `historian_events.tag_id` |
| Level badge | `historian_events.alarm_level` |
| Priority badge | `historian_events.alarm_priority` |
| State | Derived from `alarm_audit_trail` LATERAL join |
| Message | `historian_events.message` |
| Duration | Time from raised to cleared |

### Expand row → 3-panel audit view:
```
┌──────────────────┬───────────────────────┬────────────────────────┐
│  ALARM RAISED    │   ACKNOWLEDGEMENT      │   CLEARANCE            │
│                  │                        │                        │
│ Time: 03:48:36   │ By: Mustafa            │ By: Mustafa            │
│ Tag: Random...   │ At: 03:49:12           │ At: 03:51:44           │
│ Level: LowLow    │ Notes: -               │ Reason: Process adj... │
│ PV: 2.54         │                        │                        │
│ SP: 5.00         │                        │                        │
│ Priority: URGENT │                        │                        │
└──────────────────┴───────────────────────┴────────────────────────┘
```

---

## 9. API Endpoints (Flask port 6001)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/alarms/active` | Active alarm cards (excludes suppressed) |
| POST | `/api/alarms/acknowledge/<id>` | ACK alarm → proxied to C# |
| POST | `/api/alarms/clear/<id>` | CLEAR alarm → proxied to C# |
| GET | `/api/alarms/suppressed` | List all active suppressions |
| POST | `/api/alarms/suppress/<id>` | Suppress alarm card |
| POST | `/api/alarms/unsuppress/<id>` | Lift suppression immediately |
| GET | `/api/alarms/history` | Paginated history with filters |
| GET | `/api/alarms/history/tags` | Tag list for dropdown |
| GET | `/api/alarms/audit/<id>` | Full audit trail for one alarm |
| GET | `/api/alarms/stats` | Count by state and priority |

---

## 10. Operator Action Sequence (Normal Flow)

```
1. Alarm fires           → Card appears (ACTIVE_UNACK) — red border, flashing
2. Operator sees it      → Note the PV@Trip and raised_at (both frozen)
3. Operator ACKs         → State → ACTIVE_ACK
                         → "✓ ACK: Mustafa @ HH:MM:SS" appears on card
                         → CLEAR button appears
4. Operator fixes issue  → Process value returns to normal (C# sets RTN)
5. Operator CLEARs       → Selects reason from dropdown
                         → "✓ CLR: Mustafa @ HH:MM:SS" appears
                         → Card grays out, removed on next poll
6. History modal         → Full record with RAISED + ACK + CLEAR times + person names
```

## 10b. Suppression Flow (Known/Planned issue)

```
1. Alarm fires           → Card appears (ACTIVE_UNACK)
2. Operator knows cause  → Clicks [SUPP]
3. Modal opens           → Select duration (e.g. 4h) + Reason (Planned Maintenance)
4. Submit               → Card disappears from active panel
                         → "⊘ Suppressed (1)" section shows at bottom
5. During suppression    → DB still logs everything, condition still in alarm_active
6. After 4h             → Card reappears automatically (next 5s poll)
   OR
6b. Operator clicks      → [Restore] → immediate reappear
7. Then handle normally  → ACK → CLEAR
```

---

## 11. Priority vs Level — Never Confuse These

| Concept | Badge | Values | Meaning |
|---------|-------|--------|---------|
| **Level** | `LL` `L` `H` `HH` | Which limit was crossed | Process engineering — which threshold |
| **Priority** | `P1`–`P5` | Configured importance | Business decision — how urgent is operator response |

A `LL` (LowLow) alarm can be `P1` (low priority) — e.g. a non-critical tank.
A `H` (High) alarm can be `P5` (critical) — e.g. a safety-critical pump.

---

## 12. Known Constraints

| Constraint | Reason |
|-----------|--------|
| CLEAR requires ACK first | ISA-18.2 §3.4: operator must acknowledge before closing |
| ACK of RTN_UNACK → auto CLEAR | ISA-18.2 §3.3: if value already returned, ACK = confirmation of lifecycle end |
| Suppress does NOT require ACK | Suppress is a management action, not an acknowledgement |
| PV@Trip frozen in UI | Prevents oscillating tag from overwriting diagnostic first-hit value |
| raised_at frozen in UI | First-hit time is the ISA-18.2 "alarm time" — must never change |
| C# is sole state machine authority | Flask only reads state; mutations go through C# proxy endpoints |
