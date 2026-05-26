# DEVELOPMENT INSTRUCTIONS — SMALL-STEP IMPLEMENTATION PROTOCOL

**Purpose:** Mandatory development methodology for PLC Gateway stabilization and all future critical work  
**Status:** ACTIVE — Must be followed for ALL Sprint 1-5 tasks  
**Date Created:** May 26, 2026

---

## 🚨 CORE PRINCIPLE

> **"One change. Build. Test. Verify. Commit. Repeat."**

**Stability is MORE important than speed.**

---

## ✅ 10 MANDATORY EXECUTION RULES

These rules are **NON-NEGOTIABLE** for all PLC Gateway work:

1. ✅ **ONE CHANGE ONLY** per implementation cycle
2. ✅ **BUILD** after EVERY change  
3. ✅ **TEST** after EVERY build
4. ✅ **VERIFY** logs after EVERY test
5. ✅ **COMMIT** only after verification
6. ✅ **NEVER** combine multiple fixes
7. ✅ **NEVER** refactor during stabilization
8. ✅ **NEVER** "improve architecture" during bug fixing
9. ✅ **EVERY** change must be reversible
10. ✅ **IF ANY REGRESSION** → STOP and rollback immediately

---

## 📋 STANDARD IMPLEMENTATION CYCLE (10 STEPS)

**Use this cycle for EVERY task without exception:**

```
STEP 1  → Read target code completely
          - Understand full context
          - Identify all dependencies
          - Note related functions

STEP 2  → Understand exact issue
          - Root cause analysis
          - Why it fails
          - What correct behavior looks like

STEP 3  → Implement MINIMAL fix only
          - Smallest possible change
          - No "improvements"
          - No refactoring
          - No optimization

STEP 4  → Build solution
          - Command: dotnet build
          - Must succeed with zero errors
          - Fix build errors before proceeding

STEP 5  → Run application
          - Command: dotnet run
          - Or: START_HMI.bat
          - Wait for full startup

STEP 6  → Test target functionality
          - Test exact feature that was broken
          - Test related features
          - Use API/UI/logs as appropriate

STEP 7  → Check logs for regressions
          - No new errors introduced
          - No new warnings introduced
          - No performance degradation

STEP 8  → Verify CPU/memory stable
          - Task Manager or htop
          - Check for memory leaks
          - Check for thread leaks
          - Monitor for 2-5 minutes minimum

STEP 9  → Commit with clean message
          - Follow commit message template
          - Reference task ID
          - Describe what and why

STEP 10 → Move to next task
          - Update progress tracking
          - Document any observations
          - Proceed to next priority item
```

**DO NOT SKIP ANY STEP.**

---

## 🎯 WHAT TO DO DURING STABILIZATION

**DO:**
- ✅ Fix critical bugs only
- ✅ Add missing safety checks
- ✅ Improve error handling
- ✅ Add necessary logging
- ✅ Fix state machine issues
- ✅ Add timeout protection
- ✅ Fix counter/metric bugs
- ✅ Add validation

**DO NOT:**
- ❌ Refactor working code
- ❌ "Improve" architecture
- ❌ Optimize performance (unless critical)
- ❌ Add new features
- ❌ Change naming conventions
- ❌ Reorganize file structure
- ❌ Update dependencies
- ❌ Change design patterns

**Golden Rule:** If it's not blocking production readiness, defer it to Sprint 2+.

---

## 📝 COMMIT MESSAGE TEMPLATE

```
<type>(S<sprint>-<number>): <short summary max 72 chars>

<Detailed explanation of what was changed and why>

Changes:
- Specific change 1
- Specific change 2
- Specific change 3

Fixes: S<sprint>-<number>
Risk: <Low|Medium|High|Critical>
Tested: <What you tested>
```

**Types:**
- `fix` — Bug fix
- `feat` — New feature (rare in Sprint 1)
- `refactor` — Code restructure (avoid in Sprint 1)
- `test` — Test additions
- `docs` — Documentation
- `chore` — Build/tooling

**Example:**
```
fix(S1-13): prioritize runtime worker status in /api/plc/connections

Changed data source priority order from saved → pool → runtime
to runtime → saved → pool. PlcWorker.GetStatus() already returns
correct IP/port from _config, but controller was ignoring it.

Changes:
- Modified PlcController.cs line 363: protocol fallback order
- Modified PlcController.cs line 364: ipAddress fallback order
- Modified PlcController.cs line 365: port fallback order

Fixes: S1-13
Risk: Low (only changes data priority, no logic changes)
Tested: GET /api/plc/connections now returns correct IP/protocol
```

---

## 🧪 TESTING REQUIREMENTS

