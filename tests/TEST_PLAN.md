# CEREVEATE HMI — MASTER TEST PLAN
**Production Resilience Validation**
**Last updated: 2026-05-26**

---

## STATUS LEGEND
| Symbol | Meaning |
|--------|---------|
| ✅ | Implemented + passing |
| ⏳ | Planned, not yet implemented |
| 🔴 | CRITICAL gap — must implement before production |
| 🟡 | Important — implement this sprint |
| 🔵 | Future / next sprint |
| ❌ | Blocked by prerequisite |

---

## WHAT EACH TEST FILE COVERS

| File | Purpose |
|------|---------|
| `tests/full_test_suite.py` | API coverage, Fix #1/#2 verification, OPC performance, pool integrity, edge cases, soak |
| `tests/opc_stress_test.py` | Original stress + 10ms feasibility analysis (retained for regression) |

Run full suite:
```
.\HMI\.venv\Scripts\python.exe tests\full_test_suite.py
.\HMI\.venv\Scripts\python.exe tests\full_test_suite.py --quick        # skip 30s soak
.\HMI\.venv\Scripts\python.exe tests\full_test_suite.py --only C       # Fix #2 only
.\HMI\.venv\Scripts\python.exe tests\full_test_suite.py --soak 120     # 2 min soak
```

---

## SECTION A — Pre-flight & API Coverage
**File**: `full_test_suite.py` — Section A
**Status**: ✅ Implemented

| ID | Test | Status |
|----|------|--------|
| A1 | Backend reachable, OPC connected, tagCount=27 | ✅ |
| A2 | All REST endpoints return valid HTTP codes | ✅ |
| A3 | /api/opc/values shape — 27 tags, correct fields | ✅ |
| A4 | /api/opc/status fields — connected, tagCount, serverName, lastUpdate | ✅ |
| A5 | /api/opc/servers non-empty list | ✅ |

---

## SECTION B — Fix #1 Verification (LiveTagCacheService)
**File**: `full_test_suite.py` — Section B
**Status**: ✅ Implemented

| ID | Test | Status |
|----|------|--------|
| B1 | Pool freshness — lastUpdate age <1500ms over 10s | ✅ |
| B2 | tagCount stable under concurrent load (no drops = no 2nd OPC connection race) | ✅ |
| B3 | Pool populated continuously over 30s — no empty windows | ✅ |

---

## SECTION C — Fix #2 Verification (MQTT Exponential Retry)
**File**: `full_test_suite.py` — Section C
**Status**: ✅ Implemented (static analysis + logic tests)

| ID | Test | Status | Notes |
|----|------|--------|-------|
| C1 | _reconnect_stopped never permanently set True | ✅ | Static analysis |
| C2 | Backoff schedule [5,10,30,60] present | ✅ | Static analysis |
| C3 | _reconnect_with_backoff method + import random + jitter | ✅ | Static analysis |
| C4 | _on_disconnect does NOT call loop_stop on failures | ✅ | Static analysis |
| C5 | Reconnect thread spawned in _on_disconnect | ✅ | Static analysis |
| C6 | Backoff math unit test (attempt → correct delay) | ✅ | Logic test |
| C7 | **LIVE: Kill Mosquitto → DEGRADED+RETRYING in logs** | ⏳ | Manual / live test |
| C8 | **LIVE: Restart Mosquitto → auto-reconnects, logs "back to CONNECTED"** | ⏳ | Manual / live test |

**NOTE**: C7/C8 require Mosquitto broker control. Run manually:
1. `net stop mosquitto`
2. Watch Python app logs for `DEGRADED+RETRYING`
3. `net start mosquitto`
4. Confirm `Reconnect succeeded — back to CONNECTED`

---

## SECTION D — OPC REST Performance (Cache Layer)
**File**: `full_test_suite.py` — Section D
**Status**: ✅ Implemented

