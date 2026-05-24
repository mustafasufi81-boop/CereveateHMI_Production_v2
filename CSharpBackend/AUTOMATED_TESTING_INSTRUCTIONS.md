# Automated Testing Instructions
## Tool: pytest + requests + psycopg2

---

## Why pytest?

| Tool | Role |
|------|------|
| **pytest** | Runs and reports all tests. Industry standard. |
| **requests** | Makes real HTTP calls to Flask API (port 6001) and OPC backend (port 5001) |
| **psycopg2** | Direct PostgreSQL connection — queries DB to verify calculations |
| **pytest-html** | Generates a clean HTML report you can open in any browser |

No Selenium. No browser automation. Tests call the APIs directly — fast, reliable, runs in seconds.

---

## File Layout

```
project_root/
│
├── RUN_TESTS.bat              ← Double-click to run ALL tests
├── RUN_SINGLE_TEST.bat        ← Run one test file at a time
│
└── tests/
    ├── conftest.py            ← Shared config (URLs, credentials, DB connection)
    ├── requirements_test.txt  ← Libraries needed (auto-installed by RUN_TESTS.bat)
    │
    ├── test_auth.py           ← Login, MFA, JWT, session tests (10 tests)
    ├── test_alarms.py         ← Active, ACK, suppress, history, trips (11 tests)
    ├── test_reports.py        ← Daily/Shift/Monthly — incl. calc verification (16 tests)
    ├── test_historical.py     ← Trend charts, downsampling, OPC live values (8 tests)
    └── test_db_calculations.py← Direct DB: agg match, no duplicates, quality (10 tests)
```

**Total: 55 automated tests**

---

## Prerequisites

### 1. All three services must be running

```powershell
netstat -ano | findstr "5001 6001 8090" | findstr LISTENING
```

Must show 3 lines before you run tests. If any are missing, start them first.

### 2. Python virtual environment must exist

The `.venv` folder is at:
```
c:\MQTT_Implemented_OPC\...\BACKUP_20251206\.venv\
```

This is already set up. The bat files use it automatically.

---

## How to Run

### Option A — Run ALL tests (recommended)

1. Open Windows Explorer
2. Navigate to the project root folder
3. Double-click **`RUN_TESTS.bat`**
4. A console window opens — watch tests run
5. When done, **`test_report.html`** opens automatically in your browser

### Option B — Run ONE test file

Double-click **`RUN_SINGLE_TEST.bat`**, OR open cmd and run:

```cmd
RUN_SINGLE_TEST.bat test_reports.py
```

Available files:
```
test_auth.py
test_alarms.py
test_reports.py
test_historical.py
test_db_calculations.py
```

### Option C — Run a single specific test

```cmd
cd tests
..\.venv\Scripts\python.exe -m pytest test_reports.py::test_daily_report_avg_calculation -v
```

---

## Reading the Console Output

```
tests/test_auth.py::test_login_valid_credentials         PASSED   [ 10%]
tests/test_auth.py::test_login_wrong_password            PASSED   [ 20%]
tests/test_reports.py::test_daily_report_avg_calculation FAILED   [ 55%]
```

| Symbol | Meaning |
|--------|---------|
| `PASSED` | Test passed ✅ |
| `FAILED` | Test failed ❌ — details shown below |
| `SKIPPED` | Test skipped (usually: no data for that date, or service not reachable) |
| `ERROR` | Test could not run at all (setup problem) |

At the end you see:
```
5 failed, 48 passed, 2 skipped in 34.21s
```

---

## Reading the HTML Report

The file **`tests/test_report.html`** opens automatically after `RUN_TESTS.bat` finishes.

- Green rows = PASSED
- Red rows = FAILED — click to expand and see the exact failure message
- Yellow rows = SKIPPED — shows why

**Share this HTML file** with Mustafa after testing. It is self-contained (single file, no internet needed).

---

## What Each Test File Covers

### `test_auth.py` — 10 tests
- Valid login returns 200 or 202
- Wrong password → 401
- SQL injection in username → 401 (security check)
- `/api/auth/me` with valid/invalid/no token
- Empty username / password handled

### `test_alarms.py` — 11 tests
- Active alarm list loads and has correct schema (id, tag_id, alarm_time, severity)
- Alarm stats has severity keys
- History date range query works
- Suppressed / trips / interlocks endpoints return 200
- Acknowledging a fake alarm ID fails gracefully (not 500)

