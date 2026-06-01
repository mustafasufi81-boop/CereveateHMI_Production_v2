# Alarm Card "Missing Value" — Investigation & Fix Options

**Date:** 2026-05-31
**Component:** Alarm Panel (HMI) — live PV / setpoint display on alarm cards
**Status:** Diagnosed. Fix not yet applied (awaiting decision).
**Scope guard:** No C#/PLC code was modified during this investigation. Only read-only inspection + temporary `_diag_*.py` scripts were used.

---

## 1. Symptom

Some alarm cards (e.g. `AY1101`) intermittently render **without** their value (PV) shown,
while other tag cards (e.g. `PDY1104`) display the value fine. The card itself still
appears in the panel — only the **SP / PV** value block is missing.

---

## 2. What was studied

### 2.1 Frontend render path
- `HMI/apex-hmi/src/components/hmi/AlarmPanel.tsx`
  - **Card value block (~line 3067):** the SP/PV block is gated by:
    ```tsx
    {alarm.alarm_setpoint !== null && alarm.alarm_actual_value !== null && (
       ... SP / Live-PV block ...
    )}
    ```
    The live value itself is read as `tagValues[alarm.tag_id]` and only falls back to
    `alarm.alarm_actual_value` for the displayed number — **but the whole block is hidden
    unless `alarm_actual_value` is non-null.**
  - **Live tag values (`tagValues`):** populated every poll from `/api/tags/latest`
    (fetch at ~line 571, map build at ~line 601).
  - **Realtime MQTT handler `handleRealtimeAlarm` (~line 723):** builds a temporary card with
    `alarm_actual_value: alarmData.value` (~line 783). If `alarmData.value` is `null`, the
    temp card has no actual value.

### 2.2 Backend live-value source
- `HMI/controllers/tag_controller.py` — `/api/tags/latest`
  - Builds a `tags` map from `historian_latest_value`, then **overlays the live PLC pool**
    (`/api/plc/values`) keyed by `tag_id` **or** `tag_name`/`address` via a `name_to_id` map.
  - Confirmed AY1101 and PDY1104 are **both** matched by `tag_name` (their pool `tagId` is
    `null`), so both resolve to a live value. The null `tagId` is harmless here.

### 2.3 MQTT alarm delta source
- `mqtt_subscriber_service/websocket_bridge.py` (~line 173) and `HMI/app.py`
  (~lines 1012 & 1070) both `emit('mqtt_alarm', …)` carrying `value` and `setpoint`
  taken directly from the published MQTT payload.
- `CSharpBackend/Services/AlarmEvaluation/Services/AlarmEvaluationService.cs`
  `PublishTransitionAsync` (~line 384) serialises `value = evt.Value`,
  `setpoint = evt.SetpointValue` from the `AlarmTransitionEvent`.
- `CSharpBackend/Services/AlarmEvaluation/Models/AlarmTransitionEvent.cs`
  `Value` and `SetpointValue` are **`double?`** (default `null`).
- `CSharpBackend/Services/AlarmEvaluation/Services/AlarmStateManager.cs`
  `EmitTransition(...)` calls are **inconsistent**:

  | Transition | Sets `Value` / `SetpointValue`? | Approx. line |
  |-----------|--------------------------------|--------------|
  | **RAISED** (`ActiveUnack`)        | ✅ Yes | ~323 |
  | **RTN** (`RtnUnack`)              | ✅ Yes | ~485 |
  | **Auto-clear** (non-latching)     | ✅ Yes | ~593 |
  | **ACK** (`ActiveAck`)             | ❌ **No** | ~798 |
  | **Operator CLEAR** (ACK→CLEARED)  | ❌ **No** | ~777 |

---

## 3. Diagnostic evidence

Simulated the **exact** `/api/tags/latest` pipeline for all active alarm cards:

| Check | Result |
|-------|--------|
| Active alarm cards | **204** |
| Cards that resolve a live PV after overlay | **204 (all)** |
| Cards with no live value | **0** |
| Active alarms in DB with NULL `setpoint_value` or `raised_value` | **0** |

Pool sample for the two reference tags (both identical in structure):
```
{"tagId": null, "tagName": "AY1101",  "address": "AY1101",  "value": 1.99, "quality": "Good"}
{"tagId": null, "tagName": "PDY1104", "address": "PDY1104", "value": 2.38, "quality": "Good"}
```

**Conclusion:** The data pipeline is healthy. The `tagId is null` lead was a dead end.

---

## 4. Root cause

