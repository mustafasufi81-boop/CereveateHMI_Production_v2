# Sprint 2 Execution Plan — Python HMI + DB Prep + Observability

**Sprint Goal:** Add scan sequence tracking, per-PLC liveness monitoring, database integration, and structured logging to enable full SCADA observability and UI correlation.

**Status:** 🟢 **STARTED** (Sprint 1: 100% complete, all tests passed)

**Prerequisites:**
- ✅ Sprint 1 complete (12/12 tasks, 19/19 tests passed)
- ✅ Database stress tested (500 concurrent requests - 100% success)
- ✅ Backend stable and production-ready
- ✅ PLC connection architecture validated

---

## Sprint 2 Tasks (9 tasks total)

### **Critical Path (Backend → HMI → Database):**

| ID | Task | File | Effort | Priority |
|----|------|------|--------|----------|
| S2-6 | Add `scan_sequence_id` to cache model | `PlcTagValueCacheEntry.cs` | Small | P0 |
| S2-6a | Implement sequence counter in polling loop | `PlcWorker.cs` | Small | P0 |
| S2-1 | Apply `age_ms` calculation to PLC MQTT | `app.py` | Small | P1 |
| S2-2 | Add `last_plc_mqtt_msg_at` liveness tracking | `app.py` | Small | P1 |
| S2-3 | Expose per-PLC transport state API | `app.py` | Small | P1 |
| S2-4 | Insert PLC tags into `tag_master` table | SQL migration | Medium | P2 |
| S2-5 | Assign `plant_id`/`area_id` to PLC tags | SQL migration | Small | P2 |
| S2-7 | Add Serilog JSON logging + correlation IDs | `Program.cs`, `PlcWorker.cs` | Medium | P3 |

### **Optional Optimization (Deferred to Sprint 2.5):**

| ID | Task | File | Effort | Priority |
|----|------|------|--------|----------|
| S2-8 | MQTT ChangedOnly publish mode | PLC MQTT publisher | Medium | P4 |
| S2-9 | Stale change-detection entry purge | PLC MQTT publisher | Small | P4 |

---

## Task Breakdown

### **S2-6: Add `scan_sequence_id` to PlcTagValueCacheEntry**

**Problem:**
- Cache entries have no scan cycle tracking
- UI cannot detect partial/mixed-cycle data
- MQTT payloads not correlated to scan cycles
- OPC already has `SequenceId` field, PLC missing

**Implementation:**
1. Add `SequenceId` property to `PlcTagValueCacheEntry.cs` model
2. Add `public long SequenceId { get; set; }` as Int64/bigint

**File:** `CSharpBackend/Services/PlcTagValueCacheEntry.cs`

**Acceptance Criteria:**
- ✅ Build succeeds with new property
- ✅ No breaking changes to existing code
- ✅ Property serializes to JSON in API responses

**Risk:** LOW (additive change only)

**Estimated Time:** 5 minutes

---

### **S2-6a: Implement Scan Sequence Counter in PlcWorker**

**Problem:**
- No sequence tracking in PLC polling loop
- OPC uses `Interlocked.Increment(ref _sequenceId)` pattern
- PLC needs identical implementation

**Implementation:**
1. Add field to `PlcWorker.cs`: `private long _sequenceId = 0;`
2. In polling loop (after successful PLC read), before cache update:
   ```csharp
   long currentSequenceId = Interlocked.Increment(ref _sequenceId);
   ```
3. Pass `currentSequenceId` to cache entries
4. Pass `currentSequenceId` to MQTT publisher
5. Log sequence in scan cycle logs

**Files:**
- `CSharpBackend/Services/PlcWorker.cs` (polling loop)
- `CSharpBackend/Services/PlcTagValuesPoolService.cs` (cache update signature)
- `CSharpBackend/Services/PlcMqttPublisherService.cs` (MQTT payload)

