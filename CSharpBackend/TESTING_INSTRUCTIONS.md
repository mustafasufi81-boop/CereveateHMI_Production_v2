# HMI Functional Testing — Instructions for Tester

**Document:** TEST_FUNCTIONS_HMI_COMPREHENSIVE.xlsx  
**System:** Cereveate OPC DA Historian Platform  
**Date:** May 2026  
**Prepared by:** Mustafa Shah

---

## 1. Prerequisites — Before You Start

### 1.1 Access Required
| Item | Value |
|------|-------|
| HMI URL | http://localhost:8090 |
| API Base | http://localhost:6001 |
| Login | Username: `Mustafa` / Password: `Admin@123` |
| Database | PostgreSQL — `Automation_DB` @ `localhost:5432` |
| DB Tool | pgAdmin 4 or DBeaver (must be installed) |
| API Tool | Postman or browser (for GET requests) |

### 1.2 Services Must Be Running
Before starting ANY test, verify all three services are up:

```powershell
netstat -ano | findstr "5001 6001 8090" | findstr LISTENING
```

You must see **3 lines** — one for each port.  
If any port is missing, contact the system administrator — do **not** start services yourself.

### 1.3 Database Access Check
Open pgAdmin and confirm you can connect to `Automation_DB`. Run this quick check:

```sql
SELECT count(*) FROM historian_raw.historian_timeseries WHERE time > now() - interval '5 minutes';
```

Result must be **> 0**. If zero, OPC data is not flowing — flag this before testing.

---

## 2. How to Use the Test Document

### 2.1 Excel Sheet Structure
The Excel file has **13 sheets**. Work through them in order:

| Sheet | What to Test |
|-------|-------------|
| 1_Authentication | Login, MFA, session, logout |
| 2_Dashboard_LiveTags | Live tag display, SignalR updates |
| 3_Alarms | Active alarms, ACK, suppress, history |
| 4_Trends_Historical | Charts, date range, export |
| 5_Report_Daily | Daily report, hourly columns |
| 6_Report_Shift | Morning / Evening / Night shift reports |
| 7_Report_Monthly | Monthly rollup report |
| **8_DataMatching_CalcVerify** | ⭐ Manual DB vs UI calculation checks |
| **9_DB_Logs_Verification** | ⭐ Database write and log verification |
| 10_Admin | User management, roles, permissions |
| 11_AssetBrowser | Equipment tree, live tag panel |
| 12_AuditTrail | Audit log entries and filtering |

### 2.2 Columns to Fill In
For **every test row**, you must fill in two columns:

- **Actual Result** — Write exactly what you observed (value, message, behaviour)
- **Status** — Write one of: `PASS` / `FAIL` / `BLOCKED` / `N/A`

Leave no row blank. If a test cannot be run, write `BLOCKED` and explain why in **Remarks**.

### 2.3 Colour Guide
| Row Colour | Meaning |
|-----------|---------|
| White / Light Blue | Standard functional test — follow steps as written |
| **Purple** | Manual calculation step — requires DB query + math (see Section 4) |
| Green | Expected to PASS under normal conditions |
| Orange | Edge case / boundary — pay close attention |

---

## 3. Step-by-Step Testing Approach

### Step 1 — Authentication (Sheet 1)
1. Open http://localhost:8090 in a fresh browser (no saved session)
2. Run each TC in order — TC-A01 through TC-A13
3. For MFA tests (TC-A07 to TC-A09): use Google Authenticator or any TOTP app
4. For JWT tests: capture the token from browser DevTools → Application → Local Storage

### Step 2 — Dashboard & Alarms (Sheets 2 & 3)
1. Login and navigate to the Dashboard
2. Watch tag values for at least 10 seconds before recording
3. For alarm tests: use the API directly via Postman where the test step says "POST /api/..."
4. After each ACK or Suppress action, immediately check the DB (see TC-AL15) to confirm the audit row was written

### Step 3 — Trends (Sheet 4)
1. Select a tag that has at least 7 days of data (e.g. `Random.Real4`)
2. For downsampling test TC-TR07: open both pgAdmin and the chart side by side

### Step 4 — Reports (Sheets 5, 6, 7)
Generate each report type for **2026-05-19** (a date known to have full data).

> ⚠️ **Important:** The Daily Report day starts at **05:00 IST**, not midnight.  
> The first column in the report = "5 am To 6 am". If you see a different first column, record as FAIL.

For each report:
1. Generate in the UI → record what you see
2. Export to Excel → open and spot-check values
3. Then run the **purple calculation verification rows** (Section 4 below)

---

## 4. Calculation Verification — Purple Rows (Critical)

These rows require you to manually query the database and compare results to the UI.  
**Take your time here — this is the most important part of the test.**

### 4.1 How to Run the SQL Queries
1. Open pgAdmin → connect to `Automation_DB`
2. Open Query Tool (Tools → Query Tool)
3. Copy the SQL from the **Test Steps** column exactly as written
4. Replace placeholders like `<tag_id>` with `Random.Real4` and `<date>` with `2026-05-19`
5. Note the result in the **Actual Result** column

### 4.2 How to Verify Hourly Average (TC-RD06 example)

**DB Query:**
```sql
SELECT AVG(value_num) AS db_avg
FROM historian_raw.historian_timeseries
WHERE tag_id = 'Random.Real4'
  AND time >= '2026-05-19 06:00:00+05:30'
  AND time  < '2026-05-19 07:00:00+05:30';
```

