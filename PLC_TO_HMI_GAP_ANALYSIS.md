# PLC → HMI Data Flow — Gap Analysis (Code-Verified)
**Date:** 2026-05-27  
**Scope:** Why live values appear frozen, why fallback does not activate, why no alert when data freezes.  
**Status:** Analysis only. No code changes. No git operations. No assumptions — every claim references an exact file and line.

---

## 0. Reading guide

This document is structured to map directly to the four issues you raised:

1. **Issue 1** — Data does not flow correctly from PLC to HMI  → §3, §4, Gap 1, Gap 2, Gap 6
2. **Issue 2** — When data freezes, no alert is raised        → §5, Gap 3, Gap 4
3. **Issue 3** — Fallback is not activated                    → §6, Gap 5
4. **Issue 4** — Make sure we connect correctly               → §7, Gap 1, Gap 7

Every gap entry contains: **Symptom → Root cause (file:line) → Minimal targeted fix → Risk → Verification**.  
None of the fixes are written into code yet. This is a plan you approve before I touch anything.

---

## 1. Components on disk (verified)

| Layer | File | Role |
|---|---|---|
| C# driver | `CSharpBackend/Services/PlcGateway/Drivers/RockwellDriver.cs` | EtherNet/IP read via libplctag |
| C# worker | `CSharpBackend/Services/PlcGateway/Services/PlcWorker.cs` (800 lines) | One Task per PLC, polling loop, backoff, circuit breaker |
| C# pool   | `CSharpBackend/Services/PlcGateway/Services/PlcTagValuesPoolService.cs` | `ConcurrentDictionary` cache, per-PLC `_connectionStatus` |
| C# config | `CSharpBackend/Services/PlcGateway/Services/PlcConfigLoaderService.cs` | Reads `historian_meta.tag_master`, fallback to `appsettings.json` |
| C# transport | `CSharpBackend/Services/PlcGateway/Transport/MqttPublisher.cs` + `MultiProtocolPublisherService.cs` | Publishes `{PlcId}/tags/bulk` |
| C# REST   | `CSharpBackend/Services/PlcGateway/Controllers/PlcController.cs` (2089 lines) | `/api/plc/values`, `/api/plc/connections`, `/api/plc/diagnostics` |
| C# config file | `CSharpBackend/appsettings.json` | `PlcGateway.Connections: []` ← **empty (verified line 78)** |
| Python proxy | `HMI/controllers/system_controller.py` | `/api/plc/values` proxy to C# :5001 |
| Python MQTT cb | `HMI/app.py` line 917 `on_mqtt_message` | Stamps liveness, updates `latest_tag_values`, broadcasts Socket.IO |
| Python REST fallback | `HMI/app.py` line 1515 `_rest_fallback_poller` | Activates only when MQTT + SignalR both dead for 30s |
| Python status proxy | `HMI/app.py` line 342 `/api/opc-plc-status` | Combines `/api/health/opc` + `/api/plc/connections` |
| React health hook | `HMI/apex-hmi/src/hooks/useConnectionHealth.ts` | RED/ORANGE/GREEN banner |
| React PLC status hook | `HMI/apex-hmi/src/hooks/useOpcPlcStatus.ts` | Per-PLC badges (polls `/api/opc-plc-status` every 10s) |
| React polling | `HMI/apex-hmi/dist/assets/index-CzoO-1IB.js` line 521 | **Browser fetches `/api/plc/values` every 1000 ms unconditionally** |

---

## 2. Actual end-to-end data flow (as built)