**Acceptance Criteria:**
- ✅ Sequence increments by 1 on each scan cycle
- ✅ All cache entries from same scan have identical SequenceId
- ✅ MQTT payloads include SequenceId field
- ✅ Logs show scan sequence numbers
- ✅ Thread-safe increment (no race conditions)

**Risk:** LOW (mirrors proven OPC pattern)

**Estimated Time:** 20 minutes

---

### **S2-1: Apply `age_ms` Calculation to PLC MQTT in Python HMI**

**Problem:**
- Python HMI `on_mqtt_message()` computes `age_ms` for OPC MQTT path
- PLC MQTT path does not compute `age_ms`
- UI cannot show "stale X seconds ago" for PLC tags

**Implementation:**
1. Open `HMI/app.py`
2. Find `on_mqtt_message()` function (~L2300)
3. Locate PLC MQTT handling code block
4. Add `age_ms = _compute_age_ms(entry)` for each PLC tag
5. Mirror OPC pattern exactly

**File:** `HMI/app.py`

**Acceptance Criteria:**
- ✅ PLC tags have `age_ms` field in browser
- ✅ UI shows "stale X seconds ago" for PLC tags
- ✅ `age_ms` calculation identical to OPC path
- ✅ No performance degradation

**Risk:** LOW (mirrors existing OPC code)

**Estimated Time:** 10 minutes

---

### **S2-2: Add Per-PLC MQTT Liveness Tracking**

**Problem:**
- `_transport_state["last_mqtt_msg_at"]` tracks all MQTT messages (OPC + PLC)
- When PLC offline but OPC alive, Python cannot distinguish sources
- Need separate `last_plc_mqtt_msg_at` timestamp

**Implementation:**
1. Add `last_plc_mqtt_msg_at` field to `_transport_state` dict initialization
2. In `on_mqtt_message()`, when processing PLC MQTT messages:
   ```python
   _transport_state["last_plc_mqtt_msg_at"] = time.time()
   ```
3. Update liveness check logic to use per-source timestamps

**File:** `HMI/app.py`

**Acceptance Criteria:**
- ✅ `last_plc_mqtt_msg_at` updates on PLC MQTT messages only
- ✅ `last_mqtt_msg_at` updates on all MQTT messages (OPC + PLC)
- ✅ `/api/system-status` shows both timestamps
- ✅ Can detect "PLC offline, OPC alive" scenario

**Risk:** LOW (additive field)

**Estimated Time:** 10 minutes

---

### **S2-3: Expose Per-PLC Transport State in `/api/system-status`**

**Problem:**
- `/api/system-status` endpoint shows overall MQTT liveness
- No per-PLC transport metrics exposed
- UI cannot show per-connection health

**Implementation:**
1. Add `plc_transport` section to `/api/system-status` JSON response
2. Include:
   - `last_plc_mqtt_msg_at` timestamp
   - `plc_mqtt_age_seconds` (time since last PLC message)
   - `plc_mqtt_alive` boolean (< 30s threshold)
3. Keep existing OPC transport metrics

**File:** `HMI/app.py` (system-status endpoint)

**Acceptance Criteria:**
- ✅ API returns `plc_transport` object
- ✅ Fields populated correctly
- ✅ No breaking changes to existing response structure
- ✅ UI can consume per-PLC metrics

**Risk:** LOW (additive API field)

**Estimated Time:** 10 minutes

---

### **S2-4: Insert PLC Tags into `tag_master` Table**

**Problem:**
- PLC tags defined in `appsettings.json` only
- Not in `historian_meta.tag_master` database table
- No DB historization for PLC tags
- No RBAC area assignment possible

**Implementation:**
1. Create SQL migration script: `migrations/002_add_plc_tags_to_tag_master.sql`
2. Query existing PLC tags from C# backend config
3. Insert records into `tag_master`:
   ```sql
   INSERT INTO historian_meta.tag_master (tag_name, data_source, description, enabled)
   VALUES ('Rockwell_PLC_001.Temperature', 'PLC', 'PLC temperature sensor', true);
   ```