**UI Check:**  
Go to Daily Report → 2026-05-19 → Find row `Random.Real4` → Note the value in column **"6 am To 7 am"**

**Pass Condition:**  
`|DB AVG  −  UI Value| ≤ 0.01`

### 4.3 How to Verify Daily Summary AVG (TC-RD09)

The daily **Avg** column is NOT `sum(all_raw_values) / 24`.  
It is: `sum(hourly_averages) / count(non-null hours)`

**Example:**  
If a tag has data for 20 hours out of 24, the denominator is **20**, not **24**.

**Verify in API:**
```
GET http://localhost:6001/api/reports/daily?date=2026-05-19&plant=Plant001&area=AreaA
```
Find the `hourly` array for `Random.Real4`. Count non-null entries → that is your denominator.  
Calculate: `round(sum(non_null_values) / count, 2)` → compare to the `avg` field.

### 4.4 Cross-Report Consistency Check (TC-DM08 — Most Important)

The **daily report avg** for 2026-05-19 must equal the **monthly report column "19"** for May 2026.

1. Generate Daily Report → note avg for `Random.Real4` = **A**
2. Generate Monthly Report (May 2026) → note value in column **19** for same tag = **B**
3. **A must equal B** — if they differ, this is a critical FAIL

---

## 5. DB Log Verification — Sheet 9

For every user action in the UI, the system must write a log row to the database. You must verify this.

### Actions to Check and Where to Look

| UI Action | Table to Check | SQL |
|-----------|----------------|-----|
| Login | `historian_meta.user_sessions` | `SELECT * FROM historian_meta.user_sessions ORDER BY created_at DESC LIMIT 1` |
| Generate Report | `historian_meta.report_gen_log` | `SELECT * FROM historian_meta.report_gen_log ORDER BY generated_at DESC LIMIT 1` |
| ACK Alarm | `historian_raw.alarm_audit_trail` | `SELECT * FROM historian_raw.alarm_audit_trail ORDER BY event_time DESC LIMIT 1` |
| Create User | `historian_meta.user_actions_audit` | `SELECT * FROM historian_meta.user_actions_audit ORDER BY created_at DESC LIMIT 1` |

**How to test:**  
Perform the action in the UI → immediately switch to pgAdmin → run the SQL → confirm the new row has:
- Correct `user` / `operator` = `Mustafa`
- Timestamp = within the last 30 seconds
- Correct action/type field

---

## 6. What Counts as a PASS vs FAIL

| Status | When to Use |
|--------|-------------|
| **PASS** | Actual result matches expected result exactly (or within ±0.01 for numeric values) |
| **FAIL** | Any deviation — wrong value, missing row, crash, wrong message, calculation mismatch |
| **BLOCKED** | Test cannot run (service down, no data, missing prerequisite) — describe reason |
| **N/A** | Test step not applicable in the current environment |

> **Never mark PASS if you are unsure.** Write `BLOCKED` or `FAIL` with a note — it is always better to flag a concern than to miss a defect.

---

## 7. Reporting Defects

For every **FAIL**, record in the **Remarks** column:
1. What you expected
2. What you actually saw (exact value or message)
3. Steps to reproduce
4. Screenshot reference (name the screenshot file as `TC-RD06_fail.png` etc.)

Compile all FAILs into a summary email with the completed Excel attached.

---

## 8. Quick Reference — Key SQL Queries

```sql
-- 1. Check live data flowing
SELECT count(*) FROM historian_raw.historian_timeseries
WHERE time > now() - interval '2 minutes';

-- 2. Hourly averages for a tag on a date
SELECT local_hour, avg_val, min_val, max_val
FROM historian_raw.v_daily_hourly_agg
WHERE tag_id = 'Random.Real4' AND local_date = '2026-05-19'
ORDER BY local_hour;

-- 3. Raw rows for a specific hour
SELECT time AT TIME ZONE 'Asia/Kolkata' AS ist_time, value_num, quality
FROM historian_raw.historian_timeseries
WHERE tag_id = 'Random.Real4'
  AND time >= '2026-05-19 08:00:00+05:30'
  AND time  < '2026-05-19 09:00:00+05:30'
ORDER BY time;

-- 4. Last 5 audit entries
SELECT * FROM historian_meta.user_sessions ORDER BY created_at DESC LIMIT 5;

-- 5. Check for duplicate rows
SELECT tag_id, time, count(*) FROM historian_raw.historian_timeseries
GROUP BY tag_id, time HAVING count(*) > 1 LIMIT 5;

-- 6. Tags enabled for DB logging
SELECT tag_id, enabled, deadband_value FROM historian_meta.tag_master WHERE enabled = TRUE;
```

---

## 9. Estimated Testing Time

| Module | Estimated Time |
|--------|---------------|
| Auth + Dashboard | 30 min |
| Alarms (full) | 45 min |
| Trends | 30 min |
| Reports (Daily + Shift + Monthly) | 60 min |
| **Data Matching / Calc Verify** | **90 min** ← allow extra time |
| DB Log Verification | 45 min |
| Admin + Assets + Audit | 30 min |
| **Total** | **~5.5 hours** |

---

*For any issues with access, DB connectivity, or unclear test steps — contact Mustafa before proceeding.*