```
                ┌──────────────────────────────────────────────────┐
                │  Physical PLC  192.168.0.20:44818                │
                │  (currently: NOT WIRED — confirmed in            │
                │   PLC_COMM_ARCHITECTURE.md §1)                   │
                └────────────────────┬─────────────────────────────┘
                                     │ libplctag CIP
                                     ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │ PlcWorker.PollingLoopAsync()                                    │
   │   - If driver.IsConnected == false → ConnectWithRetryAsync()    │
   │   - On read success  → PlcTagValuesPoolService.UpdateFromPlc()  │
   │   - On read failure  → HandlePollFailure() → MarkPlcDisconnected│
   │   - On connect fail  → NO call to MarkPlcDisconnected (Gap 4)   │
   └─────────────────────────────────────────────────────────────────┘
                                     │
                          ┌──────────┴──────────┐
                          ▼                     ▼
   PlcTagValuesPoolService               PlcSampleBufferService
   (in-memory cache)                     │
   key = "{PlcId}::{Address}"            ▼
   - never evicts entries          MultiProtocolPublisherService
   - on disconnect: marks          → MqttPublisher → mosquitto:1883
     Quality=Uncertain only        Topic: {PlcId}/tags/bulk
   - serves last-known forever
   │
   │ GET /api/plc/values        GET /api/plc/connections
   ▼                            ▼
   ┌────────────────────────────────────────────┐
   │ HMI Flask (:6001 / :8090)                  │
   │                                            │
   │  /api/plc/values  (system_controller.py)   │  ← React polls this every 1s
   │     proxies C# /api/plc/values (timeout=3) │
   │     returns whatever pool returns          │
   │                                            │
   │  on_mqtt_message (app.py:917)              │
   │     stamps liveness, updates               │
   │     latest_tag_values{}, broadcasts        │
   │     socketio.emit('mqtt_tag_update')       │
   │                                            │
   │  _rest_fallback_poller (app.py:1515)       │
   │     only activates if MQTT+SignalR dead    │
   │     for >30s. Polls C# /api/plc/values     │
   │     and pushes via socketio 'tag_update'   │
   │                                            │
   │  /api/opc-plc-status (app.py:342)          │
   │     combines /api/health/opc + connections │
   └────────────────────────────────────────────┘
                                     │
                                     ▼
   ┌────────────────────────────────────────────┐
   │ React (apex-hmi)                           │
   │  - Socket.IO listener (mqtt-websocket.ts)  │
   │    stamps lastDataReceivedAt on every      │
   │    socket event; dataIsStale=true after    │
   │    60 s without ANY socket event           │
   │  - fetch('/api/plc/values') every 1s       │
   │    UPDATES THE TILES regardless of socket  │
   │  - useOpcPlcStatus polls 10 s              │
   │  - useConnectionHealth → RED/ORANGE/GREEN  │
   └────────────────────────────────────────────┘
```

**Critical observation:** the browser tiles are updated by **two independent paths** — (a) Socket.IO `mqtt_tag_update`/`tag_update` events, and (b) a 1-second direct REST poll to `/api/plc/values`. Path (b) runs unconditionally and is what you are seeing in the UI right now.

---

## 3. Why the value is "fixed and not changing" (Issue 1)

When the physical PLC is unreachable, the system enters this exact state — verified against the code:

1. `PlcWorker.PollingLoopAsync` (PlcWorker.cs:208) sees `_driver.IsConnected == false`.
2. Enters backoff (30 s → 60 s → 120 s). Polling DOES NOT happen during backoff (PlcWorker.cs:233-248).
3. `PlcTagValuesPoolService._cache` is **not cleared** and **not aged-out**. Any previously cached entries stay forever (PlcTagValuesPoolService.cs:170 `GetAllTagValues` — pure `_cache.Values.ToList()`).
4. `MarkPlcDisconnected` only sets `Quality = Uncertain` on existing entries (PlcTagValuesPoolService.cs:100-107) — it does not remove them.
5. C# `/api/plc/values` (PlcController.cs:60) returns those frozen values with `computedQuality` and `age_ms` fields.
6. HMI proxy `proxy_plc_values` (`system_controller.py:74`) copies every field via `dict(t)` and returns them.
7. React renders **only `value`** (verified in the built `dist/assets/index-CzoO-1IB.js`). The `quality`, `computedQuality` and `age_ms` fields are ignored.

**Net effect:** the browser keeps drawing the same numbers forever because the cache keeps serving them and React does not respect freshness metadata.

