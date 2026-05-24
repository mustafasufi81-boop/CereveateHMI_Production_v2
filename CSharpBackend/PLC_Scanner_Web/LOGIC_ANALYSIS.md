# PLC Scanner Web vs Enhanced - Complete Logic Analysis

## ✅ SCENARIO 1: Value CHANGES
**Flow:** PLC scan → Value different from last time → Add to cache

### Enhanced Logic (Line 1699-1707):
```python
if value_changed:
    tag_cache.put(tag, ts_utc, raw_value, quality)  ✅
    last_scanned_values[tag] = raw_value             ✅
    changed_count += 1
```

### Web Logic (Line 454-462):
```python
if value_changed:
    tag_cache.put(tag, ts_utc, processed_value, 'G')  ✅
    last_scanned_values[tag] = processed_value        ✅
    changed_count += 1
else:
    last_scanned_values[tag] = processed_value        ✅ BETTER!
```

**STATUS:** ✅ **WEB IS CORRECT** - Even has extra safety in `else` block!

---

## ✅ SCENARIO 2: Value NOT Changed
**Flow:** PLC scan → Value same as last time → Skip cache, but track value

### Enhanced Logic:
```python
# No else block - does NOT update last_scanned_values
# This is a minor bug in enhanced version
```

### Web Logic (Line 464-465):
```python
else:
    # Still update last_scanned_values for future comparison
    last_scanned_values[tag] = processed_value  ✅
```

**STATUS:** ✅ **WEB IS BETTER** - Handles unchanged values properly!

---

## ❌ SCENARIO 3: DB Writer - Call Every Second
**Flow:** DB thread wakes up → Checks cache → Writes changed values

### Enhanced Logic (Line 1491):
```python
write_interval = 1.0  # Check every 1 second ✅
time.sleep(write_interval)
```

### Web Logic (Line 207):
```python
DB_WRITE_INTERVAL = 2  # seconds ❌ WRONG!
time.sleep(DB_WRITE_INTERVAL)
```

**STATUS:** ❌ **ISSUE: Web checks every 2 seconds, should be 1 second**

---

## ✅ SCENARIO 4: 2-Minute Forced Write
**Flow:** Even if value unchanged → After 2 minutes → Force write to DB

### Enhanced Logic (Line 1536-1542):
```python
if tag_id in last_write_time_per_tag:
    time_since_last_write = (current_time - last_write_time_per_tag[tag_id]).total_seconds()
    if time_since_last_write >= forced_write_interval:  # 120 seconds
        force_write = True
        forced_write_count += 1
```

### Web Logic (Line 527-534):
```python
if tag_id in last_write_time_per_tag:
    time_since_last_write = (current_time - last_write_time_per_tag[tag_id]).total_seconds()
    if time_since_last_write >= FORCED_WRITE_INTERVAL:  # 120 seconds
        force_write = True
        forced_write_count += 1
```

**STATUS:** ✅ **WEB IS CORRECT**

---

## ❌ SCENARIO 5: DB Write SUCCESS → Clear Cache
**Flow:** DB write successful → Clean old cache entries (keep recent for retry)

### Enhanced Logic (Line 1582-1585):
```python
if db_success:
    # Clean old cache (keep last 10 seconds) ✅
    cleanup_time = current_time - timedelta(seconds=10)
    tag_cache.clear_old(cleanup_time)
```

### Web Logic (Line 542-546):
```python
if db_success:
    # Normal cleanup: keep last 5 MINUTES ❌ WRONG!
    cleanup_time = current_time - timedelta(minutes=5)
    tag_cache.clear_old(cleanup_time)
```

**STATUS:** ❌ **ISSUE: Web keeps 5 minutes, should be 10 seconds**

**WHY 10 SECONDS IS CORRECT:**
- Cache is ONLY for DB writes, NOT for UI display
- UI reads from `last_scanned_values` dictionary (not cache)
- Keeping 5 minutes wastes memory
- 10 seconds buffer is enough for DB retry scenarios

---

## ✅ SCENARIO 6: DB Write FAILED → Check Size Before Emergency Cleanup
**Flow:** DB write failed → Check cache size → Only cleanup if too large

### Enhanced Logic (Line 1589-1594):
```python
# Check cache size - emergency cleanup ONLY if cache too large
needs_cleanup, total_values = tag_cache.check_emergency_cleanup()
if needs_cleanup:
    before, after = tag_cache.emergency_cleanup()
    ui.log("WARNING", f"🚨 EMERGENCY CLEANUP: {before} → {after}")
```

