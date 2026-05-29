# Occurrence_ID Population Fix - Implementation Complete

**Date:** May 28, 2026  
**Status:** ✅ IMPLEMENTED  
**Risk Level:** Low (backward compatible, no breaking changes)

---

## Problem Statement

The `alarm_audit_trail` table was showing `occurrence_id = NULL` for all records, preventing proper tracking of alarm lifecycle across multiple occurrences of the same alarm.

**Root Cause Analysis:**
- C# AlarmStateManager correctly writes `occurrence_id` to `historian_events` and `alarm_active` tables ✅
- Python Flask HMI was **NOT** fetching or writing `occurrence_id` when inserting audit trail records ❌

---

## Changes Implemented

### 1. **AlarmAuditDAO.insert_audit_record()** 
**File:** `mqtt_subscriber_service/src/database/alarm_audit_dao.py`

**Changes:**
- ✅ Added `occurrence_id: Optional[str] = None` parameter to method signature (line 52)
- ✅ Updated INSERT statement to include `occurrence_id` column (line 79)
- ✅ Added `occurrence_id` to parameters for HistoricalDataService path (line 102)
- ✅ Added `occurrence_id` to parameters for DatabaseConnection path (line 143)

**Before:**
```python
def insert_audit_record(self, event_id: int, tag_id: str, ..., 
                       metadata: Optional[Dict[str, Any]] = None)
```

**After:**
```python
def insert_audit_record(self, event_id: int, tag_id: str, ..., 
                       occurrence_id: Optional[str] = None,
                       metadata: Optional[Dict[str, Any]] = None)
```

---

### 2. **acknowledge_alarm() Endpoint**
**File:** `HMI/controllers/alarm_controller.py`

**Changes:**
- ✅ Updated SELECT query to fetch `aa.occurrence_id` from alarm_active (line 369)
- ✅ Extract occurrence_id from query result (dict and tuple paths) (lines 380-389)
- ✅ Pass `occurrence_id=occurrence_id` to insert_audit_record() (line 478)

**SQL Change:**
```sql
-- Before
SELECT aa.alarm_key, aa.alarm_state, aa.tag_id,
       aa.priority, aa.raised_value, aa.setpoint_value
FROM historian_raw.alarm_active aa
WHERE aa.current_event_id = %s

-- After
SELECT aa.alarm_key, aa.alarm_state, aa.tag_id,
       aa.priority, aa.raised_value, aa.setpoint_value, aa.occurrence_id
FROM historian_raw.alarm_active aa
WHERE aa.current_event_id = %s
```

---

### 3. **clear_alarm() Endpoint**
**File:** `HMI/controllers/alarm_controller.py`

**Changes:**
- ✅ Updated SELECT query to include `aa.occurrence_id` (line 623)
- ✅ Extract occurrence_id from query result (lines 641-657)
- ✅ Pass `occurrence_id=occurrence_id` to insert_audit_record() (line 730)

---

### 4. **suppress_alarm() Endpoint**
**File:** `HMI/controllers/alarm_controller.py`

**Changes:**
- ✅ Updated SELECT query to include `occurrence_id` (line 2162)
- ✅ Extract occurrence_id from query result (lines 2177-2184)
- ✅ Added `occurrence_id` column to raw SQL INSERT statement (line 2223)

**Note:** suppress_alarm uses raw SQL INSERT instead of AlarmAuditDAO (legacy pattern)

---

### 5. **unsuppress_alarm() Endpoint**
**File:** `HMI/controllers/alarm_controller.py`

**Changes:**
- ✅ Updated SELECT query to include `occurrence_id` (line 2279)
- ✅ Extract occurrence_id from query result (lines 2290-2297)
- ✅ Added `occurrence_id` column to raw SQL INSERT statement (line 2304)

---

## Testing Plan

### Automated Verification Script
**File:** `_verify_occurrence_id_fix.py`

Run this script to verify the fix is working:
```powershell
cd d:\CereveateHMI_Production
python _verify_occurrence_id_fix.py
```

**Script checks:**
1. ✅ Active alarms with occurrence_id in alarm_active table
2. ✅ Recent audit trail records - how many have occurrence_id populated
3. ✅ Consistency check - occurrence_id matches across tables
4. ✅ Statistics - percentage of records with occurrence_id
5. ✅ Action breakdown - which action types have occurrence_id

---

### Manual Testing Steps

1. **Restart HMI Service:**
   ```powershell
   cd d:\CereveateHMI_Production\HMI
   python app.py
   ```

2. **Trigger Test Actions:**
   - ACK an alarm via UI or API
   - CLEAR an alarm via UI or API
   - SUPPRESS an alarm
   - UNSUPPRESS an alarm

3. **Verify Database:**
   ```sql
   -- Check latest audit records
   SELECT audit_id, event_id, action_type, performed_by, occurrence_id
   FROM historian_raw.alarm_audit_trail
   ORDER BY action_timestamp DESC
   LIMIT 10;
   
   -- Should see occurrence_id populated for new records
   ```