| ID | Test | What is actually stressed | Threshold | Status |
|----|------|--------------------------|-----------|--------|
| D1 | Baseline idle 50×100ms | ASP.NET + JSON + ConcurrentDict | p50<50ms, p99<200ms | ✅ |
| D2 | Serial 100ms for 5s | REST cache read throughput | ≥95% within 100ms | ✅ |
| D3 | Serial 50ms for 5s | REST cache read throughput | ≥90% within 50ms | ✅ |
| D4 | Serial 10ms for 3s (feasibility) | Windows timer floor | p50<50ms | ✅ |
| D5 | Concurrent 10t×20r | ASP.NET thread pool + cache | success≥99%, p95<500ms | ✅ |
| D6 | Concurrent 50t×10r | ASP.NET thread pool saturation | success≥95%, p95<1000ms | ✅ |
| D7 | Saturation 500 req/20 workers | **REST cache saturation** (NOT dispatcher) | success≥95%, empty=0 | ✅ |

> ⚠️ **IMPORTANT NAMING NOTE (from expert review)**:
> D5/D6/D7 stress the **REST cache layer** (ConcurrentDictionary + JSON serialization + ASP.NET thread pool).
> They do NOT stress the **OPC dispatcher/STA/COM layer** — that requires a dedicated dispatcher-ping endpoint.
> This is a KNOWN gap — see Section H.

---

## SECTION E — Pool Integrity
**File**: `full_test_suite.py` — Section E
**Status**: ✅ Implemented

| ID | Test | Status |
|----|------|--------|
| E1 | All 27 tags present in /api/opc/values | ✅ |
| E2 | Tag value objects have required fields (id, value, timestamp) | ✅ |
| E3 | Pool freshness 30s sustained — 0 stale events (age >1500ms) | ✅ |
| E4 | No empty responses (tag_count=0) in 200 rapid parallel reads | ✅ |

---

## SECTION F — Endpoint Edge Cases
**File**: `full_test_suite.py` — Section F
**Status**: ✅ Implemented

| ID | Test | Status |
|----|------|--------|
| F1 | Unknown route → 404/400, not 500 | ✅ |
| F2 | Status endpoint: 20t×10r concurrent — no 500 errors | ✅ |
| F3 | Content-Type: application/json on values endpoint | ✅ |
| F4 | 100 concurrent threads × 1 request — success ≥95% | ✅ |

---

## SECTION G — Soak Test
**File**: `full_test_suite.py` — Section G
**Status**: ✅ Implemented (30s default, configurable)

| ID | Test | Status |
|----|------|--------|
| G1 | 30s continuous @ 100ms — p95<500ms, drift<100% vs baseline | ✅ |
| G2 | **Memory/thread growth during soak** | 🔴 CRITICAL GAP — see Section I |

---

## 🔴 SECTION H — TRUE DISPATCHER / COM STRESS (CRITICAL GAP)
**File**: `full_test_suite.py` — Section H *(not yet implemented)*
**Status**: 🔴 CRITICAL — must add before production

### H — Why This Matters
Current tests hit `/api/opc/values` → ConcurrentDictionary → no COM.
The **dispatcher STA thread** and **COM layer** are exercised only by the internal 500ms poll cycle.
If the dispatcher hangs, queues up, or deadlocks — current tests **will not detect it**.

### H1 — Dispatcher Ping Endpoint (prerequisite)
**Required backend change**: Add to `OpcDaController.cs`:
```csharp
// GET /api/opc/dispatcher-ping
// Routes THROUGH dispatcher — performs lightweight COM read (server state or group count)
// Returns: { "dispatcherQueueDepth": N, "comRoundtripMs": X, "state": "Healthy" }
[HttpGet("dispatcher-ping")]
public async Task<IActionResult> DispatcherPing()
{
    var sw = Stopwatch.StartNew();
    var state = await _opcDispatcher.RunAsync(() => _opcServer.GetServerState()); // lightweight COM
    sw.Stop();
    return Ok(new { dispatcherQueueDepth = _opcDispatcher.QueueDepth, comRoundtripMs = sw.ElapsedMilliseconds, state });
}
```
**Blocked by**: Fix #7 (bounded queue with depth metric)

