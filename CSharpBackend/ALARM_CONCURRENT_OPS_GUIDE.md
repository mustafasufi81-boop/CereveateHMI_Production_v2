# Alarm System — Concurrent Operations Guide

> **Last updated: May 23, 2026**  
> Phases 1, 2, and 3 implemented in `AlarmPanel.tsx`. C# `forceAck` in `AlarmStateManager.cs` written — pending build.

---

## Current State (May 2026)

### How the state machine works today

The alarm lifecycle is enforced entirely inside **C# `AlarmStateManager`**.  
Flask and React are only allowed to read state and request transitions — they never write alarm tables directly.

```
ACTIVE_UNACK  ──ACK──►  ACTIVE_ACK  ──CLEAR──►  (removed)
     │                                               ▲
     └──────────────── forceAck=true ────────────────┘
     
ACTIVE_UNACK  ──value returns to normal──►  RTN_UNACK  ──ACK──►  (removed)
```

### C# concurrency protection (already in place)

Every alarm key has its own `SemaphoreSlim(1, 1)`.  
If two operators request ACK on the same alarm at the same moment:

```
Operator A ──► acquires semaphore ──► writes ACK to DB ──► updates memory ──► releases
Operator B ──► waits in semaphore ──► sees ACTIVE_ACK ──► returns false ──► 409 Conflict
```

The C# layer is **already correct** for concurrent access.  
The semaphore IS the queue — requests serialize per key, never race.

### Problem in the React UI (before this fix)

Before this change, `AlarmPanel.tsx` used a single:

```tsx
const [acknowledging, setAcknowledging] = useState<number | null>(null);
```

**Problems:**
1. **Only one alarm could show a spinner at a time** — if two alarms were being ACK'd simultaneously (e.g. bulk operations), the second spinner was invisible
2. **409 Conflict showed a raw `alert()`** — when a second operator ACK'd an alarm first, the late-arriving operator saw: `"Failed to acknowledge alarm: Cannot acknowledge alarm in state 'ACTIVE_ACK'"` — confusing and alarming
3. **No "Ack All" button** — operators had to click each alarm individually during upset conditions (10+ alarms)
4. **No per-alarm feedback** — no way to see which alarms were in-flight
5. **Clear dialog confirm button** shared the same `acknowledging` state as ACK — clicking ACK on a different alarm while clear dialog was open would visually break the UI

---

## What Was Built — Phase by Phase

---

### Phase 1 — Core Safety (Implemented May 23, 2026)

**Goal:** Make individual ACK/CLEAR operations safe, non-blocking and flood-proof.

#### Changes in `AlarmPanel.tsx`

**1. `pendingOps: Set<number>` replaces single `acknowledging` state**

```tsx
// BEFORE — only one alarm could spin at a time:
const [acknowledging, setAcknowledging] = useState<number | null>(null);

// AFTER — each alarm tracks itself independently:
const [pendingOps, setPendingOps] = useState<Set<number>>(new Set());
const addPending    = useCallback((id) => setPendingOps(prev => { const s = new Set(prev); s.add(id);    return s; }), []);
const removePending = useCallback((id) => setPendingOps(prev => { const s = new Set(prev); s.delete(id); return s; }), []);
const isPending     = (id) => pendingOps.has(id);
```

Multiple alarms show spinners simultaneously. Clear dialog uses `isPending` — no more state clash.

**2. Duplicate click guard**

```tsx
if (isPending(alarmId)) return;  // added at start of handleAcknowledge + submitClearAlarm
```

Prevents double-submits. C# already handles this safely with semaphores, but avoids useless traffic.

**3. `AbortController` — 12 second timeout**

```tsx
const controller = new AbortController();
const timeoutId = setTimeout(() => controller.abort(), 12_000);
const response = await fetch(url, { signal: controller.signal, ... });
clearTimeout(timeoutId);
```

If C# or Flask hangs, the spinner clears after 12s. No more infinite pending states.

**4. Graceful 409 / 404 — no more `alert()`**

```
409 → another operator already handled this alarm
      logs to console, calls scheduleRefresh() — no popup
404 → alarm already gone from DB
      calls scheduleRefresh() silently
Other errors → console.error, scheduleRefresh() — no popup
```

**5. Polling overlap guard — `pollingInProgress` ref**

```tsx
const pollingInProgress = useRef(false);

const fetchSnapshot = async () => {
  if (pollingInProgress.current) return;  // skip if previous fetch still running
  pollingInProgress.current = true;
  try { ... } finally { pollingInProgress.current = false; }
};
```

Prevents stacked polls under slow network. No UI flicker from overlapping fetches.

**6. Debounced refresh — `scheduleRefresh()`**

```tsx
const scheduleRefresh = useCallback(() => {
  if (refreshDebounceTimer.current) clearTimeout(refreshDebounceTimer.current);
  refreshDebounceTimer.current = setTimeout(fetchSnapshot, 600);
}, []);
```

All post-ACK/409/404 refresh calls collapse into one fetch 600ms after the last trigger.  
During ACK ALL on 50 alarms: 50 triggers → 1 fetch.

**7. Optimistic local update**

After a successful ACK, the card flips to `ACTIVE_ACK` immediately in local state — no waiting for the next poll cycle. CLEAR button appears instantly.

---

### Phase 2 — ACK ALL + Inline Messages (Implemented May 23, 2026)

**Goal:** Let operators ACK multiple alarms efficiently with safety constraints.

#### Changes in `AlarmPanel.tsx`

**1. Per-alarm checkbox for batch selection**

Each `ACTIVE_UNACK` / `RTN_UNACK` card shows a small checkbox (left of the ACK button).  
Ticking adds the alarm to `selectedForAck: Set<number>`.

**Hard cap: max 10 alarms at once**

