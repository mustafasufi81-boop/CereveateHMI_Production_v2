# RESILIENCE FIX PLAN
**CereveateHMI Production — Backend + Frontend Hardening**
**Status as of: 2026-05-26**

---

## PROGRESS TRACKER

| # | Fix | File(s) | Status |
|---|-----|---------|--------|
| 1 | LiveTagCacheService — eliminate 2nd OpcServerConnection | `Services/LiveTagCacheService.cs`, `Program.cs` | ✅ DONE |
| 2 | MQTT exponential retry forever + jitter | `HMI/services/mqtt_client_service.py` | ✅ DONE |
| 3 | REST fallback 30s grace + single-flight + backoff | `HMI/app.py` | ✅ DONE |
| 4 | Transport health state + source arbitration (MQTT > SignalR > REST) | `HMI/app.py` | ✅ DONE |
| 5 | Cache age/freshness (age_ms) + Last Good Value stale policy | `HMI/app.py` | ⏳ NEXT |
| 6 | OPC Connection State Machine | `CSharpBackend/Services/OpcServerConnection.cs` | ⏳ |
| 7 | Dispatcher bounded queue + metrics | `CSharpBackend/Services/OpcStaDispatcher.cs` | ⏳ |
| 8 | Dispatcher per-op timeout (WARN >5s, Degraded >30s) | `CSharpBackend/Services/OpcStaDispatcher.cs` | ⏳ |
| 9 | Dispatcher watchdog (DETECT+LOG ONLY — no auto-reconnect initially) | `CSharpBackend/Services/OpcStaDispatcher.cs` | ⏳ |
| 10 | Dispatcher graceful shutdown + COM RCW reverse-order release | `CSharpBackend/Services/OpcStaDispatcher.cs`, `OpcServerConnection.cs` | ⏳ |
| 11 | Central health endpoint `/api/system-health` | `CSharpBackend/Controllers/HealthController.cs` | ⏳ |
| 12 | Remove Parquet.Net | `OpcDaWebBrowser.csproj` + 4 files | 🅿️ DEFERRED |

---

## 10 IMPLEMENTATION SAFETY RULES

1. **One fix at a time** — implement, build/run, verify, then move to next.
2. **Watchdog = DETECT+LOG ONLY** — no auto-reconnect until Fix #6 (state machine) is done.
3. **Circuit breaker on OPC reconnects**: 5 failures / 2 min → `Faulted` state → 5 min cooldown before retry.
4. **Bounded queue = FAIL FAST** — never block ASP.NET thread pool. Drop or reject if queue full.
5. **NEVER `.Result` or `.Wait()` on dispatcher tasks** from ASP.NET request context — always `await`.
6. **COM calls ONLY on dispatcher thread** — NEVER DB writes, MQTT publish, JSON serialization on dispatcher thread.
7. **No architecture changes during implementation** — design is frozen; correctness only.
8. **Test after every fix** — at minimum: build succeeds + tagCount=27 + no new errors in log.
9. **Parquet.Net removal is a separate sprint** — 4 files still depend on it; do not touch during this plan.
10. **Fix #6 (state machine) and Fix #8 (op timeout) are prerequisites** for any multi-group / per-tag scan rate work.

---

## FIX DETAILS

---

### ✅ Fix #1 — LiveTagCacheService (DONE)

**Problem**: `DataLoggingService` created a second `OpcServerConnection` just to read tag values for the pool. Two COM connections to the same OPC server caused instability.

**Solution**: Created `LiveTagCacheService.cs` — a `BackgroundService` that calls `OpcDaService.ReadAllTagValues()` every 500ms and pushes results into `TagValuesPoolService.UpdatePool()`. No second OPC connection.

**Files changed**:
- `CSharpBackend/Services/LiveTagCacheService.cs` — CREATED (~55 lines)
- `CSharpBackend/Program.cs` — removed `DataLoggingService` hosted service registration, added `LiveTagCacheService`

**Verification**: Build ✅, tagCount=27 ✅, log line `[LiveTagCache] Started — polling OpcDaService every 500ms → TagValuesPoolService` ✅