### H2 — Planned Dispatcher Tests

| ID | Test | What it stresses | Threshold | Status |
|----|------|-----------------|-----------|--------|
| H1 | Dispatcher ping baseline — 20 serial requests | STA thread COM roundtrip | p50<100ms | ⏳ |
| H2 | Dispatcher queue depth under load — 50 concurrent pings | Queue fill rate + drain rate | depth<50 at steady state | ⏳ |
| H3 | Dispatcher saturation — 200 rapid pings | Queue bounded? Drop behavior? | No queue explosion, fail-fast | ⏳ |
| H4 | Dispatcher during REST load — parallel ping + values reads | COM isolation from REST reads | Pings succeed while REST load runs | ⏳ |
| H5 | Queue depth metric present in response | Fix #7 prerequisite check | queueDepth field in response | ❌ blocked by Fix #7 |

**Prerequisite**: Fix #7 (bounded queue) must be done first.

---

## 🔴 SECTION I — MEMORY & RESOURCE LEAK DETECTION (CRITICAL GAP)
**File**: `full_test_suite.py` — Section I *(not yet implemented)*
**Status**: 🔴 CRITICAL for industrial runtime

### Why This Matters
COM RCW leaks, orphaned subscriptions, stale Tasks, and queue retention only show up under sustained load.
They are INVISIBLE in short tests. Industrial systems run 24/7 — leaks that manifest in hours are production bugs.

### Planned Tests

| ID | Test | Metric | Threshold | Status |
|----|------|--------|-----------|--------|
| I1 | Memory baseline snapshot | Process RSS MB | Record | ⏳ |
| I2 | Memory during saturation (500 req) | RSS growth | <50MB growth over baseline | ⏳ |
| I3 | Memory during soak (30s+) | RSS growth per 10s window | <5MB/window (no steady growth) | ⏳ |
| I4 | Thread count baseline | threading.active_count() or psutil | Record | ⏳ |
| I5 | Thread count after saturation | Thread leak detection | <baseline + 5 | ⏳ |
| I6 | Thread count after reconnect cycles | COM thread accumulation | <baseline + 10 | ⏳ |
| I7 | Handle count (Windows) | psutil process handles | No steady growth | ⏳ |
| I8 | **24-hour soak** (future sprint) | RSS, threads, handles, p95 drift | See 24h thresholds | 🔵 Future |

**Implementation note**: Requires `psutil` package:
```
pip install psutil
```
Track every 10s window during soak:
```python
import psutil
proc = psutil.Process()
mem_mb = proc.memory_info().rss / 1024 / 1024
threads = proc.num_threads()
handles = proc.num_handles()   # Windows only
```

---

## 🟡 SECTION J — OPC FREEZE SIMULATION (IMPORTANT)
**File**: `full_test_suite.py` — Section J *(not yet implemented)*
**Status**: 🟡 Important — implement after Fix #6 (state machine)

### Why This Matters
COM hangs are the #1 industrial OPC failure mode. A frozen Matrikon process will block the STA thread
indefinitely without a timeout. This is the scenario Fix #8 (per-op timeout) and Fix #9 (watchdog) exist to detect.

### Test Scenarios