### `test_reports.py` — 16 tests
- Areas endpoint returns plant/area list
- Daily report: 200, has rows, 24 hourly columns
- **Calculation check**: `avg` = `round(sum(non-null hourly) / count, 2)` ← automated
- **Calculation check**: `max` = `max(hourly_max values)` ← automated
- **Calculation check**: `min` = `min(hourly_min values)` ← automated
- Missing params → 400, invalid date → 400, empty date → 200 with empty rows
- No auth → 401
- Export → Excel content-type
- Shifts list returns at least 1 shift
- Monthly vs Daily cross-check: day column must equal daily report avg

### `test_historical.py` — 8 tests
- Last 24h trend returns data with time + value fields
- Empty date range → 200 with empty list (no crash)
- No auth → 401
- `max_points` parameter is respected (≤ 100 points returned)
- Unknown tag → 200/404, never 500
- OPC live values from C# backend: 200, has `quality` field (CRITICAL: no fake data)

### `test_db_calculations.py` — 10 tests (direct DB, no HTTP)
- Data flowing in last 5 minutes
- No NULL tag_id rows
- No future timestamps
- No duplicate (tag_id, time) pairs in last hour
- Quality values are valid (G/B/U/C only)
- **`v_daily_hourly_agg.avg_val` matches `AVG(value_num)` from raw table** ← key check
- **`ts_hourly_agg` matches `v_daily_hourly_agg`** ← both agg tables agree
- `report_gen_log` is populated
- All enabled tags have data in last 10 minutes
- All 24 hours present in agg for yesterday

---

## Customising Test Settings

Edit **`tests/conftest.py`** to change:

```python
FLASK_BASE = "http://localhost:6001"   # Flask API port
OPC_BASE   = "http://localhost:5001"   # C# OPC port
DB_DSN     = "host=localhost ..."      # DB connection
LOGIN_USER = "Mustafa"
LOGIN_PASS = "Admin@123"
TEST_TAG   = "Random.Real4"            # tag used for all data checks
TEST_DATE  = "2026-05-19"              # override if needed
```

Or set environment variables before running:
```cmd
set TEST_TAG=YourTag.Name
set TEST_DATE=2026-05-15
RUN_TESTS.bat
```

---

## Common Issues & Fixes

| Problem | Cause | Fix |
|---------|-------|-----|
| `ConnectionRefusedError` on port 6001 | Flask not running | Start `app.py` first |
| All tests `SKIPPED` | No data for TEST_DATE | Change `TEST_DATE` in conftest.py |
| `ModuleNotFoundError: pytest` | pip install failed | Run: `.venv\Scripts\pip install pytest requests psycopg2-binary pytest-html` |
| `test_db_calculations` all skip | DB not accessible | Check PostgreSQL is running, check DB_DSN credentials |
| MFA tests fail | MFA token expired | Default token `123456` should always work as fallback |
| `test_daily_report_avg_calculation FAILED` | Real bug in report | Investigate: avg formula may be wrong — escalate |

---

## After Testing

1. Close the console window
2. Open `tests/test_report.html` in browser (if not auto-opened)
3. Take a screenshot of the summary line: `X failed, Y passed, Z skipped`
4. Send `test_report.html` to Mustafa with the completed manual Excel

---

## Combined Manual + Automated Coverage

| Module | Manual (Excel) | Automated (pytest) | Coverage |
|--------|---------------|-------------------|----------|
| Authentication | ✅ 13 TCs | ✅ 10 tests | Full |
| Alarms | ✅ 21 TCs | ✅ 11 tests | Full API |
| Reports — Daily | ✅ 15 TCs | ✅ 10 tests incl. calc | Full |
| Reports — Shift | ✅ 11 TCs | ✅ 3 tests | API + calc |
| Reports — Monthly | ✅ 8 TCs | ✅ 3 tests incl. cross-check | Full |
| Historical Trends | ✅ 11 TCs | ✅ 8 tests | Full |
| DB Calculations | ✅ 11 TCs | ✅ 10 tests | Full |
| Admin / Assets / Audit | ✅ 25 TCs | — | Manual only (UI) |

The automated tests focus on **API correctness and calculation accuracy**.  
The manual Excel covers **UI behaviour, visual checks, and admin flows** that cannot be automated without a browser.

**Both must pass before sign-off.**