There is a second contributor: if the PLC has **never** successfully connected since process start, the cache is filled by the database seed in `_seed_tag_cache_from_db()` (app.py:649 — reads `historian_raw.historian_latest_value` within the last hour). Those DB-seeded values are written to `latest_tag_values` with `source='DB_SEED'` and never get refreshed when no MQTT messages arrive. That is *exactly* the "frozen value" pattern described.

---

## 4. Why MQTT is silent in this state

`MqttPublisher` only publishes a batch when `PlcSampleBufferService` has samples. The sample buffer is filled **only inside the `readResult.Success` branch** of the polling loop (PlcWorker.cs:351-376). With no successful reads:

- No samples are buffered.
- `MultiProtocolPublisherService` publishes empty/no batches.
- Python `on_mqtt_message` is never called for that PLC.
- `_transport_state["last_plc_mqtt_msg_at"]` stays `None`.
- Liveness goes false after `_LIVENESS_TIMEOUT_S = 10 s` (app.py:1547).

So MQTT silence is the *correct* downstream consequence of the upstream condition (PLC offline). The system does, however, fail to *act* on that silence in a user-visible way.

---

## 5. Why no alert is raised when data freezes (Issue 2)

There are three nested signals, and each has a hole:

### 5.1 React `useConnectionHealth` — `dataIsStale`
- Defined in `mqtt-websocket.ts:13` as `STALE_DATA_THRESHOLD_MS = 60_000`.
- `lastDataReceivedAt` is stamped **only on Socket.IO events** (mqtt-websocket.ts:179, 191). It is **not stamped on the 1-second REST fetch**.
- Therefore, if MQTT/SignalR are dead but REST polling keeps returning the same cached values, after 60 s the banner correctly goes ORANGE ("Data Update Delayed").
- **Gap:** "stale" is global, not per-PLC. There is no "PLC X went stale 95 s ago" indicator.
- **Gap:** the banner is also bypassed because the tiles continue to render REST values, so the operator visually believes the system is live.

### 5.2 React `useOpcPlcStatus` — per-PLC `connected` badge
- Polls `/api/opc-plc-status` every 10 s (useOpcPlcStatus.ts:36).
- Renders one orange badge per PLC where `connected === false`.
- This **does** work when the C# backend reports a PLC as disconnected.
- **Gap A:** if the C# backend has **no PLC worker at all** (because `appsettings.json` has `Connections: []` and `historian_meta.tag_master` has no PLC rows — see §7 below), then `/api/plc/connections` returns an empty list and `plcs: []` reaches the React hook. No badges are shown. **Silent disconnect.**
- **Gap B:** `dataIsStale` (transport-level) and `plc.connected` (per-PLC) are computed independently. There is no rule "if PLC reports connected but its tags are >N seconds stale → mark stale on that PLC's tile". So a PLC can be `connected:true` while its tags have not updated for an hour.

### 5.3 Pool-level staleness in C#
- `PlcTagValuesPoolService.IsHealthy()` (PlcTagValuesPoolService.cs:267) considers the pool stale after 30 s of no updates — but **this value is not exposed in `/api/plc/connections`**. Nobody downstream consumes it.
- `PlcTagValueCacheEntry.ComputedQuality` (PlcTagValuesPoolService.cs:339) upgrades `Good` → `Stale` at `age_ms > 10_000`. **Short-circuit bug:** if `Quality != Good` (e.g. `Uncertain` after `MarkPlcDisconnected`) it returns the original quality and *never* becomes `Stale`. So an offline PLC's cached values report `quality=Uncertain` but the React layer treats only `computedQuality=Stale` as a freshness flag.

---

## 6. Why the fallback is not activated (Issue 3)

`_rest_fallback_poller` in `HMI/app.py:1515` activates only when **both** of these are true for **at least 30 s**:

```python
mqtt_ok = last_mqtt_msg_at is not None and (now - last_mqtt_msg_at) < 10.0
sig_ok  = last_signalr_msg_at is not None and (now - last_signalr_msg_at) < 10.0
live_transport = mqtt_ok or sig_ok
# if live_transport → fallback never activates
```

