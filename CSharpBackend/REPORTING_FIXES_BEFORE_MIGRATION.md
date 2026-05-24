# REPORTING CODE FIXES - BEFORE PHASE 1 MIGRATION

## PURPOSE
Fix all reporting code issues **BEFORE** running Phase 1 migration.
Migration is ONE-TIME and irreversible. Code must be correct first.

---

## CRITICAL ISSUES FOUND

### Issue 1: Column name mismatch in current view
**File**: `WEB_HMI_MFA/HMI/migrations/010_report_views.sql`

**Current view uses**: `opc_timestamp` column
```sql
FROM historian_raw.historian_timeseries ht
WHERE ht.quality = 'G'
```

**But actual table has**: `time` column (not `opc_timestamp`)
**Source**: `Services/HistorianIngest/DB/production_schema.sql` line 77

```sql
CREATE TABLE IF NOT EXISTS historian_timeseries (
    time TIMESTAMPTZ NOT NULL,  -- ← ACTUAL COLUMN NAME
    tag_id TEXT NOT NULL,
    ...
```

**Impact**: Current view may be broken or using wrong column

**Fix Required**: Update view to use `time` instead of `opc_timestamp`

---

### Issue 2: Hardcoded hour boundaries (6 AM assumption)
**File**: `WEB_HMI_MFA/HMI/services/report_service.py`

**Lines**: 119-120 (daily report)
```python
cursor.execute(
    """
    SELECT tag_id, local_date, local_hour AS hour, avg_val, max_val, min_val
    FROM historian_raw.v_daily_hourly_agg
    WHERE tag_id = ANY(%s)
      AND (
          (local_date = %s AND local_hour >= 6)  -- ← HARDCODED 6 AM
          OR
          (local_date = %s AND local_hour < 6)   -- ← HARDCODED 6 AM
      )
```

**Problem**: Daily reports assume 6 AM start time is hardcoded
**But**: Architecture document says shift boundaries should come from database

**Current plant schedule**:
- Shift-A: 05:00 → 13:00  (NOT 6 AM!)
- Shift-B: 13:00 → 21:00
- Shift-C: 21:00 → 05:00

**Fix Required**: 
1. Remove hardcoded 6 AM assumption
2. Daily report should cover full calendar day (00:00 → 23:59)
3. Shift reports already use database-driven shift times (GOOD)

---

### Issue 3: Monthly report hitting wrong view
**File**: `WEB_HMI_MFA/HMI/services/report_service.py`

**Line 463** (monthly report):
```python
SELECT tag_id, local_date, local_hour AS hour, avg_val
FROM historian_raw.v_daily_hourly_agg  -- ← WRONG!
WHERE tag_id = ANY(%s)
```

**Problem**: Monthly reports query HOURLY aggregate
**Architecture says**: "monthly reports must never hit raw historian directly"
**Architecture says**: "monthly reports should use daily aggregate layers"

**Fix Required**: 
- Monthly reports should aggregate from hourly data in Python code
- OR create daily aggregate after Phase 1 stabilizes (Phase 1.5)

---

### Issue 4: Timezone handling inconsistency
**Current view** uses: `AT TIME ZONE 'Asia/Kolkata'`
**Production schema** uses: `TIMESTAMPTZ` (UTC storage)

**Architecture document says**:
- "store source event/report timestamps as TIMESTAMPTZ in UTC"
- "perform official rendering into plant-local timezone at report generation time"

**Current approach**: Converting in view (acceptable for Phase 1)
**Future**: Timezone should be configurable, not hardcoded in SQL

---

## FIXES TO APPLY BEFORE MIGRATION

### Fix 1: Update current view to use correct column
**File**: `WEB_HMI_MFA/HMI/migrations/010_report_views.sql`

Replace entire view with:
```sql
CREATE OR REPLACE VIEW historian_raw.v_daily_hourly_agg AS
SELECT
    ht.tag_id,
    DATE(ht.time AT TIME ZONE 'Asia/Kolkata') AS local_date,
    EXTRACT(HOUR FROM ht.time AT TIME ZONE 'Asia/Kolkata')::INT AS hour,
    ROUND(AVG(ht.value_num)::NUMERIC, 2) AS avg_val,
    ROUND(MAX(ht.value_num)::NUMERIC, 2) AS max_val,
    ROUND(MIN(ht.value_num)::NUMERIC, 2) AS min_val
FROM historian_raw.historian_timeseries ht
WHERE ht.quality = 'G'
  AND ht.value_num IS NOT NULL
GROUP BY
    ht.tag_id,
    DATE(ht.time AT TIME ZONE 'Asia/Kolkata'),
    EXTRACT(HOUR FROM ht.time AT TIME ZONE 'Asia/Kolkata');
```

**Key change**: `opc_timestamp` → `time`

---

### Fix 2: Remove hardcoded 6 AM assumption from daily reports
**File**: `WEB_HMI_MFA/HMI/services/report_service.py`

**Current logic** (lines 119-129):
```python
AND (
    (local_date = %s AND local_hour >= 6)
    OR
    (local_date = %s AND local_hour < 6)
)
```

**Fixed logic**:
```python
AND local_date = %s
```