### Web Logic (Line 548-552):
```python
# Emergency cleanup check
needs_cleanup, total_values = tag_cache.check_emergency_cleanup()
if needs_cleanup:
    before, after = tag_cache.emergency_cleanup()
    print(f"🚨 EMERGENCY CLEANUP: {before} → {after} values")
```

**STATUS:** ✅ **WEB IS CORRECT** - Checks size before emergency cleanup!

---

## 🎯 SUMMARY OF ALL SCENARIOS

| Scenario | Enhanced | Web | Status |
|----------|----------|-----|--------|
| 1. Value Changes | ✅ Correct | ✅ Correct | MATCH |
| 2. Value NOT Changed | ⚠️ Minor bug | ✅ Fixed | WEB BETTER |
| 3. DB Check Interval | ✅ 1 second | ❌ 2 seconds | **NEEDS FIX** |
| 4. 2-Min Forced Write | ✅ Correct | ✅ Correct | MATCH |
| 5. Cache Cleanup (Success) | ✅ 10 seconds | ❌ 5 minutes | **NEEDS FIX** |
| 6. Emergency Cleanup (Fail) | ✅ Size check | ✅ Size check | MATCH |

---

## 🔧 REQUIRED FIXES IN WEB VERSION

### Fix 1: DB Write Interval (Line 207)
```python
# CURRENT (WRONG):
DB_WRITE_INTERVAL = 2  # seconds

# SHOULD BE:
DB_WRITE_INTERVAL = 1  # seconds (check every 1 second for changed values)
```

### Fix 2: Cache Cleanup Time (Line 542-546)
```python
# CURRENT (WRONG):
cleanup_time = current_time - timedelta(minutes=5)

# SHOULD BE:
cleanup_time = current_time - timedelta(seconds=10)
```

**REASON:** Cache is only for DB writes. UI reads from `last_scanned_values`, so no need to keep cache data for 5 minutes. 10 seconds is enough buffer for DB operations.

---

## 📊 COMPLETE DATA FLOW

```
┌─────────────────────────────────────────────────────────────────┐
│ PLC SCAN (Every 1000ms)                                         │
│                                                                 │
│ 1. Read all tags from PLC                                       │
│ 2. For each tag:                                                │
│    IF value changed:                                            │
│      → tag_cache.put(tag, value)  [For DB write]               │
│      → last_scanned_values[tag] = value  [For UI & tracking]   │
│    ELSE (value NOT changed):                                    │
│      → last_scanned_values[tag] = value  [Update tracking]     │
│                                                                 │
│ 3. Web UI Dashboard reads from: last_scanned_values ✅          │
│    (NOT from tag_cache, so no "---" when values don't change)  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ DB WRITER (Every 1 second) ← NEEDS FIX: Currently 2 seconds    │
│                                                                 │
│ 1. Get changed values from tag_cache                            │
│ 2. For each value:                                              │
│    IF value changed from last DB write:                         │
│      → Write to database                                        │
│    ELSE IF 2 minutes elapsed since last write:                 │
│      → Force write to database (keep alive)                     │
│    ELSE:                                                        │
│      → Skip (filter unchanged)                                  │
│                                                                 │
│ 3. IF DB write SUCCESS:                                         │
│      → Clear cache older than 10 seconds ← NEEDS FIX: 5 mins   │
│    ELSE IF DB write FAILED:                                     │
│      → Check cache size                                         │
│      → IF size > 50,000: Emergency cleanup                      │
│      → ELSE: Keep cache (retry next cycle)                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## ✅ WHAT IS WORKING CORRECTLY

1. ✅ Change detection at PLC scan level
2. ✅ Separate cache for DB (only changed values)
3. ✅ Separate tracking for UI (all current values in `last_scanned_values`)
4. ✅ 2-minute forced write for unchanged values
5. ✅ Emergency cleanup only when cache size exceeds limit
6. ✅ Dashboard API reads from `last_scanned_values`, not cache

---

## ⚠️ WHAT NEEDS FIXING

1. ❌ DB write interval: Change from 2 seconds → 1 second
2. ❌ Cache cleanup: Change from 5 minutes → 10 seconds

**These are simple configuration changes, logic is already correct!**