4. **Verify API Response:**
   ```powershell
   $login = Invoke-WebRequest -Uri "http://localhost:8090/api/auth/login" -Method POST -ContentType "application/json" -Body '{"username":"admin","password":"admin123"}' -UseBasicParsing | ConvertFrom-Json
   $token = $login.access_token
   
   $r = Invoke-WebRequest -Uri "http://localhost:8090/api/alarms/audit/881456" -UseBasicParsing -Headers @{Authorization="Bearer $token"} | ConvertFrom-Json
   
   # Check audit_trail array - each record should have occurrence_id
   $r.audit_trail | Select-Object action_type, performed_by, occurrence_id
   ```

---

## Expected Behavior

### ✅ After Fix:
- **New audit records:** occurrence_id populated from alarm_active.occurrence_id
- **Old audit records:** occurrence_id remains NULL (no backfill needed)
- **API response:** occurrence_id field present in all audit_trail records
- **Lifecycle tracking:** Can now distinguish between multiple occurrences of same alarm

### ⚠️ Known Limitations:
1. **Historical data:** Existing audit records have NULL occurrence_id (expected - won't be backfilled)
2. **C# dependency:** occurrence_id only populated if C# AlarmStateManager wrote it to alarm_active
3. **Legacy alarms:** Pre-Phase 1 alarms raised before occurrence_id was implemented will have NULL

---

## Backward Compatibility

✅ **100% Backward Compatible:**
- occurrence_id parameter is **optional** (defaults to None)
- Existing code calling insert_audit_record() without occurrence_id still works
- Database schema already has occurrence_id column (added in previous sprint)
- API response includes occurrence_id field (null-safe, React handles gracefully)

**No breaking changes.**

---

## Performance Impact

✅ **Minimal Performance Impact:**
- SELECT queries: +1 column (occurrence_id UUID) - negligible overhead
- INSERT statements: +1 column, +1 parameter - negligible overhead
- Indexes: idx_alarm_audit_occurrence already exists (created in previous sprint)

**Expected impact:** < 1% query time increase

---

## Rollback Plan

If issues occur, rollback is simple:

1. **Revert Python files:**
   ```powershell
   git checkout HEAD~1 HMI/controllers/alarm_controller.py
   git checkout HEAD~1 mqtt_subscriber_service/src/database/alarm_audit_dao.py
   ```

2. **Restart HMI:**
   ```powershell
   cd d:\CereveateHMI_Production\HMI
   python app.py
   ```

**Database schema:** No changes needed (occurrence_id column remains, NULL-safe)

---

## Dependencies

### ✅ Prerequisites (Already Met):
- Database schema: `occurrence_id UUID` column exists in alarm_audit_trail ✅
- Database index: `idx_alarm_audit_occurrence` exists ✅
- C# AlarmStateManager: Writes occurrence_id to alarm_active ✅
- Python AlarmAuditDAO: count_audit_records() method exists ✅

### ⚠️ Upstream Requirements:
- C# AlarmStateManager must continue writing occurrence_id to alarm_active
- alarm_active table must have occurrence_id column populated

---

## Related Documentation

- **Database Schema:** `ALARM_AUDIT_TRAIL_FIX_PLAN.md` (Phase 2)
- **API Enhancement:** `ALARM_AUDIT_TRAIL_FIX_PLAN.md` (Phase 3-4)
- **Testing Results:** `_verify_occurrence_id_fix.py` output
- **Original Issue:** 12 ACK + 4 CLEAR records analysis (`_verify_ack_records.py`)

---

## Implementation Log

| Timestamp | Action | File | Status |
|-----------|--------|------|--------|
| 2026-05-28 | Add occurrence_id parameter | alarm_audit_dao.py | ✅ Complete |
| 2026-05-28 | Update INSERT statement | alarm_audit_dao.py | ✅ Complete |
| 2026-05-28 | Update acknowledge_alarm() | alarm_controller.py | ✅ Complete |
| 2026-05-28 | Update clear_alarm() | alarm_controller.py | ✅ Complete |
| 2026-05-28 | Update suppress_alarm() | alarm_controller.py | ✅ Complete |
| 2026-05-28 | Update unsuppress_alarm() | alarm_controller.py | ✅ Complete |
| 2026-05-28 | Create verification script | _verify_occurrence_id_fix.py | ✅ Complete |
| 2026-05-28 | Create summary document | OCCURRENCE_ID_FIX_SUMMARY.md | ✅ Complete |

---

## Next Steps

1. ✅ **Implementation:** Complete (all files updated)
2. 🔄 **Testing:** Run `_verify_occurrence_id_fix.py` after HMI restart
3. ⏳ **Validation:** Perform test ACK/CLEAR actions and verify occurrence_id populated
4. ⏳ **Monitoring:** Watch for any errors in HMI logs after restart
5. ⏳ **Frontend:** Update React UI to display occurrence_id (separate ticket)

---

## Success Criteria

✅ **Fix is successful if:**
1. `_verify_occurrence_id_fix.py` shows > 0 records with occurrence_id after test actions
2. New audit trail records have occurrence_id matching alarm_active.occurrence_id
3. API response includes occurrence_id in audit_trail array
4. No Python errors in HMI logs after restart
5. Old functionality (ACK/CLEAR/SUPPRESS/UNSUPPRESS) still works correctly

---

## Contact

**Implementation:** GitHub Copilot (Claude Sonnet 4.5)  
**Review:** System Owner  
**Testing:** QA Team  

---

**STATUS: ✅ READY FOR TESTING**