Scenarios where it does not activate even though data is frozen:

- **A. MQTT is alive but only carrying OPC traffic.** `last_mqtt_msg_at` is updated on **every** MQTT message regardless of topic (app.py:927). So a single OPC publish keeps `mqtt_alive=True` indefinitely, and the REST fallback never starts — even if the PLC topic has been silent for hours. The PLC-specific timer `last_plc_mqtt_msg_at` exists (app.py:929-931) but is **not** consulted in the fallback decision (line 1554-1556).
- **B. SignalR is alive.** Same blocker — any SignalR heartbeat keeps `sig_ok=True`.
- **C. There is no React-side fallback activation indicator.** Even when the Python fallback *does* activate, `useConnectionHealth` does not know — the only signal it consumes is "did a Socket.IO message arrive". So the orange "Using Backup Connection" only triggers when Flask itself becomes unreachable, not when the Python REST fallback is the active source.

Net effect: in the most common failure mode (PLC offline, OPC still publishing), Python REST fallback **stays off**, and even if it ran, the React UI is already REST-polling C# directly at 1 Hz — so the fallback would be redundant and invisible.

---

## 7. Why connection correctness cannot be guaranteed today (Issue 4)

### 7.1 Config source is single-point-of-failure

`appsettings.json` confirmed:
```json
"PlcGateway": {
  "Connections": [],          // ← empty, line 78
  ...
}
```
The only remaining config source is `historian_meta.tag_master` (PlcConfigLoaderService).  
If the DB has zero PLC rows, **no `PlcWorker` is ever created**:
- `PlcGatewayManager._workers` stays empty.
- `_gatewayManager.GetAllStatus()` → `[]`.
- `_tagPool.GetPlcStatus()` → `{}`.
- `/api/plc/connections` returns `{ connections: [], totalCount: 0 }`.
- React banner shows nothing. **System looks healthy but is doing nothing.**

### 7.2 Connect-time failures do not propagate

`ConnectWithRetryAsync` (PlcWorker.cs:510) on failure:
- Increments `_consecutiveFailures` and sets `_lastError`.
- Does **not** call `_sharedPool?.MarkPlcDisconnected(...)`.

Result: the very first time a PLC fails to connect at startup, the **pool** never learns about that PLC at all (`_connectionStatus[plcId]` is never written). The only place that record is created is `UpdateFromPlc` (PlcTagValuesPoolService.cs:69), which is only called after a *successful* read. So the pool's connection map has only ever-successful PLCs.

`PlcController.GetConnections` (PlcController.cs:331) merges three sources and the runtime source still sees the worker, so a row does appear in `/api/plc/connections` — but its `lastError` from `pool` will be `null` (because the pool has no record), and the React badge will say "NOT CONNECTED" only if the runtime row exists. If for some reason the worker was never created (see §7.1), nothing appears.

### 7.3 Ambiguous "connected" semantics

`PlcWorkerStatus.IsConnected = _driver.IsConnected` (PlcWorker.cs:706). The driver reports `IsConnected=true` after `ConnectAsync()` succeeds, but it does **not** verify that subsequent reads succeed. A TCP session that has gone half-open (typical with industrial gear after a switch reboot) will still report `IsConnected=true` until the next read fails. During that window, `/api/plc/connections` lies.

---

## 8. Gap register (the only thing that needs fixing)

Each gap is **independent** — none of them depends on another. They can be addressed one by one.

### Gap 1 — Pool serves stale data forever (HIGH)
**Where:** `PlcTagValuesPoolService.GetAllTagValues()` and `GetPlcValues()`.  
**Symptom:** values frozen on the screen.  
**Targeted fix (no architecture change):**  
- In `GetAllTagValues` / `GetPlcValues`, project entries through a helper that recomputes `Quality`:
  - if `age_ms > stale_threshold_ms` (suggest 10 000 ms): force `Quality = Stale`.
  - **Fix the short-circuit bug** in `ComputedQuality` (PlcTagValuesPoolService.cs:329-340): the check `if (Quality != Good) return Quality;` must allow `Uncertain` to become `Stale` once age exceeds threshold.