### After Every Change

**Minimum Tests:**
1. **Smoke test** — Application starts without crash
2. **Feature test** — Changed functionality works correctly
3. **Regression test** — Related features still work
4. **Log check** — No new errors/warnings
5. **Resource check** — No memory/CPU spikes

### Before Committing

**Pre-Commit Checklist:**
- [ ] Code builds successfully (`dotnet build`)
- [ ] Application runs without crashes
- [ ] Target functionality verified working
- [ ] No new errors in logs
- [ ] No new warnings in logs
- [ ] Memory stable (Task Manager check)
- [ ] CPU stable (< 50% sustained)
- [ ] Related features tested (spot check)

### Before Moving to Next Task

**Task Completion Checklist:**
- [ ] All pre-commit checks passed
- [ ] Commit message written and pushed
- [ ] Changes documented in task tracker
- [ ] Any observations noted for future reference
- [ ] System stable for 2-5 minutes minimum

---

## 🚫 WHEN TO STOP AND ROLLBACK

**Immediately stop and rollback if you see:**

1. **Build Failures**
   - New compilation errors
   - Unresolved references
   - Syntax errors introduced

2. **Runtime Failures**
   - Application won't start
   - Immediate crashes
   - Dependency injection failures
   - Connection failures (new ones)

3. **Functional Regressions**
   - Previously working feature now broken
   - Data corruption
   - Incorrect calculations
   - Missing data

4. **Performance Degradation**
   - Memory leak (sustained growth)
   - CPU spike (> 80% sustained)
   - Thread leak (thread count growing)
   - Response time degradation

5. **Error Storm**
   - Logs flooding with errors
   - Reconnect storms
   - Exception spam
   - Timeout cascades

**Rollback Process:**
```bash
# If not yet committed:
git checkout -- <file>

# If already committed:
git revert <commit-hash>

# Then:
dotnet build
dotnet run
# Verify system stable again
```

---

## 📊 PROGRESS TRACKING

### Daily Log Format

```markdown
## [Date] — Sprint [X] Progress

### Tasks Completed Today
- [S1-13] ✅ Fixed IP address mapping (30 min)
- [S1-1a] ✅ Added formal state machine (45 min)

### Tasks In Progress
- [S1-2] 🔄 Circuit breaker implementation (50% complete)

### Blockers
- None

### Observations
- State machine reduced invalid transition attempts by 80%
- Logs now much cleaner with validated transitions
- No regressions observed in 10-minute soak test

### Next Session
- [ ] Complete S1-2 (circuit breaker)
- [ ] Begin S1-9 (hard timeout wrapper)
```

---

## 🎯 SPRINT-SPECIFIC GUIDELINES

### Sprint 1 — Operational Correctness
**Goal:** Make system safe for production PLC connection  
**Focus:** Fix critical bugs, add safety checks  
**Avoid:** Architecture changes, optimizations, new features

### Sprint 2 — Stability & Diagnostics
**Goal:** Add observability and backpressure protection  
**Focus:** Metrics, diagnostics, resource limits  
**Avoid:** Event bus, analytics, AI features

### Sprint 3 — Global Supervisor
**Goal:** Platform-wide health monitoring  
**Focus:** CPU/memory/MQTT/DB monitoring, coordinated shutdown  
**Avoid:** Event bus (comes after supervisor)

### Sprint 4 — Event Bus Architecture
**Goal:** Decoupling layer for extensibility  
**Focus:** Lightweight in-process event bus, OPC+PLC unified  
**Avoid:** Kafka, distributed systems, over-engineering

### Sprint 5+ — Intelligence Layer
**Goal:** AI/ML, OEE, predictive maintenance  
**Focus:** Analytics, alarms, quality monitoring  
**Prerequisite:** All previous sprints stable

---

## 🔍 CODE REVIEW CHECKLIST

**Before accepting any change (self-review or peer review):**

### Correctness
- [ ] Solves stated problem completely
- [ ] No edge cases overlooked
- [ ] Handles errors gracefully
- [ ] Validation added where needed

### Safety
- [ ] No null reference risks
- [ ] No divide-by-zero risks
- [ ] No infinite loops possible
- [ ] No deadlock risks
- [ ] No race conditions

### Stability
- [ ] No memory leaks
- [ ] No thread leaks
- [ ] No resource leaks (files, connections, etc.)
- [ ] Timeout protection where needed
- [ ] Cancellation token support

### Observability
- [ ] Appropriate logging added
- [ ] Error messages helpful
- [ ] State transitions logged
- [ ] Metrics updated if applicable

### Maintainability
- [ ] Code is readable
- [ ] Intent is clear
- [ ] Comments added for non-obvious logic
- [ ] No "clever" code