4. Set appropriate defaults for `plant_id`, `area_id`, `unit`, `data_type`

**Files:**
- New: `migrations/002_add_plc_tags_to_tag_master.sql`
- Update: Migration tracking table

**Acceptance Criteria:**
- ✅ All PLC tags inserted into `tag_master`
- ✅ `data_source` = 'PLC' to distinguish from OPC
- ✅ Tags show in HMI tag browser
- ✅ No duplicate tag names
- ✅ Migration idempotent (can run multiple times safely)

**Risk:** MEDIUM (database schema change)

**Estimated Time:** 30 minutes

---

### **S2-5: Assign `plant_id`/`area_id` to PLC Tags**

**Problem:**
- PLC tags have no plant/area assignment
- RBAC area filtering won't work for PLC tags
- Users with area restrictions can't access PLC data

**Implementation:**
1. Create SQL migration script: `migrations/003_assign_plc_tag_areas.sql`
2. Update PLC tags with appropriate `plant_id` and `area_id`:
   ```sql
   UPDATE historian_meta.tag_master
   SET plant_id = 1, area_id = 101  -- Production Line 1
   WHERE tag_name LIKE 'Rockwell_PLC_001.%';
   ```
3. Match area assignments to physical plant layout

**Files:**
- New: `migrations/003_assign_plc_tag_areas.sql`

**Acceptance Criteria:**
- ✅ All PLC tags assigned to plant and area
- ✅ RBAC filtering works for PLC tags
- ✅ Users with area restrictions see correct PLC tags
- ✅ No orphaned tags (NULL plant_id/area_id)

**Risk:** LOW (data-only change)

**Estimated Time:** 15 minutes

---

### **S2-7: Add Serilog JSON Logging + Correlation IDs**

**Problem:**
- Template-style structured logging exists
- No JSON sink for log aggregation
- No correlation IDs across scan → MQTT → browser
- Cannot trace request flow through system

**Implementation:**
1. Install Serilog NuGet packages:
   - `Serilog.AspNetCore`
   - `Serilog.Sinks.File`
   - `Serilog.Formatting.Compact` (JSON formatter)
2. Configure Serilog in `Program.cs`:
   ```csharp
   Log.Logger = new LoggerConfiguration()
       .WriteTo.File(new CompactJsonFormatter(), "logs/plc-gateway-.json", rollingInterval: RollingInterval.Day)
       .CreateLogger();
   ```
3. Add correlation IDs to scan cycle logs in `PlcWorker.cs`:
   ```csharp
   _logger.LogInformation("Scan cycle complete {PlcId} {ScanSeq} {TagCount}", 
       _config.PlcId, currentSequenceId, tagCount);
   ```
4. Add correlation IDs to MQTT publish logs
5. Add correlation IDs to API endpoint logs

**Files:**
- `CSharpBackend/Program.cs` (Serilog configuration)
- `CSharpBackend/OpcDaWebBrowser.csproj` (NuGet packages)
- `CSharpBackend/Services/PlcWorker.cs` (add correlation fields)
- `CSharpBackend/Services/PlcMqttPublisherService.cs` (add correlation fields)

**Acceptance Criteria:**
- ✅ JSON log files created in `logs/` directory
- ✅ Each log entry has structured fields (PlcId, ScanSeq, TagCount)
- ✅ Correlation IDs present in logs
- ✅ Can trace scan cycle → MQTT publish → API request
- ✅ Log aggregation tools can parse JSON format
- ✅ Performance impact < 5% (async logging)

**Risk:** MEDIUM (logging infrastructure change)

**Estimated Time:** 45 minutes

---

## Testing Plan

### **Unit Tests:**