**Full corrected query**:
```python
cursor.execute(
    """
    SELECT
        tag_id,
        local_date,
        local_hour AS hour,
        avg_val,
        max_val,
        min_val
    FROM historian_raw.v_daily_hourly_agg
    WHERE tag_id = ANY(%s)
      AND local_date = %s
    ORDER BY tag_id, local_date, local_hour
    """,
    (tag_ids, report_date),
)
```

**Also update**: Hour column ordering in `_ordered_hours()` method
```python
@staticmethod
def _ordered_hours() -> List[int]:
    # Calendar day order: 00:00 → 23:00
    return list(range(24))  # [0, 1, 2, ..., 23]
```

**Also update**: `_hour_columns()` to match calendar day
```python
@staticmethod
def _hour_columns() -> List[str]:
    return [
        "12 am To 1 am",
        "1 am To 2 am",
        "2 am To 3 am",
        # ... (full 24 hours in calendar order)
    ]
```

---

### Fix 3: Monthly report - aggregate in Python instead of hitting hourly view repeatedly
**File**: `WEB_HMI_MFA/HMI/services/report_service.py`

**Current approach** (line 463):
```python
SELECT tag_id, local_date, local_hour AS hour, avg_val
FROM historian_raw.v_daily_hourly_agg
WHERE tag_id = ANY(%s)
  AND (
      (local_date >= %s AND local_date <= %s AND local_hour >= 6)
      OR
      (local_date >= %s AND local_date <= %s AND local_hour < 6)
  )
```

**Fixed approach**:
```python
# Query once for full date range
cursor.execute(
    """
    SELECT
        tag_id,
        local_date,
        AVG(avg_val) AS daily_avg,
        MAX(max_val) AS daily_max,
        MIN(min_val) AS daily_min
    FROM historian_raw.v_daily_hourly_agg
    WHERE tag_id = ANY(%s)
      AND local_date >= %s
      AND local_date <= %s
    GROUP BY tag_id, local_date
    ORDER BY tag_id, local_date
    """,
    (tag_ids, from_date, to_date),
)
```

**Benefit**:
- Single query instead of per-day queries
- Aggregates hourly data into daily in database
- Prepares code for future daily aggregate layer

---

## TESTING SEQUENCE (BEFORE MIGRATION)

### Test 1: Fix current view
```bash
psql -h localhost -U cereveate -d Automation_DB -f WEB_HMI_MFA\HMI\migrations\010_report_views_FIXED.sql
```

### Test 2: Verify view works
```sql
SELECT * FROM historian_raw.v_daily_hourly_agg 
WHERE local_date = CURRENT_DATE 
LIMIT 10;
```

### Test 3: Test daily report with fixes
```bash
# Call Flask API endpoint
curl http://localhost:6001/api/reports/daily?date=2026-05-18&plant=BALCO&area=CPP
```

### Test 4: Test monthly report with fixes
```bash
curl "http://localhost:6001/api/reports/monthly?from_date=2026-05-01&to_date=2026-05-31&plant=BALCO&area=CPP"
```

### Test 5: Test shift report (should already work)
```bash
curl "http://localhost:6001/api/reports/shift?date=2026-05-18&shift_code=A&plant=BALCO&area=CPP"
```

---

## ONLY AFTER ALL TESTS PASS

### Then run Phase 1 migration:
```bash
RUN_PHASE1_MIGRATION.bat
```

**Migration changes**:
- Drops current view
- Creates `ca_hourly` continuous aggregate
- Creates compatibility view over `ca_hourly`
- Adds refresh policy

**Report code changes needed**: NONE (compatibility view maintains same interface)

---

## POST-MIGRATION VALIDATION

### Test 1: Wait for first refresh cycle (10 minutes)
```bash
RUN_PHASE1_MONITORING.bat
```

### Test 2: Verify continuous aggregate has data
```sql
SELECT COUNT(*) FROM historian_raw.ca_hourly;
SELECT MIN(hour_bucket), MAX(hour_bucket) FROM historian_raw.ca_hourly;
```

### Test 3: Re-test all report endpoints
```bash
# Daily
curl http://localhost:6001/api/reports/daily?date=2026-05-18&plant=BALCO&area=CPP

# Shift
curl "http://localhost:6001/api/reports/shift?date=2026-05-18&shift_code=A&plant=BALCO&area=CPP"

# Monthly
curl "http://localhost:6001/api/reports/monthly?from_date=2026-05-01&to_date=2026-05-31&plant=BALCO&area=CPP"
```

### Test 4: Compare performance before/after
- Measure query latency
- Check database load
- Verify continuous aggregate is being used

---

## ROLLBACK PLAN

If tests fail after migration:
```bash
RUN_PHASE1_ROLLBACK.bat
```

This will:
- Drop continuous aggregate
- Restore normal SQL view
- System returns to pre-migration state

---

## SUMMARY

| Step | Action | Status |
|------|--------|--------|
| 1 | Fix current view (`time` column) | Required |
| 2 | Remove hardcoded 6 AM from daily reports | Required |
| 3 | Fix monthly report aggregation | Required |
| 4 | Test all report endpoints | Required |
| 5 | Run Phase 1 migration | After tests pass |
| 6 | Validate post-migration | After migration |
| 7 | Monitor 24-48 hours | After validation |

**CRITICAL**: Do NOT run migration until Steps 1-4 complete successfully.