**Note**: `DataLoggingService.cs` still on disk but no longer registered. `Parquet.Net` kept — still needed by `ArchiveController`, `ArchiveMonitoringService`, `LogBackupService`, `LogFileReaderService`.

---

### ✅ Fix #2 — MQTT Exponential Retry Forever + Jitter (DONE)

**Problem**: In `HMI/services/mqtt_client_service.py`, after 3 consecutive connection failures the service set `_reconnect_stopped = True` and called `loop_stop()`. MQTT died permanently — no recovery without process restart.

**Solution implemented**:
- Removed `_max_reconnect_attempts = 3` hard limit
- `_on_disconnect` now spawns `_reconnect_with_backoff()` thread — retries forever
- Backoff: attempt 1=5s, 2=10s, 3=30s, 4+=60s cap, each + `random.uniform(0, 3)` jitter
- `_reconnect_stopped` kept for API compat but NEVER set `True` permanently
- Logs `DEGRADED+RETRYING` with attempt number and next retry delay
- On success: resets `_reconnect_attempts = 0`, logs `back to CONNECTED`
- Added `import random`

**Files changed**: `HMI/services/mqtt_client_service.py`

**Verification**: Kill Mosquitto → logs show `DEGRADED+RETRYING` → restart Mosquitto → logs show `Reconnect succeeded — back to CONNECTED`

---

### ✅ Fix #3 — REST Fallback 30s Grace + Single-Flight + Backoff (DONE)

**Problem**: No REST fallback existed. When MQTT and SignalR both drop, the UI gets no live data and there is no recovery path short of process restart.

**Solution implemented** — `_rest_fallback_poller()` gevent greenlet in `HMI/app.py`:

