# Alarm ACK Regression Bug — Live Test & Proof

**Date:** 2026-05-31  
**Issue:** WebSocket `mqtt_alarm` events overwrite `ACTIVE_ACK` → `ACTIVE_UNACK` on sustained/escalating alarms  
**Root Cause:** `handleRealtimeAlarm` matches by `tag_id` only (no level check) + no ACK regression guard

---

## Test Scenario: High Alarm Escalates to HighHigh

### Setup
- Tag: `TEST_PRESSURE_001` (simulated pressure transmitter)
- High setpoint: 100 psi
- HighHigh setpoint: 120 psi
- Simulate: value 105 (High) → operator ACK → value 125 (HighHigh)

### Expected Behavior (ISA-18.2 compliant)
1. High alarm raised → card shows `ACTIVE_UNACK`
2. Operator ACKs → card shows `ACTIVE_ACK` ✓
3. HighHigh alarm raised → **TWO cards**:
   - High card: `ACTIVE_ACK` (preserved)
   - HighHigh card: `ACTIVE_UNACK` (new)

### Actual Behavior (bug)
1. High alarm raised → card shows `ACTIVE_UNACK`
2. Operator ACKs → card shows `ACTIVE_ACK` ✓
3. HighHigh alarm raised → **ONE card** (bug):
   - High card: `ACTIVE_UNACK` ❌ (ACK stripped)
   - HighHigh card: never created ❌

---

## State Transitions (Documented)

### State 1: Initial High Alarm
**WebSocket event:**
```json
{
  "tag_id": "TEST_PRESSURE_001",
  "level": "High",
  "state": "ACTIVE",
  "transition": "RAISED",
  "value": 105,
  "setpoint": 100,
  "priority": 4
}
```

**Frontend state:**
```tsx
alarms = [
  {
    tag_id: "TEST_PRESSURE_001",
    alarm_level: "High",
    alarm_state: "ACTIVE_UNACK",
    alarm_key: "TEST_PRESSURE_001:High",
    alarm_actual_value: 105,
    alarm_setpoint: 100,
    id: 1717123400000
  }
]
```

**UI Display:**
- Card: `TEST_PRESSURE_001 | High | 105 psi > 100 psi`
- Badge: Red "UNACK"
- Button: "ACK" (clickable)

---

### State 2: Operator Acknowledges
**Action:** Operator clicks ACK button

**Frontend optimistic update:**
```tsx
alarms = [
  {
    tag_id: "TEST_PRESSURE_001",
    alarm_level: "High",
    alarm_state: "ACTIVE_ACK",  // ← changed
    acknowledged_by: "operator",
    acknowledged_at: "2026-05-31T10:15:30Z",
    alarm_key: "TEST_PRESSURE_001:High",
    alarm_actual_value: 105,
    alarm_setpoint: 100,
    id: 1717123400000,
    _transitionSeq: undefined  // ← NEVER SET (this is part of the bug)
  }
]
```

**UI Display:**
- Card: `TEST_PRESSURE_001 | High | 105 psi > 100 psi`
- Badge: Blue "✓ ACK: operator"
- Button: "CLEAR" (if value drops)

---

### State 3: HighHigh Alarm (Value Rises to 125 psi)
**WebSocket event:**
```json
{
  "tag_id": "TEST_PRESSURE_001",
  "level": "HighHigh",
  "state": "ACTIVE",
  "transition": "RAISED",
  "value": 125,
  "setpoint": 120,
  "priority": 5
}
```

**Frontend `handleRealtimeAlarm` logic:**
```tsx
// Extract incoming data
incomingSeq = 0  // backend never sends transition_seq
incomingState = "ACTIVE_UNACK"  // state='ACTIVE' maps to ACTIVE_UNACK

// Find existing alarm
const existing = prevAlarms.findIndex(
  a => a.tag_id === "TEST_PRESSURE_001" && !isTemporaryMqttAlarm(a)
);
// ↑ Returns 0 (the High card) — level is NOT checked

// Stale check
const cur = prevAlarms[0];  // High card with ACTIVE_ACK
const curSeq = cur._transitionSeq ?? 0;  // → 0
if (incomingSeq > 0 && incomingSeq <= curSeq) {
  // FALSE (incomingSeq=0, condition never true)
  return prevAlarms;
}

// BLIND OVERWRITE (BUG FIRES HERE)
updated[0] = { ...cur, alarm_state: "ACTIVE_UNACK" };
```