### Testing
- [ ] Change is testable
- [ ] Has been tested manually
- [ ] Regression tests passed
- [ ] Edge cases tested

---

## 🧪 SOAK TEST PROTOCOL

**Run after completing each sprint (mandatory):**

### Duration
- **Minimum:** 30 minutes
- **Recommended:** 60 minutes
- **Pre-production:** 24 hours

### Test Scenarios

1. **Normal Operation**
   - All PLCs connected
   - Normal polling
   - MQTT publishing
   - Historian writing
   - API responding

2. **PLC Disconnect/Reconnect**
   - Unplug network cable
   - Wait 2 minutes
   - Reconnect
   - Verify recovery

3. **MQTT Restart**
   - Stop Mosquitto
   - Wait 1 minute
   - Restart Mosquitto
   - Verify reconnection

4. **Backend Restart**
   - Stop C# backend
   - Wait 30 seconds
   - Restart backend
   - Verify full recovery

5. **Python HMI Restart**
   - Stop Python app
   - Wait 30 seconds
   - Restart Python app
   - Verify data flow resumes

6. **Network Interruption**
   - Disable network adapter
   - Wait 1 minute
   - Re-enable adapter
   - Verify reconnection

7. **Stale Data Handling**
   - Stop PLC polling (debugger pause)
   - Wait 15 seconds
   - Resume
   - Verify stale marking works

8. **Circuit Breaker Trigger**
   - Set invalid PLC IP
   - Verify fault state entered
   - Verify cooldown respected
   - Fix IP and verify recovery

### Monitoring During Soak Test

**Watch these metrics continuously:**

```
CPU Usage:        Should stay < 30% average
Memory (C#):      Should be stable (no growth)
Memory (Python):  Should be stable (no growth)
Thread Count:     Should be stable (no growth)
Log Error Rate:   Should be near zero
MQTT Queue:       Should not back up
DB Connections:   Should not leak
Response Times:   Should remain consistent
```

**Tools:**
- Task Manager (Windows)
- htop (Linux)
- Application logs
- MQTT broker logs
- PostgreSQL logs

### Soak Test Rules

**During soak test:**
- ❌ DO NOT change code
- ❌ DO NOT restart unnecessarily
- ❌ DO NOT interfere with processes
- ✅ DO observe behavior
- ✅ DO log anomalies
- ✅ DO document failure modes
- ✅ DO take screenshots of issues

**After soak test:**
- Document all failures observed
- Prioritize fixes for next sprint
- Update architecture doc with learnings
- Add regression tests for failures found

---

## 📈 METRICS & HEALTH INDICATORS

### Healthy System Indicators

**C# Backend:**
```
CPU:                  10-30% average
Memory:               200-500 MB stable
Threads:              20-40 stable
GC Collections:       < 10/minute
API Response Time:    < 100ms p95
```

**Python HMI:**
```
CPU:                  5-20% average
Memory:               100-300 MB stable
Gevent Greenlets:     < 1000 active
MQTT Queue:           < 100 messages
API Response Time:    < 200ms p95
```

**PostgreSQL:**
```
Active Connections:   < 50
Idle Connections:     5-20
Query Time:           < 50ms p95
Deadlocks:            0
Table Locks:          < 10 concurrent
```

**Mosquitto MQTT:**
```
Connected Clients:    3-10 stable
Messages/sec:         10-100 normal
Queue Depth:          0-50 normal
Retained Messages:    < 1000
```

### Warning Indicators

**Watch for these patterns:**
- Memory climbing steadily (leak)
- Thread count growing (leak)
- Error rate increasing
- Response times degrading
- Log spam (same error repeatedly)
- MQTT queue backing up
- DB connection pool exhausted
- GC pause times increasing

---

## 🛠️ DEBUGGING WORKFLOW

### Issue Identification

1. **Collect Evidence**
   - Error messages (full stack traces)
   - Log snippets (before/after error)
   - Metrics at time of failure
   - User actions that triggered it

2. **Reproduce Locally**
   - Identify minimal repro steps
   - Document environment state
   - Capture logs during repro
   - Take screenshots/recordings

3. **Root Cause Analysis**
   - Use debugger to step through code
   - Add temporary logging if needed
   - Check state machine transitions
   - Verify data flow

### Fix Implementation

1. **Design Fix**
   - Identify minimal change needed
   - Consider edge cases
   - Plan testing approach
   - Check for similar bugs elsewhere

2. **Implement Fix**
   - Follow 10-step implementation cycle
   - Add validation if missing
   - Add logging if needed
   - Update error messages

