# Alarm History — Full Audit Report & Fix Plan
**Date:** June 1, 2026  
**Author:** Copilot Audit  
**File Under Investigation:** `HMI/controllers/alarm_controller.py` + `HMI/apex-hmi/src/components/hmi/AlarmHistoryModal.tsx`

---

## Architecture Overview

The C# backend writes **one row per event** into `historian_raw.historian_events`.  
A single alarm occurrence produces **multiple rows with different event_ids**:

| Row | `event_type`      | `time`    | `event_id` | Notes                        |
|-----|-------------------|-----------|------------|------------------------------|
| 1   | `ALARM_RAISED_HH` | 09:16:50  | 501        | alarm fires                  |
| 2   | `ALARM_ACK`       | 09:16:55  | 502        | operator acknowledges        |
| 3   | `ALARM_CLEARED`   | 09:16:56  | 503        | value returns to normal      |

- Rows are **NOT linked by foreign key** — only by `tag_id` + `alarm_level` + time proximity.
- `alarm_audit_trail` stores ACK/CLEAR actions and links back to the **RAISE event's `event_id`**, not the ACK/CLEAR row's `event_id`.

---

## Bug #1 — `orig_event` lateral does NOT filter by `alarm_level` ❌

**Location:** `alarm_controller.py` — `orig_event` LEFT JOIN LATERAL (~line 2082)

**Current broken code:**
```sql
WHERE he2.tag_id = he.tag_id
  AND he2.event_id != he.event_id
  AND he2."time" <= he."time"
  AND (he2.event_type = 'ALARM' OR he2.event_type LIKE 'ALARM_RAISED%%')
ORDER BY he2."time" DESC
LIMIT 1
```

**Problem:**  
For tag `PY1105F` at `09:16:55` (ACK for HIGH), this finds the most recent RAISE event  
for **any level** — returns `ALARM_RAISED_HH` at `09:16:54` instead of `ALARM_RAISED_H` at `09:16:50`.

**Impact:**
- ❌ Detail card "ALARM RAISED → Time" shows wrong time (HH raise time instead of H raise time)
- ❌ Trigger Value & Setpoint wrong (HH values instead of H values)

**Fix:** Add `AND he2.alarm_level = he.alarm_level` to the lateral WHERE clause.

**Status:** 🔴 NOT FIXED YET

---

## Bug #2 — Wrong setpoint/value on ACK/RTN rows ❌

**Location:** `alarm_controller.py` — COALESCE for alarm_setpoint/alarm_actual_value

**Current broken code:**
```sql
COALESCE(he.alarm_setpoint, orig_event.alarm_setpoint) AS alarm_setpoint,
COALESCE(he.alarm_actual_value, orig_event.alarm_actual_value) AS alarm_actual_value,
```

**Problem:**  
ACK and CLEARED events have NULL setpoint/value in `historian_events`.  
COALESCE falls back to `orig_event` — but `orig_event` is the wrong level due to Bug #1.

**Impact:**
- ❌ Grid Value/SP column shows wrong numbers for ACK/RTN/CLEARED rows
- ❌ e.g. `0.64 / 0.60` shown for HIGH row instead of correct HIGH setpoint

**Fix:** Resolved by the same fix as Bug #1 (correct `orig_event` level filter).

**Status:** 🔴 NOT FIXED YET (blocked by Bug #1)

---

## Bug #3 — `original_raise_time` wrong on ACK/CLEARED rows ❌

**Location:** `alarm_controller.py` — CASE for `original_raise_time` (~line 2022)

**Problem:**  
`original_raise_time` for non-RAISE rows uses `orig_event.raise_time`.  
Because `orig_event` finds the wrong level (Bug #1), the time is wrong.

**Impact:**
- ❌ Detail card "ALARM RAISED → Time" for ACK/CLEARED rows shows wrong time

**Fix:** Resolved by the same fix as Bug #1.

**Status:** 🔴 NOT FIXED YET (blocked by Bug #1)

---

## Bug #4 — ACK/CLEAR rows show "Not ACK'd" because audit trail links to RAISE event_id ❌

**Location:** `alarm_controller.py` — `ack_at` and `clr_at` lateral joins

**Current broken code:**
```sql
WHERE event_id = he.event_id AND action_type = 'ACKNOWLEDGED'
```

**Problem:**  
The audit trail `event_id` column stores the **RAISE event's ID** (e.g. 501), NOT the ACK row's ID (502).  
So for ACK row (event_id=502): `ack_at` finds nothing → `acknowledged_by = NULL`.

**Impact:**
- ❌ ACK/CLEARED rows show "Not ACK'd" / no operator name
- ❌ The RAISE row correctly shows the operator (audit event_id matches RAISE event_id)
  but ACK and CLEARED rows don't

**Fix:**  
For `ack_at` and `clr_at` joins, also search by `alarm_key` = `tag_id:alarm_level`  
so all event types can resolve the operator from audit trail, regardless of which `event_id` the audit record is stored under.

**Status:** 🔴 NOT FIXED YET

---

## Bug #5 — Grid timestamp column shows event action time, not raise time ❌

**Location:** `AlarmHistoryModal.tsx` line ~421

**Current code:**
```tsx
<td>{fmt(r.raised_at)}</td>
```

**Problem:**  
`raised_at = he."time"` = the time of **that specific event row**.  
- For ACK row → shows ACK time (09:16:55), not when alarm was raised (09:16:50)  
- For RTN row → shows RTN time, not raise time  

This misleads the operator into thinking the alarm was raised at the ACK/RTN time.

**Fix:** Display `r.original_raise_time ?? r.raised_at` in the grid timestamp column  
so every row shows when the alarm was **originally raised**.

**Status:** 🔴 NOT FIXED YET

---

## Fix Plan (ordered by dependency)

| Order | Bug | Fix | Test |
|-------|-----|-----|------|
| 1 | Bug #1 + #2 + #3 | Add `alarm_level` filter to `orig_event` lateral | Expand ACK row → ALARM RAISED time must match RAISE row time |
| 2 | Bug #4 | Fix `ack_at`/`clr_at` audit join to use alarm_key fallback | ACK/CLEARED rows must show operator name |
| 3 | Bug #5 | Frontend: use `original_raise_time` in grid timestamp column | All rows show alarm raise time, not action time |

---

## Fix Status Tracker

| Fix | Applied | Flask Restarted | Tested | Result |
|-----|---------|-----------------|--------|--------|
| Bug #1/#2/#3 — `orig_event` alarm_level filter | ✅ | ✅ | ⏳ Pending user test | — |
| Bug #4 — audit trail alarm_key fallback | ✅ | ✅ | ⏳ Pending user test | — |
| Bug #5 — frontend grid timestamp | ✅ | ✅ (Vite hot-reload) | ⏳ Pending user test | — |