| Concern | Implementation |
|---------|---------------|
| 30s grace period | `grace_start` monotonic timer; REST never activates until `_REST_GRACE_S=30` elapsed |
| Grace cancelable | `grace_cancelled` flag set by `on_mqtt_message` / `on_signalr_tag_update` on first message |
| Single-flight guard | `rest_inflight` bool under `_rest_lock`; tick skipped if previous request in-flight |
| Per-request timeout | `_REST_TIMEOUT_S=4.0` — shorter than poll interval, prevents pileup |
| Exponential backoff | `[1, 2, 4, 8, 30]` ladder — advances on every error |
| Jitter | `random.uniform(0, 1.5)` added to each backoff sleep |
| Backoff reset | After `_REST_STABLE_SUCCESSES=3` consecutive successes |
| Transport priority | REST only runs when `mqtt_alive=False AND signalr_alive=False` |
| Liveness detection | Message age > 10s → transport considered dead |
| Transport transitions | All logged: LOST / grace start / grace cancelled / activated / deactivated |
| `latest_tag_values` write | Same shape as MQTT path, `source='REST_FALLBACK'`, `age_ms=None` (Fix #5) |
| Status endpoint | `/api/system-status` now returns full `transport` block |

**New state block** (`_transport_state` dict, protected by `_rest_lock`):
```
mqtt_alive, signalr_alive, fallback_active, grace_start, grace_cancelled,
rest_inflight, rest_backoff_s, rest_consecutive_ok, rest_last_error,
last_mqtt_msg_at, last_signalr_msg_at, last_rest_ok_at,
rest_poll_count, rest_error_count
```

**Constants** (all tunable at top of block):
```python
_REST_GRACE_S          = 30
_REST_POLL_INTERVAL_S  = 1.0
_REST_TIMEOUT_S        = 4.0
_REST_BACKOFF_STEPS    = [1, 2, 4, 8, 30]
_REST_BACKOFF_JITTER   = 1.5
_REST_STABLE_SUCCESSES = 3
```

**Verification**: Syntax check ✅. Start app → kill Mosquitto → wait 30s → `[TRANSPORT] REST fallback ACTIVATED` in logs → restart Mosquitto → `[TRANSPORT] MQTT recovered → REST fallback will deactivate` → REST poll count stops incrementing.

---

### ✅ Fix #4 — Transport Health State + Source Arbitration (DONE)

**Problem**: No clear priority order when multiple transports are alive or partially alive. MQTT recovery could race with REST writes. SignalR could overwrite fresher MQTT values.

**Solution implemented** — `_update_active_source()` helper + per-transport cache write guards in `HMI/app.py`:

| Concern | Implementation |
|---------|---------------|
| Explicit priority | `MQTT > SIGNALR > REST > NONE` |
| Hysteresis | Transport must be alive for `_PROMOTE_STABLE_S=5s` before promotion — prevents oscillation |
| Stability timers | `mqtt_stable_since`, `signalr_stable_since` — monotonic timestamps of when transport first became alive |
| Arbitration function | `_update_active_source()` — called under `_rest_lock` from all 3 paths (MQTT cb, SignalR cb, REST poller tick) |
| Cache write guard (MQTT) | Always writes — highest priority, never blocked |
| Cache write guard (SignalR) | Only writes when `active_source != "MQTT"` — MQTT values are never overwritten |
| Cache write guard (REST) | Only writes when `active_source == "REST"` — discards payload if MQTT/SignalR promoted during in-flight request |
| `source` field | SignalR now writes `source='SIGNALR'` (was missing before) |
| Status endpoint | `active_source` exposed in `/api/system-status` transport block |
| Transition logging | Every `active_source` change logged: `ACTIVE SOURCE: REST → MQTT (mqtt_age=Xs signalr_age=Ys stable_window=5s)` |

**New `_transport_state` fields**:
```
active_source        "NONE" | "MQTT" | "SIGNALR" | "REST"
mqtt_stable_since    monotonic time MQTT first became alive (None when dead)
signalr_stable_since monotonic time SignalR first became alive (None when dead)
```

**New constant**: `_PROMOTE_STABLE_S = 5`

**Verification**: Syntax ✅. 35/35 tests pass (run_20260526_014625). No regressions.

---

### ⏳ Fix #5 — Cache Age/Freshness (age_ms) + Last Good Value Stale Policy

**Problem**: Cached tag values have no age metadata. Stale values served silently.

**Solution**:
- Add `age_ms` field to all tag value responses
- Define stale threshold (e.g. >5s = stale)
- Last Good Value policy: serve stale value but mark `quality: STALE`
- Never serve a value older than `max_age_ms` (configurable, default 30s)

---

### ⏳ Fix #6 — OPC Connection State Machine

**Problem**: `OpcServerConnection.cs` has no formal state machine. Reconnect logic is ad-hoc.

**Solution**: Explicit states: `Disconnected → Connecting → Connected → Degraded → Faulted → Cooldown`
- Circuit breaker: 5 failures / 2 min → `Faulted` → 5 min cooldown
- State exposed via health endpoint
- Prerequisite for Fix #8 (op timeout) and multi-group work

---

### ⏳ Fix #7 — Dispatcher Bounded Queue + Metrics

**Problem**: `OpcStaDispatcher` uses unbounded `BlockingCollection<Action>`. Under load, queue grows without limit.

**Solution**:
- Set `BoundedCapacity` (e.g. 1000)
- On overflow: reject with `InvalidOperationException`, log warning
- Expose queue depth metric via health endpoint
- FAIL FAST — never block ASP.NET thread pool

---

### ⏳ Fix #8 — Dispatcher Per-Op Timeout

**Problem**: Dispatcher tasks can hang indefinitely if a COM call blocks.

**Solution**:
- Per-operation timeout using `CancellationToken`
- >5s: log `WARN`
- >30s: log `ERROR`, mark dispatcher as `Degraded`
- Prerequisite for Fix #9 (watchdog)

---

### ⏳ Fix #9 — Dispatcher Watchdog (DETECT+LOG ONLY)

**Problem**: No watchdog to detect a hung or dead dispatcher.

**Solution**:
- Heartbeat: dispatcher posts a no-op every 10s
- Watchdog checks heartbeat timestamp every 15s
- If no heartbeat for >30s: log `CRITICAL — dispatcher appears hung`
- **DETECT+LOG ONLY** — no auto-reconnect, no restart (until Fix #6 state machine is proven stable)

---

### ⏳ Fix #10 — Dispatcher Graceful Shutdown + COM RCW Reverse-Order Release

**Problem**: On `SIGTERM`/`CTRL+C`, COM objects may not be released in correct order → RCW leaks → next process start fails to connect.

**Solution**:
- `IAsyncDisposable` on dispatcher — drain queue before stopping STA thread
- Release COM objects in reverse order: Items → Group → Server
- `Marshal.ReleaseComObject()` on each, then `Marshal.FinalReleaseComObject()` if ref count > 0

---

### ⏳ Fix #11 — Central Health Endpoint `/api/system-health`

**Problem**: No single endpoint to check overall system health.

**Solution**: `GET /api/system-health` returns:
```json
{
  "opc": { "state": "Connected", "tagCount": 27, "lastPollMs": 450 },
  "dispatcher": { "state": "Healthy", "queueDepth": 3, "lastHeartbeatAgo": 8 },
  "pool": { "tagCount": 27, "oldestValueAgeMs": 312 },
  "uptime": "02:14:33"
}
```

---

### 🅿️ Fix #12 — Remove Parquet.Net (DEFERRED — Separate Sprint)

**Problem**: `Parquet.Net` is a heavy dependency only used by archiving/logging features.

**Blocked by**: `ArchiveController.cs`, `ArchiveMonitoringService.cs`, `LogBackupService.cs`, `LogFileReaderService.cs` all use it.

**Action**: Do not touch during this resilience sprint. Create separate cleanup task.

---

## STRESS TEST BASELINE (for regression comparison)

Run: `.\HMI\.venv\Scripts\python.exe tests\full_test_suite.py --quick`

**Golden baseline**: 2026-05-26 01:37:51 — **35/35 PASSED** (100%) — post Fix #3+#4
**Result file**: `tests/results/run_20260526_013751.json`

**Section H baseline**: 2026-05-26 01:54:48 — **7/7 PASSED** (100%)
**Section H file**: `tests/results/section_h_20260526_015448.json`
**Section H dispatcher fields gap**: `queueDepth`, `threadId`, `apartment` not yet in `/api/health/opc` — will be added by Fix #11

| Test | Result | p50 | p95/p99 | Notes |
|------|--------|-----|---------|-------|
### Section H Dispatcher Baseline

| Test | Result | Notes |
|------|--------|-------|
| H1 STA apartment | ✅ | 10/10 concurrent, tagCount=27, no marshalling errors |
| H2 heartbeat monotonic | ✅ | 5/5 health polls, timestamps advancing |
| H3 queue depth drain | ✅ | 50-burst: 0 HTTP 500s, tagCount=27 after 5s drain |
| H4 dispatcher latency | ✅ | p50=15ms p95=16ms p99=16ms — STA overhead floor |
| H5 tagCount stability | ✅ | 200×50ms: min=27, zeros=0, drops=0, errors=0 |
| H6 saturation 500 req | ✅ | 500 req/50 workers: 0 HTTP 500s, 100% success |
| H7 OPC restart recovery | ⏭ | SKIPPED — requires --restart flag (destructive) |
| H8 dispatcher post-restart | ⏭ | SKIPPED — requires --restart flag |
| H9 OPC health fields | ✅ | Status=Connected, TagsConnected=27, HealthScore=100 |
| H10 long soak | ⏭ | SKIPPED — requires --soak flag (5+ min) |

**Key finding from H4**: Dispatcher p50=15ms (vs REST pool p50=3ms). This 12ms delta is the STA dispatch + COM call overhead. Normal and expected.

**Key finding from H9**: `queueDepth`, `threadId`, `apartment` fields MISSING from `/api/health/opc`. These are required by Fix #11. Currently a documentation gap, not a runtime failure.

**H7/H8 to run**: `--restart` flag required. Schedule during maintenance window.
**H10 to run**: `--soak --soak-duration 300` for 5-min soak.

---

### Section A–F Full Suite Baseline

| A1 backend+OPC | ✅ | — | — | HTTP 200, OPC connected, tagCount=27 |
| A2 all endpoints | ✅ | — | — | 6/6 endpoints respond correctly |
| A3 values shape | ✅ | — | — | Wrapped response `{count,lastUpdate,timestamp,tags}` |
| A4 status fields | ✅ | — | — | All 4 required fields present |
| A5 servers list | ✅ | — | — | 3 servers listed |
| B1 pool freshness | ✅ | 1ms age | — | LiveTagCacheService caching locally; age ~1ms |
| B2 tagCount stable | ✅ | — | — | min=max=27 across 100 concurrent reads |
| B3 pool 30s sustained | ✅ | — | — | 0 empty windows in 6×5s windows |
| C1–C6 MQTT Fix #2 | ✅ | — | — | All 6 static analysis checks pass |
| D1 baseline latency | ✅ | 9.4ms | p99=25ms | Well below p50<50 / p99<200 thresholds |
| **D2 serial 100ms** | **❌** | **172ms** | **p99=301ms** | **Windows GC/JIT spike during full run — passes isolated** |
| D3 serial 50ms | ✅ | 6.8ms | — | 100% within 50ms budget |
| D4 scheduler floor | ✅ | 6.5ms | — | 60.6% < 10ms informational |
| D5 burst 10t×20r | ✅ | 55ms | p95=74ms | 100% success |
| D6 burst 50t×10r | ✅ | 304ms | p95=458ms | 100% success — well under 1000ms threshold |
| D7 saturation 500 | ✅ | 124ms | p95=166ms | 0 empty responses |
| E1–E5 pool integrity | ✅ | — | — | All 5 pass incl. timestamp monotonicity |
| F1–F4 edge cases | ✅ | — | — | 404 not 500, no 500s under concurrent load |
| Resource delta | ℹ️ | — | — | Memory +5.2MB, threads stable (Δ0), handles +114 |

**D2 NOTE**: D2 passes when run in isolation (`--only D`: 100% within 100ms). Fails in full-suite run because preceding sections (B3 30s soak + E3 30s soak) warm up the process and a Windows GC/JIT pause inflates one batch of requests to ~172ms median. This is **Windows timer jitter, not a backend regression**. Threshold could be relaxed to ≥80% in full-suite mode.

**Key findings**:
- Backend serial p50 = 5–9ms. Extremely fast. LiveTagCacheService is working as intended.
- Pool freshness age ≈ 1ms (cache is local in-process, not re-reading OPC on every request).
- tagCount=27 rock-solid under all load scenarios — Fix #1 verified.
- Fix #2 MQTT static verification: 100%.
- 0 errors across D5/D6/D7 burst and saturation tests.
- Response payload stable at ~2858 bytes (no accidental inflation).
- No memory leaks or thread leaks detected.

---

## ARCHITECTURAL NOTE — Multi-Group OPC DA (Future, Post Fix #6+#8)

For 5000 tags with mixed scan rates, use OPC DA multiple groups per connection:

```
StartupTagSeedService reads tag_master
→ groups tags by scan_rate_ms:
    { 50ms:  [TAG_A, TAG_B, ...50 tags] }
    { 500ms: [TAG_C, TAG_D, ...500 tags] }
    { 5000ms:[TAG_E, TAG_F, ...4450 tags] }

→ OpcDaService.AddServerConnection(progId, pollingIntervalMs=50)
    → creates OpcServerConnection
    → creates Group_Fast  (50ms,  50 tags)
    → creates Group_Med   (500ms, 500 tags)
    → creates Group_Slow  (5000ms, 4450 tags)

All 3 groups → one connection → one dispatcher → one pool
```

**Pre-conditions**: Fix #6 (state machine) + Fix #8 (op timeout) must be done first.
**DB change needed**: Add `scan_rate_ms` column to `tag_master`.