- Keep the `Value` field. Do not delete entries — historical zero-flicker is worse than stale-with-flag.
- Optionally evict entries older than `max_age_ms` (suggest 300 000 ms = 5 min) so disconnected PLC keys disappear from queries after long outages.

**Risk:** low. Pure read-side computation, no writer touched.  
**Verification:** with C# running and no PLC, hit `GET /api/plc/values` — every entry should show `computedQuality:"Stale"` and `age_ms` > 10000.

### Gap 2 — React ignores `quality` / `age_ms` (HIGH)
**Where:** the built React bundle reads only `value` from `/api/plc/values` and the Socket.IO payload.  
**Symptom:** tiles render the same number with no visual difference between "live 1 s ago" and "frozen 3 h ago".  
**Targeted fix:**  
- In the source TS file that renders the tag tiles (the source for `index-CzoO-1IB.js` — needs to be located in `apex-hmi/src/...` and confirmed before editing), use `computedQuality` or `age_ms` to:
  - grey out the tile and overlay "STALE Xs" badge when `computedQuality !== 'Good'` or `age_ms > 10_000`.
- No change to data path. Display-only.

**Risk:** low.  
**Verification:** unplug the PLC (or stop the C# backend); tiles should turn grey within 10 s.

### Gap 3 — `dataIsStale` only stamps on Socket.IO events (MEDIUM)
**Where:** `mqtt-websocket.ts:179, 191`.  
**Symptom:** the 1 Hz REST poll keeps the screen looking alive, but `dataIsStale` only flips after 60 s of Socket.IO silence — and even then is not per-PLC.  
**Targeted fix:**  
- Stamp `lastDataReceivedAt` from the REST polling code path **only when at least one returned tag has `age_ms < threshold`** (i.e. the response itself contains fresh data). A 200-OK response full of stale entries must NOT reset the stale timer.
- Add a per-PLC freshness map (key: `plcId`, value: most-recent `age_ms` across that PLC's tags) and surface it in `useConnectionHealth` so a single stale PLC is visible without affecting the global LIVE/STALE indicator.

**Risk:** low/medium. Touches the React service that drives the banner. Test in isolation.  
**Verification:** with PLC offline but REST returning stale data, banner goes ORANGE within 60 s; with at least one fresh tag, banner stays GREEN.

### Gap 4 — Connect-time failure does not register the PLC in the pool (MEDIUM)
**Where:** `PlcWorker.ConnectWithRetryAsync` (PlcWorker.cs:510-555) — no call to `_sharedPool?.MarkPlcDisconnected`.  
**Symptom:** if a PLC has never connected, the pool has no record of it; `/api/plc/connections` data merging logic relies on the runtime source only.  
**Targeted fix:**  
- After the for-loop in `ConnectWithRetryAsync` finishes without success, call `_sharedPool?.MarkPlcDisconnected(PlcId, _lastError)`. This makes the pool's `_connectionStatus[plcId]` entry exist from the very first failed attempt with `IsConnected=false` and the real error string.

**Risk:** very low. Pure additive.  
**Verification:** start C# with an unreachable PLC IP → `GET /api/plc/connections` shows the PLC with `isConnected:false` and a `lastError` within 1 polling cycle.

### Gap 5 — REST fallback liveness uses the wrong timer (MEDIUM)
**Where:** `_rest_fallback_poller` in `HMI/app.py:1554-1556` uses `last_mqtt_msg_at`, which is set on **any** MQTT topic (OPC or PLC).  
**Symptom:** if OPC is publishing but PLC topic is silent, fallback never activates for PLC.  
**Targeted fix:**  
- Decide at the fallback level which sources are required:
  - For PLC fallback: use `last_plc_mqtt_msg_at` (already tracked at app.py:931).
  - Keep `last_mqtt_msg_at` for OPC.
- Replace the single `mqtt_ok` with two checks: `mqtt_opc_ok` and `mqtt_plc_ok`. Activate fallback for the silent side independently.
- Alternatively (simpler): change the meaning of `last_mqtt_msg_at` to require *at least one PLC topic message*, but this would regress OPC fallback semantics — not recommended.

**Risk:** medium. Touches an already-fragile state machine. Apply only after Gap 4 is verified to avoid masking it.  
**Verification:** with OPC publishing but PLC offline for >40 s, Python log shows `[TRANSPORT] PLC REST fallback ACTIVATED`.

### Gap 6 — DB-seeded values pollute the cache (HIGH)
**Where:** `_seed_tag_cache_from_db()` in `app.py:649`.  
**Symptom:** even if MQTT never delivers a single PLC tag, `latest_tag_values` is pre-populated from `historian_raw.historian_latest_value` (up to 1 hour old). Socket.IO snapshot on connect returns these values; React renders them as if they were live.  
**Targeted fix:**  
- On seed: write `quality='STALE'`, `source='DB_SEED'`, and **stamp `age_ms` from the DB row's `last_time`**. Today only `source` and `quality` ('G') are written, and React does not respect quality.
- In the Socket.IO `snapshot` emit path, the same Gap 2 fix in React will then hide/grey these tiles correctly.

**Risk:** very low (only changes the data we write into the seed entries).  
**Verification:** restart Flask with no live MQTT; connect a browser; tiles render with STALE indicator.

### Gap 7 — Empty config = silent system (CRITICAL but operational)
**Where:** `appsettings.json` line 78 — `Connections: []`. Combined with no DB rows.  
**Symptom:** zero workers, zero alerts, blank UI considered "healthy".  
**Targeted fix:** *not a code fix; an operational/start-up fix.*  
- Add a startup invariant check in `PlcGatewayHostedService.LoadAndStartPlcsAsync()` — after config load, if zero PLCs are configured, log `CRITICAL: no PLC configured (DB has 0 rows and appsettings Connections is empty)` and emit it through the health endpoint as a top-level `state: "NoPlcConfigured"`.
- Surface that state in `/api/opc-plc-status` so the React banner can render a distinct RED message: "No PLC configured — contact engineering".
- Independently: restore one known-good entry in `appsettings.json.Connections` as the fallback path documented in `PLC_COMM_ARCHITECTURE.md` §2.3 (the doc says it has 5 tags but the file is empty — doc and reality disagree).

**Risk:** low.  
**Verification:** clear DB PLC rows and `Connections:[]` → start C# → `GET /api/plc/connections` returns the new `state` and React banner shows the new message.

---

## 9. Recommended sequencing (smallest blast radius first)

I will **not** start any of these until you approve the order. The recommended order is:

1. **Gap 4** (C# pool registers connect-time failures) — additive, 5 lines, builds trust in `/api/plc/connections`.
2. **Gap 1** (Pool stale-quality recompute + ComputedQuality bug fix) — read-side only.
3. **Gap 6** (DB-seed marks STALE + age_ms) — Python-only, no impact on C#.
4. **Gap 2** (React respects quality/age) — display-only.
5. **Gap 3** (React stale timer respects payload freshness, per-PLC) — depends on Gap 1+2 being live.
6. **Gap 5** (REST fallback uses PLC-specific timer) — verify after Gap 4 so we're not papering over Gap 4.
7. **Gap 7** (NoPlcConfigured top-level state + restore one fallback entry) — operational + small code.

After each step: build C#, restart, hit the verification curl, then move on. No batched edits. No git.

---

## 10. What this document does **not** do

- It does not include any line of code.
- It does not modify `appsettings.json`, `app.py`, `PlcWorker.cs`, `PlcTagValuesPoolService.cs`, `PlcController.cs`, or any React file.
- It does not touch git. Nothing committed, nothing pushed, nothing fetched from history.
- It does not propose architecture changes — every fix is local to a single file and a small region.

When you say "go", I will execute exactly Gap 4 first, verify, and stop.