| ID | Test | How to trigger | What to validate | Prereq | Status |
|----|------|---------------|-----------------|--------|--------|
| J1 | Stop Matrikon service | `net stop "Matrikon OPC Server for Simulation"` | Dispatcher timeout fires within 30s | Fix #8 | ⏳ |
| J2 | State → Degraded after freeze | Check /api/opc/status | state="Degraded" within 30s | Fix #6 | ⏳ |
| J3 | REST still responsive during OPC hang | Hit /api/opc/values during freeze | Returns cached values, not 500 | Fix #7 | ⏳ |
| J4 | Queue remains bounded during freeze | Check queue depth under OPC freeze | depth < BoundedCapacity | Fix #7 | ⏳ |
| J5 | No memory explosion during freeze | RSS during 60s freeze | <100MB growth | I3 | ⏳ |
| J6 | Watchdog log fires | Scan logs during freeze | "dispatcher appears hung" within 35s | Fix #9 | ⏳ |
| J7 | Recovery after Matrikon restart | `net start`, watch logs | tagCount=27 restores, pool refills | Fix #6 | ⏳ |

**Prerequisite**: Fix #6 (state machine) + Fix #7 (bounded queue) + Fix #8 (per-op timeout) + Fix #9 (watchdog)

---

## 🟡 SECTION K — RECONNECT STORM PROTECTION
**File**: `full_test_suite.py` — Section K *(not yet implemented)*
**Status**: 🟡 Important — implement after Fix #6 (state machine)

### Why This Matters
Rapid connect/disconnect cycles on OPC DA can cause:
- Duplicate group creation
- Queue explosion (pending ops from dead session)
- COM RCW reference leaks
- Thread accumulation (each reconnect spawns threads)
- Recursive reconnect calls (reconnect triggered while reconnect is running)

### Planned Tests

| ID | Test | Metric | Threshold | Status |
|----|------|--------|-----------|--------|
| K1 | 10 rapid restart cycles (stop/start Matrikon) | tagCount stability | =27 after each cycle | ⏳ |
| K2 | No duplicate OPC groups after reconnect | Group count via dispatcher-ping | =1 group per connection | ⏳ |
| K3 | No thread growth across 10 reconnect cycles | Thread count delta | <10 threads above baseline | ⏳ |
| K4 | No queue explosion during reconnect | Queue depth during cycle | <BoundedCapacity (1000) | ⏳ |
| K5 | Circuit breaker fires after 5 rapid failures | /api/opc/status state | state="Faulted" | Fix #6 | ⏳ |
| K6 | Circuit breaker cooldown (5 min) respected | No reconnect during cooldown | No connection attempts for 5 min | Fix #6 | ⏳ |

**Prerequisite**: Fix #6 (state machine) + Fix #7 (bounded queue)

---

## 🔵 SECTION L — HEALTH ENDPOINT RESILIENCE (Fix #11 prerequisite)
**File**: `full_test_suite.py` — Section L *(not yet implemented)*
**Status**: 🔵 Implement alongside Fix #11

### Why This Matters
Many systems deadlock health checks by querying COM inside the health endpoint.
If OPC hangs and `/api/system-health` also hangs — monitoring is blind.
Health endpoint MUST respond instantly from cached state only, never via COM.

| ID | Test | What to validate | Threshold | Status |
|----|------|-----------------|-----------|--------|
| L1 | Health endpoint baseline latency | p50 | <10ms (cache-only read) | ⏳ |
| L2 | Health endpoint during OPC freeze | Response time during Matrikon stop | <100ms even when OPC hangs | ⏳ |
| L3 | Health endpoint during saturation | 100 concurrent health requests | success=100%, p95<50ms | ⏳ |
| L4 | Health endpoint fields complete | All sections present | opc, dispatcher, pool, uptime | Fix #11 | ⏳ |

**Prerequisite**: Fix #11 (health endpoint)

---

## 🔵 SECTION M — CALLBACK FLOOD (Future)
**File**: TBD
**Status**: 🔵 Future — implement when OPC DA subscriptions are enabled

### Why This Matters
OPC DA callback (IOPCDataCallback) bursts on the STA thread can deadlock if:
- Callback handler takes too long
- Re-entrant calls from within callback
- Too many pending callbacks queue up faster than they drain