The missing value is **not per-tag** — it is **per last-transition**:

- A tag whose most recent MQTT delta was **RAISED / RTN** → delta carries the value →
  card shows it.
- A tag whose most recent delta was **ACK / CLEAR** → delta carries `value: null,
  setpoint: null` (because those `EmitTransition` blocks don't set them).
  - If that delta creates a fresh **temporary** card (no DB row yet for that `alarm_key`),
    the card's `alarm_actual_value` is `null`.
  - The frontend render gate
    `alarm.alarm_setpoint !== null && alarm.alarm_actual_value !== null`
    then **hides the entire SP/PV block** until the next 1-second DB snapshot backfills it.

So tags that get acknowledged/cleared frequently appear to "lose" their value, while tags
that were last RAISED keep showing it.

---

## 5. Fix options

### Option 1 — C# source fix (data completeness)
Add `Value` and `SetpointValue` to the two `EmitTransition` blocks that currently omit them
in `AlarmStateManager.cs` (ACK and operator-CLEAR). The runtime state already holds
`state.SetpointValue`; pass the last-known value alongside it.

**Illustrative change (ACK block ~line 798):**
```csharp
EmitTransition(new AlarmTransitionEvent
{
    AlarmKey      = state.TagId,
    // ... existing fields ...
    Timestamp     = ackAt,
    Operator      = operatorName,
    Value         = state.RaisedValue,     // ADD — carry last known PV
    SetpointValue = state.SetpointValue,   // ADD — carry setpoint
});
```
(Repeat for the ACK→CLEARED block ~line 777.)

**Pros**
- Fixes the root data at the source; MQTT payload + event journal become complete for
  every transition type.

**Cons**
- Touches the alarm state-machine code that was just stabilised (higher blast radius).
- Requires a C# rebuild/redeploy.
- Only fixes the **delta** payload; the UI is still gated on a possibly-null field, so the
  frontend change is *still* wanted to cover temp cards / reconnect races.
- `state.RaisedValue` is the trip value, not necessarily the live PV at ACK time — the UI's
  live overlay is still the better PV source.

---

### Option 2 — Frontend-only fix (recommended primary)
In `AlarmPanel.tsx`, drive the SP/PV block off the **live** value
(`tagValues[alarm.tag_id]`) with `alarm.alarm_actual_value` only as a fallback, and show the
block whenever **either** a live value **or** a trip value exists.

**Illustrative change (~line 3067):**
```tsx
{/* Show the block when we have a setpoint AND any value (live OR trip) */}
{alarm.alarm_setpoint != null &&
 (tagValues[alarm.tag_id] != null || alarm.alarm_actual_value != null) && (
   <div className="...">
     {/* SP unchanged */}
     {(() => {
       const liveVal    = tagValues[alarm.tag_id] ?? null;
       const displayVal = liveVal ?? alarm.alarm_actual_value!;   // live wins, trip fallback
       const isLive     = liveVal !== null;
       // ... existing PV / PV@Trip rendering using displayVal ...
     })()}
   </div>
)}
```

**Pros**
- Fixes the actual display goal: the card always shows the **current PV** from the
  always-populated `/api/tags/latest` source.
- **Zero backend risk** — no C#/PLC/alarm-engine/MQTT/DB changes; no rebuild.
- Covers **every** gap at once: ACK/CLEAR null deltas, temporary MQTT cards, reconnect races.
- One small, contained `.tsx` change.

**Cons**
- If both the live value *and* the trip value are genuinely absent (rare — observed in
  0/204 cards), the block still won't render. Acceptable, since there is nothing to show.

---

## 6. Recommendation

1. **Now:** apply **Option 2** (frontend-only). It is low-risk, fixes the operator-facing
   behaviour completely, and leaves all C#/PLC code untouched.
2. **Later (optional, low priority):** apply **Option 1** for MQTT/journal payload
   completeness, only when a C# rebuild is acceptable.

---

## 7. Files referenced (read-only)

- `HMI/apex-hmi/src/components/hmi/AlarmPanel.tsx`
- `HMI/controllers/tag_controller.py`
- `HMI/controllers/alarm_controller.py`
- `HMI/app.py`
- `mqtt_subscriber_service/websocket_bridge.py`
- `CSharpBackend/Services/AlarmEvaluation/Services/AlarmEvaluationService.cs`
- `CSharpBackend/Services/AlarmEvaluation/Services/AlarmStateManager.cs`
- `CSharpBackend/Services/AlarmEvaluation/Models/AlarmTransitionEvent.cs`