```tsx
const ACK_SELECTION_LIMIT = 10;

if (s.size >= ACK_SELECTION_LIMIT) {
  showOpMessage(alarm.id, `Max ${ACK_SELECTION_LIMIT} alarms can be selected at once`, 'warn');
  return prev; // reject — no change to set
}
```

Attempting to select an 11th alarm shows an inline amber notice on that card. No popup.

**2. ACK ALL header button**

Appears in the panel header only when `selectedForAck.size > 0`:

```
[✓ ACK 3/10]
```

Clicking opens a confirmation modal: *"Acknowledge 3 alarms as Mustafa? Each recorded in audit trail."*

**3. Batched execution — `executeAckAll()`**

```tsx
const BATCH = 10;
for (let i = 0; i < ids.length; i += BATCH) {
  const batch = ids.slice(i, i + BATCH);
  await Promise.allSettled(batchAlarms.map(a => handleAcknowledge(a, syntheticEvent)));
}
scheduleRefresh();  // one debounced refresh after all batches complete
```

All N alarms fire concurrently within each batch of 10.  
C# `SemaphoreSlim(1,1)` per key serializes any same-alarm races — each key gets exactly one ACK.  
`scheduleRefresh()` fires once at the end — not after each individual ACK.

**4. Inline per-alarm op messages**

```tsx
const [opMessages, setOpMessages] = useState<Map<number, { text, type }>>(new Map());
const showOpMessage = (id, text, type) => {
  setOpMessages(prev => { m.set(id, { text, type }); return m; });
  setTimeout(() => setOpMessages(prev => { m.delete(id); return m; }), 4_000);
};
```

Each alarm card shows its own inline notice for 4 seconds:
- 🔵 `info` — e.g. "Already handled" on 409
- 🟡 `warn` — e.g. "Max 10 alarms can be selected at once"
- 🔴 `err` — reserved for hard failures

**5. Re-ACK prevention (same occurrence)**

Once a card is optimistically flipped to `ACTIVE_ACK`, the ACK button and checkbox disappear.  
A new ACK button only reappears if C# raises a new occurrence of the same tag (new `alarm_key` or new `raised_at`), which produces a new DB row with a new `id`.

---

### Phase 3 — Metrics Bar (Implemented May 23, 2026)

**Goal:** Give operators instant visibility into UI health without opening DevTools.

#### Changes in `AlarmPanel.tsx`

A persistent metrics bar sits between the search box and the alarm list:

```
● Pending: 2  │  Queued: 3/10  │  Sync: 4s ago  │  187ms   ↻
```

| Column | What it shows | Visual cue |
|--------|--------------|------------|
| **Pending** | In-flight ACK/CLEAR requests right now | Orange pulsing dot when >0 |
| **Queued** | Alarms selected for batch ACK | `N/10`, turns orange when non-zero |
| **Sync** | Seconds since last successful DB fetch | Amber + ⚠ if >10s (stale data warning) |
| **Latency** | How long the last `fetchSnapshot` took | 🟢 <300ms / 🟡 <1000ms / 🔴 ≥1000ms |
| **↻** | Manual force-refresh button | Always clickable |

**Staleness guard**  
If sync is >10 seconds old, the entire metrics bar background turns amber — no text reading required.

**1-second live counter**  
A dedicated `setInterval(1s)` drives the `Xs ago` display. It only re-renders the metrics bar — it does not re-evaluate the alarm list `useMemo`.

**Sync latency tracking in `fetchSnapshot`**

```tsx
const fetchStart = Date.now();
// ... fetch ...
lastSyncAt.current = Date.now();
setSyncLatencyMs(Date.now() - fetchStart);
```

---

## Why `Promise.allSettled` is safe with C# semaphores

When 10 operators ACK the same alarm simultaneously:

```
Requests arrive at C# → all 10 queue on SemaphoreSlim(1,1)
→ Request 1: ACTIVE_UNACK → ACTIVE_ACK (DB write + memory update)
→ Requests 2-10: see ACTIVE_ACK → return false → 409
→ UI: Request 1 spinner clears normally, Requests 2-10 show no popup (logged only)
→ DB audit trail: exactly one ACK row
```

When 10 operators ACK 10 different alarms simultaneously:

```
All 10 run truly in parallel (different keys → different semaphores)
→ All 10 succeed simultaneously
→ All 10 spinners clear at the same time
```

---

## Architecture Summary (current)

| Layer | Role | Concurrency mechanism |
|-------|------|-----------------------|
| **C# `AlarmStateManager`** | Sole state machine authority | `SemaphoreSlim(1,1)` per alarm key |
| **C# `AlarmsController`** | HTTP entry, delegates to state machine | `forceAck=true` on Clear (written, pending build) |
| **Flask `alarm_controller`** | Proxy + audit trail writer | Forwards to C#, never writes alarm tables directly |
| **React `AlarmPanel`** | Display + operator actions | `pendingOps` Set, `scheduleRefresh` debounce, `pollingInProgress` guard |

---

## Pending (not yet done)

| Item | Where | Notes |
|------|-------|-------|
| Build & deploy C# with `forceAck` | `dotnet build -c Release` | Code written in `AlarmStateManager.cs` + `AlarmsController.cs` |
| SignalR push on state change | C# + React | Eliminates 0–5s poll delay between operators |
| Bulk CLEAR (CLEAR ALL) | `AlarmPanel.tsx` | Same pattern as ACK ALL — needs ISA-18.2 reason dialog |
| 409 enriched with `ack_by` + `ack_at` | `AlarmsController.cs` | So UI can show "Already acknowledged by Mustafa at 14:32:05" |
| Operator presence indicator | Flask (Redis TTL) + React | Shows which operator has an alarm selected |