| ID | Test | Status |
|----|------|--------|
| M1 | Rapid tag update storm (simulate 27 tags × 100Hz) | 🔵 Future |
| M2 | Callback frequency spike detection | 🔵 Future |
| M3 | STA thread deadlock detection during callback flood | 🔵 Future |
| M4 | Dispatcher queue protection under callback storm | 🔵 Future |

---

## 🔵 SECTION N — 24-HOUR SOAK (Future Sprint)
**Status**: 🔵 Future — after all fixes #1-#11 implemented and stable

### Metrics to track every 10 minutes:
- Process RSS (MB) — detect COM RCW leaks
- Thread count — detect orphaned reconnect threads
- Handle count (Windows) — detect COM handle leaks
- GC heap — detect callback accumulation / stale Task retention
- p95 latency — detect gradual degradation
- Queue depth — detect slow queue leak
- tagCount — detect silent OPC disconnects

### Pass criteria:
- RSS growth < 100MB over 24h
- Thread count: no steady increase
- p95 latency: no drift >50% vs hour-1 baseline
- tagCount: =27 continuously
- 0 unhandled exceptions in logs

---

## HARD-FAIL THRESHOLDS (for CI automation)
The following conditions should cause **immediate test abort with exit code 1**:

| Condition | Threshold | Applies to |
|-----------|-----------|------------|
| tagCount < 27 | Hard fail | All sections |
| success rate < 90% | Hard fail | D, E, F, H |
| p95 latency > 5000ms | Hard fail | D, G |
| stale events > 5 in 30s | Hard fail | E3, G |
| queue depth > 500 | Hard fail | H (post-Fix#7) |
| memory growth > 200MB | Hard fail | I |
| thread growth > 20 | Hard fail | K |
| _reconnect_stopped permanently True | Hard fail | C1 |
| 500 errors on health endpoint | Hard fail | L |

---

## WHAT IS ACTUALLY BEING STRESSED — REFERENCE TABLE
> ⚠️ Critical for avoiding misleading conclusions

| Test Group | Common Misname | Actual Stress Target |
|-----------|----------------|---------------------|
| D5, D6, D7 | "Dispatcher saturation" | **REST cache saturation** (ConcurrentDict + JSON + ASP.NET threadpool) |
| D1-D4 | "OPC polling" | **HTTP layer + pool read** — no COM calls |
| H1-H5 | "API test" | **STA thread + COM layer** — true dispatcher exercise |
| E3, G1 | "Freshness test" | **LiveTagCacheService 500ms cycle** — Fix #1 verification |
| C1-C6 | "MQTT test" | **Static code analysis** — Fix #2 verification |
| J1-J7 | "Failure test" | **COM freeze + watchdog + state machine** — Fix #6/#8/#9 |
| K1-K6 | "Reconnect test" | **OPC DA COM lifecycle + circuit breaker** — Fix #6 |

---

## CURRENT TEST GAPS — PRIORITY ORDER

| Priority | Gap | Blocking Fix | ETA |
|----------|-----|-------------|-----|
| 🔴 CRITICAL | True dispatcher/COM stress (Section H) | Fix #7 | After Fix #7 |
| 🔴 CRITICAL | Memory/thread leak detection (Section I) | None — add psutil | This sprint |
| 🟡 IMPORTANT | OPC freeze simulation (Section J) | Fix #6+#7+#8+#9 | After those fixes |
| 🟡 IMPORTANT | Reconnect storm protection (Section K) | Fix #6+#7 | After those fixes |
| 🔵 FUTURE | Health endpoint resilience (Section L) | Fix #11 | After Fix #11 |
| 🔵 FUTURE | Callback flood (Section M) | Subscriptions enabled | Later sprint |
| 🔵 FUTURE | 24-hour soak (Section N) | All fixes done | Final sprint |

---

## IMPROVEMENT IDEAS LOG
*(Add new ideas here as they come up)*

1. **Percentile trend graphs** — plot p50/p95/p99/queue depth/stale age over time during soak. Use `matplotlib` or export to CSV. Extremely valuable during degradation analysis.
2. **JUnit XML output** — add `--junit results.xml` flag for CI pipeline integration.
3. **Automated Mosquitto kill/restart** — automate C7/C8 using `subprocess.run(["net", "stop", "mosquitto"])` for fully automated MQTT retry validation.
4. **Rename misleading test names** — "Dispatcher saturation" → "REST cache saturation", "Concurrent burst" → "ASP.NET concurrent cache reads" (see reference table above).
5. **Fail-fast mode** — `--strict` flag that converts all WARN to FAIL and exits immediately on first failure.
6. **Baseline auto-save** — save baseline p50/p95/rss to JSON after first run, reload on next run for automatic drift detection.
7. **Add `psutil` to requirements** — `pip install psutil` for memory/thread/handle tracking in Section I.

---

---

## TEST PRECONDITIONS (per section)
> Missing preconditions = false failures + misleading results. Check before running.

| Section | Required Preconditions |
|---------|----------------------|
| **A, B, C** | Backend running on :5001 · OPC connected · tagCount=27 |
| **D, E, F** | Backend running · OPC connected · tagCount=27 · No other load on backend |
| **G (soak)** | All of D/E/F passing · System idle ≥ 60s before start |
| **H (dispatcher)** | Fix #7 done (bounded queue + depth metric) · dispatcher-ping endpoint live · tagCount=27 |
| **I (memory)** | `psutil` installed · `OpcDaWebBrowser.exe` PID known · System idle · No other load |
| **J (freeze)** | Fix #6+#7+#8+#9 done · Matrikon running · tagCount=27 · Admin rights for `net stop` |
| **K (reconnect)** | Fix #6+#7 done · Matrikon running · tagCount=27 · Admin rights |
| **L (health)** | Fix #11 done · `/api/system-health` endpoint live |
| **N (24h soak)** | ALL fixes #1–#11 done · Machine dedicated · No other workload |

---

## KNOWN EXPECTED FAILURES (per scenario)
> Document these to prevent panic, misclassification, and wasted debugging during controlled tests.

### During J1 (Stop Matrikon — OPC Freeze):
- ⚠️ Timeout WARN logs → **expected** (Fix #8 firing correctly)
- ⚠️ Queue depth increase → **expected** (pending COM ops backing up)
- ⚠️ state=Degraded → **expected** (Fix #6 state machine working)
- ⚠️ `[WARN] COM operation exceeded 5s` → **expected**
- ❌ If: REST returns 500 → **NOT expected** — pool should serve cached values
- ❌ If: health endpoint hangs → **NOT expected** — must respond from cache

### During K (Reconnect Storm):
- ⚠️ state=Faulted after 5 failures → **expected** (circuit breaker working)
- ⚠️ Log: `Faulted — 5min cooldown` → **expected**
- ⚠️ tagCount drops to 0 during disconnect → **expected temporarily**
- ❌ If: thread count grows >20 → **NOT expected** — COM thread leak
- ❌ If: queue depth > BoundedCapacity → **NOT expected** — queue explosion

### During C7/C8 (MQTT Kill/Restart):
- ⚠️ Log: `DEGRADED+RETRYING — attempt #N` → **expected** (Fix #2 working)
- ⚠️ Brief tag data gap if MQTT-only source → **expected**
- ❌ If: `_reconnect_stopped = True` set → **NOT expected** — Fix #2 regression

### During G (Soak):
- ⚠️ p50 jitter ±5ms per 10s window → **expected** (Windows scheduler)
- ⚠️ Occasional p95 spike to 200ms → **expected** (GC pause / OS scheduling)
- ❌ If: p95 > 500ms sustained → **NOT expected** — investigate
- ❌ If: memory grows >5MB/window steadily → **NOT expected** — RCW leak

---

## TEST ISOLATION RULES
> CRITICAL: failure/reconnect/soak tests can contaminate later tests. Verify these after every major section.

### Post-Section Cleanup Checklist
After sections J, K, G (and before any subsequent section):

```
□ tagCount = 27 (OPC reconnected and pool refilled)
□ OPC state = Connected  (not Degraded/Faulted)
□ Queue depth = 0 or near-zero  (all pending ops drained)
□ Thread count = baseline ± 3  (no orphaned threads)
□ Memory RSS = baseline + acceptable delta  (no leak accumulation)
□ No active reconnect loop running  (check logs)
□ REST endpoints returning 200  (smoke: GET /api/opc/status)
```

### Test Abort + Taint Flag Rules
If any of these hard conditions occur — **stop remaining tests, mark environment TAINTED**:

| Condition | Action |
|-----------|--------|
| Queue depth > 500 | ABORT — queue explosion, COM probably stuck |
| Dispatcher deadlocked (no heartbeat >60s) | ABORT — STA thread dead |
| OPC state = Faulted + cooldown not recovering | ABORT — circuit breaker stuck |
| Memory RSS > +500MB above baseline | ABORT — catastrophic leak |
| tagCount = 0 for >60s without freeze test active | ABORT — silent OPC disconnect |

When TAINTED:
1. Log `ENVIRONMENT TAINTED — results invalid from this point`
2. Run cleanup: restart `OpcDaWebBrowser.exe`, verify tagCount=27
3. Do NOT compare results from tainted run to baseline

---

## RECOVERY VERIFICATION CHECKPOINTS
> For every failure test: detection is only half. Recovery must also be verified.

| Trigger | Recovery Checkpoint | Pass Criteria |
|---------|---------------------|---------------|
| J1 — Matrikon stopped | J7 — Matrikon restarted | tagCount=27 within 30s, state=Connected |
| K — Reconnect storm | Post-K isolation check | tagCount=27, queue=0, threads=baseline |
| C7 — Mosquitto killed | C8 — Mosquitto restarted | `back to CONNECTED` in logs within 65s (max backoff 60s+jitter) |
| G — Soak ends | Post-soak memory check | RSS delta <50MB, thread delta <5 |
| H3 — Dispatcher saturated | Post-H3 queue check | Queue depth returns to 0 within 5s |
| Any 500 error burst | /api/opc/status check | HTTP 200, connected=true |

---

## BASELINE SNAPSHOT PROTOCOL
> Take before every test run. Compare delta post-run. Required for leak detection.

### What to Capture (automated in full_test_suite.py):
```python
baseline = {
    "timestamp": datetime.utcnow().isoformat(),
    "memory_rss_mb": proc.memory_info().rss / 1024 / 1024,
    "thread_count": proc.num_threads(),
    "handle_count": proc.num_handles(),   # Windows only
    "opc_tag_count": 27,
    "opc_state": "Connected",
    "queue_depth": 0,   # from dispatcher-ping (post Fix #7)
}
```

### Saved to: `tests/results/baseline_<timestamp>.json`

### Delta Thresholds:
| Metric | Acceptable Delta | Hard Fail |
|--------|-----------------|-----------|
| Memory RSS | < +50MB | > +200MB |
| Thread count | < +5 | > +20 |
| Handle count | < +20 | > +100 |
| Queue depth | = 0 | > 50 |

---

## RESULT PERSISTENCE
> Console output is not enough. All test results saved to JSON for regression tracking.

### Output location: `tests/results/run_<YYYYMMDD_HHMMSS>.json`

### Schema:
```json
{
  "run_id": "20260526_143022",
  "timestamp": "2026-05-26T14:30:22Z",
  "mode": "quick",
  "baseline": { "memory_rss_mb": 45.2, "thread_count": 12, "handle_count": 180 },
  "sections": {
    "A": { "passed": 5, "failed": 0, "tests": [...] },
    "D": {
      "passed": 6, "failed": 1,
      "perf": { "baseline_p50": 7.1, "baseline_p99": 18.3, "saturation_rps": 347 }
    }
  },
  "post_run": { "memory_rss_mb": 47.1, "thread_count": 12, "delta_memory_mb": 1.9 },
  "verdict": "PASS",
  "total_passed": 28,
  "total_failed": 0
}
```

### Regression comparison:
```
.\HMI\.venv\Scripts\python.exe tests\full_test_suite.py --compare tests\results\run_20260526_143022.json
```

---

## NOISE FLOOR REFERENCE
> Read before interpreting latency results. Prevents false optimization efforts.

| Source | Typical Impact | Notes |
|--------|---------------|-------|
| Windows scheduler jitter | ±5–15ms | `time.sleep(0.01)` may actually sleep 15ms (timer resolution) |
| Python GIL | 0–5ms | GIL release every 5ms (default switch interval) affects burst tests |
| TCP stack (loopback) | 0.1–2ms | Loopback is fast but not zero. Real network = add 1–5ms |
| JSON serialization (27 tags) | 0.5–2ms | C# `System.Text.Json` for 27 tags. Grows with tag count. |
| ConcurrentDictionary read | <0.1ms | Effectively free. Not a bottleneck. |
| COM dispatch (on STA thread) | 1–50ms | Matrikon Simulation: typically 2–10ms. Real PLCs: 5–100ms. |
| GC pause (.NET) | 0–50ms | Gen0 GC: <1ms. Gen2: up to 50ms. Shows as p99 spike. |
| Windows timer resolution | ~15.6ms | `timeBeginPeriod(1)` reduces to ~1ms if needed |

**Rule of thumb**: Anything within ±15ms of target is likely OS noise, not architecture issue.
**Action threshold**: Only investigate if p95 consistently >2× baseline across multiple runs.

---

## COM APARTMENT VERIFICATION TEST
> Small but critical. STA violation = silent data corruption or deadlock, no error thrown.

### Test CA1 (add to Section A):
At backend startup, confirm dispatcher thread apartment is STA:

**What to check in logs**:
```
[OpcStaDispatcher] Thread apartment: STA   ← REQUIRED
```
If log shows MTA or is missing → **Hard fail — COM calls will be unreliable**

**How to add to C# dispatcher**:
```csharp
// In OpcStaDispatcher constructor, on the STA thread:
var apt = Thread.CurrentThread.GetApartmentState();
_logger.LogInformation($"[OpcStaDispatcher] Thread apartment: {apt}");
if (apt != ApartmentState.STA)
    throw new InvalidOperationException("Dispatcher thread must be STA");
```

**Test CA1** (add to full_test_suite.py Section A):
- Search OPC logs for `Thread apartment: STA`
- Hard fail if not found or if `MTA` found

---

## FUTURE OBSERVABILITY ROADMAP
> Not needed now. High long-term value.

| Tool | Metrics to Export | Value |
|------|------------------|-------|
| Prometheus + Grafana | queue_depth, reconnect_count, stale_age_ms, p95_latency, opc_state_duration | Real-time dashboard, alerting |
| OpenTelemetry | Traces per COM call, dispatcher wait time | Distributed tracing |
| CSV export | All soak metrics every 10s | Offline trend analysis, regression graphs |
| Matplotlib (Python) | p50/p95/p99/memory/threads over time | Visual soak analysis |

---

## CHANGELOG

| Date | Change |
|------|--------|
| 2026-05-26 | Initial test plan created |
| 2026-05-26 | `opc_stress_test.py` — original 9-test stress suite (retained for regression) |
| 2026-05-26 | `full_test_suite.py` — comprehensive A–G suite created covering Fix #1/#2 + performance + pool + edge cases + soak |
| 2026-05-26 | Test plan gaps identified: Sections H/I/J/K/L/M/N |
| 2026-05-26 | Added: Test Preconditions, Known Expected Failures, Isolation Rules, Recovery Checkpoints, Baseline Protocol, Result Persistence, Noise Floor, COM Apartment test, Future Observability |