3. **Verify Fix**
   - Test original failure scenario
   - Test edge cases
   - Run regression tests
   - Monitor for 5+ minutes

---

## 📚 REFERENCE MATERIALS

### Key Documents
- `PLC_COMM_ARCHITECTURE.md` — Complete technical spec
- `SPRINT_1_EXECUTION_PLAN.md` — Detailed task breakdown
- `BUG_FIX_LOG.md` — Historical bug fixes
- `CHANGES_RBAC_MQTT_PLC_FIX.md` — Change history

### Gold Standard Code
- `OpcStaDispatcher.cs` — State machine pattern
- `OpcAutoConnectService.cs` — Reconnect pattern
- `OpcMqttPublisherService.cs` — MQTT publishing pattern

### Critical Patterns

**State Machine:**
```csharp
private void TransitionTo(State next, string reason)
{
    if (!IsValidTransition(_state, next)) {
        _logger.LogError("Invalid {From} → {To}", _state, next);
        return;
    }
    _state = next;
    _logger.LogInformation("{From} → {To}: {Reason}", old, next, reason);
}
```

**Hard Timeout Wrapper:**
```csharp
var readTask = _driver.ReadAllTagsAsync();
if (await Task.WhenAny(readTask, Task.Delay(_timeout)) != readTask)
    throw new TimeoutException("Driver operation timed out");
```

**Circuit Breaker:**
```csharp
if (_consecutiveFailures >= 5) {
    _faultCount++;
    var cooldown = Math.Min(300 * Math.Pow(2, _faultCount - 1), 3600);
    _cooldownUntil = DateTime.UtcNow.AddSeconds(cooldown);
    TransitionTo(Faulted, $"Cooldown {cooldown}s");
}
```

---

## 🎓 LESSONS LEARNED

### From OPC Development

1. **Systems appear to work in dev/staging. Production exposes every gap.**
   - Always test disconnection scenarios
   - Always test reconnection scenarios
   - Always test resource exhaustion

2. **Worker isolation prevents cascading failures.**
   - One PLC = One task = Complete isolation
   - Never share driver connections
   - Never share error state

3. **State machines prevent invalid transitions.**
   - Inline assignments hide bugs
   - Validation catches problems early
   - Logging makes debugging trivial

4. **Hard timeouts are mandatory for native calls.**
   - Native DLLs can hang forever
   - No way to interrupt from .NET
   - Outer timeout wrapper is only protection

5. **MQTT can fail independently of PLC.**
   - Always have REST fallback
   - Cache latest values locally
   - Never assume broker is available

### From Initial PLC Development

1. **consecutiveFailures counter needs careful maintenance.**
   - Increment in ALL failure paths
   - Reset on success
   - Use for circuit breaker decisions

2. **age_ms is critical for stale data detection.**
   - CachedAt alone is insufficient
   - Must compute and compare age
   - Quality must degrade with age

3. **Watchdog detects silent degradation.**
   - Track actual vs expected scan time
   - Warn on 2× overrun
   - Escalate on sustained overrun

---

## ✅ SUCCESS CRITERIA

**Sprint 1 is complete when:**

### Functional
- [ ] All S1 tasks implemented
- [ ] All S1 tasks tested
- [ ] All S1 tasks committed
- [ ] No regressions in existing functionality
- [ ] Soak test passed (30+ minutes)

### Stability
- [ ] No crashes
- [ ] No memory leaks
- [ ] No thread leaks
- [ ] No infinite loops
- [ ] No reconnect storms
- [ ] CPU stable
- [ ] Memory stable

### Observability
- [ ] Logs clean (no spam)
- [ ] State transitions visible
- [ ] Errors actionable
- [ ] Metrics exposed
- [ ] Diagnostics endpoint working

### Documentation
- [ ] All changes documented
- [ ] Commit messages clear
- [ ] Architecture doc updated
- [ ] Lessons learned captured

**Only after ALL criteria pass → Proceed to Sprint 2.**

---

## 🚀 FINAL NOTES

**This methodology exists because:**
- Industrial systems require extreme reliability
- PLC connectivity bugs can halt production
- Small incremental changes are safer than large refactors
- Testing after every change catches regressions immediately
- Rollback is trivial when changes are small
- Commit history becomes useful documentation

**Remember:**
> "If it ain't broke, don't fix it."  
> "If it is broke, fix ONLY that."  
> "If you break something else, rollback immediately."

**Success in industrial software is measured by:**
- Uptime (not features)
- Stability (not performance)
- Predictability (not cleverness)
- Maintainability (not elegance)

**Follow these instructions. Build incrementally. Test thoroughly. Ship reliably.**

---

**END OF DEVELOPMENT INSTRUCTIONS**