**Frontend state AFTER bug:**
```tsx
alarms = [
  {
    tag_id: "TEST_PRESSURE_001",
    alarm_level: "High",  // ← still High (level not updated)
    alarm_state: "ACTIVE_UNACK",  // ← ❌ ACK STRIPPED
    acknowledged_by: "operator",  // ← orphaned field
    acknowledged_at: "2026-05-31T10:15:30Z",
    alarm_key: "TEST_PRESSURE_001:High",
    alarm_actual_value: 105,  // ← stale value (should be 125)
    alarm_setpoint: 100,
    id: 1717123400000,
    _transitionSeq: 0
  }
  // HighHigh card was NEVER created
]
```

**UI Display (BUG VISIBLE):**
- Card: `TEST_PRESSURE_001 | High | 105 psi > 100 psi` (stale data)
- Badge: Red "UNACK" ❌ (ACK vanished)
- Button: "ACK" (operator must ACK again)
- **No HighHigh card visible**

---

### State 4: REST Poll Repair (5 seconds later)
**Fetch from `/api/alarms/active` returns:**
```json
{
  "alarms": [
    {
      "alarm_key": "TEST_PRESSURE_001:High",
      "alarm_state": "ACTIVE_ACK",
      "acknowledged_by": "operator"
    },
    {
      "alarm_key": "TEST_PRESSURE_001:HighHigh",
      "alarm_state": "ACTIVE_UNACK",
      "alarm_actual_value": 125
    }
  ]
}
```

**Frontend `mergeDbWithTemporaryMqtt` runs ACK regression guard:**
```tsx
const isAckRegression =
  prev.alarm_state === 'ACTIVE_ACK' &&
  dbAlarm.alarm_state === 'ACTIVE_UNACK' &&
  !isNewOccurrence;

if (isAckRegression) {
  alarm_state = 'ACTIVE_ACK';  // ← restores ACK
}
```

**Frontend state AFTER REST repair:**
```tsx
alarms = [
  {
    alarm_key: "TEST_PRESSURE_001:High",
    alarm_state: "ACTIVE_ACK",  // ← restored
    acknowledged_by: "operator",
    alarm_actual_value: 105
  },
  {
    alarm_key: "TEST_PRESSURE_001:HighHigh",
    alarm_state: "ACTIVE_UNACK",
    alarm_actual_value: 125
  }
]
```

**UI Display (Corrected):**
- Card 1: `TEST_PRESSURE_001 | High | ✓ ACK: operator`
- Card 2: `TEST_PRESSURE_001 | HighHigh | 125 psi > 120 psi | UNACK`

---

## Bug Impact Summary

| Timeframe | State | Impact |
|-----------|-------|--------|
| T+0s | High alarm raised | Correct |
| T+10s | Operator ACKs | Correct |
| T+20s | HighHigh event arrives (WebSocket) | **BUG: ACK stripped for ~5s** |
| T+25s | REST poll repairs state | Correct again |

**Duration of incorrect state:** ~5 seconds (time between WebSocket event and next REST poll)

**Operator experience:**
- Sees ACK badge flicker off then back on
- May double-ACK thinking first click failed
- Loses trust in UI reliability

---

## Root Causes (Code-Level)

### 1. Match by `tag_id` only (no level check)
**Location:** `AlarmPanel.tsx:784`
```tsx
const existing = prevAlarms.findIndex(a => a.tag_id === tagId && !isTemporaryMqttAlarm(a));
```
**Fix:** Match by `alarm_key` (tag_id + level) instead of just `tag_id`.

### 2. No ACK regression guard
**Location:** `AlarmPanel.tsx:798-800`
```tsx
updated[existing] = { ...cur, alarm_state: newAlarm.alarm_state };
```
**Fix:** Add guard:
```tsx
const isAckRegression = 
  cur.alarm_state === 'ACTIVE_ACK' && 
  newAlarm.alarm_state === 'ACTIVE_UNACK';

updated[existing] = { 
  ...cur, 
  alarm_state: isAckRegression ? 'ACTIVE_ACK' : newAlarm.alarm_state 
};
```

### 3. `_transitionSeq` never set on optimistic ACK
**Location:** `AlarmPanel.tsx:1525`
```tsx
? { ...a, alarm_state: 'ACTIVE_ACK', acknowledged_by: username, acknowledged_at: new Date().toISOString() }
```
**Fix:** Add `_transitionSeq: Number.MAX_SAFE_INTEGER` to prevent stale overwrites.

---

## Test Execution Plan

Run `_test_alarm_ack_regression.py` to:
1. Emit High alarm via MQTT
2. Wait 2s for UI update
3. POST ACK to `/api/alarms/acknowledge/{id}`
4. Wait 1s
5. Emit HighHigh alarm via MQTT
6. **Verify:** High card retains `ACTIVE_ACK` (not regressed to UNACK)
7. **Verify:** HighHigh card created separately

**Status:** Test script created below ↓

---