1. **Sequence Counter Test:**
   - Verify `Interlocked.Increment` works correctly
   - Verify no race conditions under concurrent load
   - Verify sequence resets to 0 on restart

2. **Age Calculation Test:**
   - Verify `age_ms` computed correctly for PLC tags
   - Verify staleness detection threshold (30s)

3. **Liveness Tracking Test:**
   - Verify `last_plc_mqtt_msg_at` updates on PLC messages only
   - Verify OPC messages don't affect PLC liveness timestamp

### **Integration Tests:**

1. **Scan Sequence Propagation:**
   - Trigger PLC scan cycle
   - Verify all cache entries have same SequenceId
   - Verify MQTT payload includes SequenceId
   - Verify UI receives SequenceId

2. **Database Tag Integration:**
   - Query `/api/tags` endpoint
   - Verify PLC tags appear with correct plant/area
   - Verify RBAC filtering works for PLC tags

3. **Structured Logging:**
   - Trigger scan cycle
   - Check JSON log file
   - Verify correlation IDs present
   - Verify log fields match schema

### **System Tests:**

1. **End-to-End Correlation:**
   - Find SequenceId in backend log
   - Find same SequenceId in MQTT payload log
   - Find same SequenceId in HMI received message log
   - Verify full trace through system

2. **Per-PLC Liveness:**
   - Stop PLC MQTT publishing
   - Verify `plc_mqtt_alive` becomes false
   - Verify OPC still shows alive
   - Restart PLC MQTT
   - Verify `plc_mqtt_alive` becomes true

---

## Sprint 2 Execution Strategy

### **Phase 1: Backend Foundation (S2-6, S2-6a)**
- Add SequenceId model field
- Implement sequence counter in polling loop
- Test sequence propagation through cache and MQTT
- **Duration:** 30 minutes
- **Risk:** LOW

### **Phase 2: Python HMI Updates (S2-1, S2-2, S2-3)**
- Apply age_ms calculation to PLC path
- Add per-PLC liveness tracking
- Expose transport metrics in API
- **Duration:** 30 minutes
- **Risk:** LOW

### **Phase 3: Database Integration (S2-4, S2-5)**
- Create SQL migrations
- Insert PLC tags into tag_master
- Assign plant/area IDs
- Test RBAC filtering
- **Duration:** 45 minutes
- **Risk:** MEDIUM (database changes)

### **Phase 4: Observability (S2-7)**
- Install Serilog packages
- Configure JSON logging
- Add correlation IDs
- Test log aggregation
- **Duration:** 45 minutes
- **Risk:** MEDIUM (infrastructure change)

### **Phase 5: Validation & Testing**
- Run unit tests
- Run integration tests
- Run system tests
- Performance validation
- **Duration:** 60 minutes
- **Risk:** LOW

### **Total Estimated Duration:** 3-4 hours

---

## Success Criteria

Sprint 2 is complete when:

✅ **Sequence Tracking:**
- All PLC cache entries have SequenceId
- MQTT payloads include SequenceId field
- UI can detect partial/mixed scan cycles

✅ **Age Calculation:**
- PLC tags show accurate `age_ms` in UI
- Stale detection works for PLC tags

✅ **Liveness Monitoring:**
- Per-PLC MQTT liveness tracked separately
- `/api/system-status` shows per-source metrics
- UI can distinguish PLC offline from OPC offline

✅ **Database Integration:**
- All PLC tags in `tag_master` table
- Plant/area IDs assigned correctly
- RBAC filtering works for PLC tags

✅ **Structured Logging:**
- JSON logs created in `logs/` directory
- Correlation IDs present (PlcId, ScanSeq, TagCount)
- Can trace scan → MQTT → browser flow

✅ **No Regressions:**
- All Sprint 1 tests still pass
- System performance maintained
- No new errors in logs

---

## Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Database migration fails | Low | High | Test on dev database first; have rollback script ready |
| Sequence counter overflow | Very Low | Medium | Use `long` (Int64) — max 9 quintillion, 292 billion years at 1000 scans/s |
| Serilog performance impact | Low | Medium | Use async logging; monitor CPU/memory; disable if > 5% impact |
| Breaking changes to API | Very Low | High | Add new fields only; no field removals or renames |

---

## Deferred to Sprint 2.5 (Optional Optimizations)

### **S2-8: MQTT ChangedOnly Publish Mode**
- **Why defer:** Bandwidth optimization, not critical for MVP
- **Benefit:** Reduces MQTT traffic by ~70-90% (only changed tags published)
- **Effort:** Medium (requires `_lastPublishedValue` dictionary)
- **Risk:** LOW (proven OPC pattern)

### **S2-9: Stale Change-Detection Entry Purge**
- **Why defer:** Memory leak prevention for disabled tags
- **Benefit:** Prevents unbounded memory growth
- **Effort:** Small (mirror OPC `PruneStaleChangeDetectionEntries()`)
- **Risk:** LOW (proven OPC pattern)

---

## Sprint 2 Acceptance Testing

Run the following tests to validate Sprint 2 completion:

```powershell
# Test 1: Verify SequenceId in API response
$response = Invoke-RestMethod -Uri "http://localhost:5001/api/plc/values"
$response[0].SequenceId  # Should be present and incrementing

# Test 2: Verify age_ms for PLC tags
$hmiResponse = Invoke-RestMethod -Uri "http://localhost:5000/api/latest-tag-values"
$hmiResponse | Where-Object { $_.source -eq 'PLC' } | Select-Object tag_name, age_ms

# Test 3: Verify per-PLC liveness
$status = Invoke-RestMethod -Uri "http://localhost:5000/api/system-status"
$status.plc_transport.plc_mqtt_alive  # Should be true/false

# Test 4: Verify PLC tags in database
# (Run in PostgreSQL client)
SELECT tag_name, data_source, plant_id, area_id 
FROM historian_meta.tag_master 
WHERE data_source = 'PLC';

# Test 5: Verify JSON logs created
Test-Path "d:\CereveateHMI_Production\CSharpBackend\logs\plc-gateway-*.json"
Get-Content "d:\CereveateHMI_Production\CSharpBackend\logs\plc-gateway-*.json" -Tail 10
```

---

## Sprint 2 Completion Checklist

**Before Starting:**
- [ ] Sprint 1 fully complete (12/12 tasks)
- [ ] Sprint 1 tests all passing (19/19 tests)
- [ ] Backend stable and running
- [ ] Database accessible

**During Development:**
- [ ] S2-6: SequenceId added to model
- [ ] S2-6a: Sequence counter implemented
- [ ] S2-1: age_ms applied to PLC MQTT
- [ ] S2-2: Per-PLC liveness tracking added
- [ ] S2-3: Transport API updated
- [ ] S2-4: PLC tags in tag_master
- [ ] S2-5: Plant/area IDs assigned
- [ ] S2-7: Serilog JSON logging configured
- [ ] Unit tests passing
- [ ] Integration tests passing
- [ ] System tests passing

**After Completion:**
- [ ] All Sprint 1 tests still passing
- [ ] No performance regression
- [ ] No new errors in logs
- [ ] Documentation updated
- [ ] Code committed with clear commit messages

---

## Next Steps

Once Sprint 2 is complete, proceed to **Sprint 3** (React HMI + Deployment Hardening):
- Stale quality visual in UI
- "Last data: Xs ago" indicator
- Mosquitto hardening (auth, TLS)
- Config versioning + validation
- Write path gate documentation
- Redundancy/HA strategy documentation

**Estimated Sprint 3 Duration:** 4-6 hours

---

**Document Version:** 1.0  
**Created:** May 27, 2026  
**Status:** Ready to execute  
**Dependencies:** Sprint 1 complete ✅  
**Blocking Issues:** None  
