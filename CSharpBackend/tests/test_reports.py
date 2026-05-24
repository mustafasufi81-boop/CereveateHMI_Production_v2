"""
test_reports.py — Automated tests for Report endpoints
  GET /api/reports/areas
  GET /api/reports/daily
  GET /api/reports/daily/export
  GET /api/reports/shifts
  GET /api/reports/shift
  GET /api/reports/monthly
  GET /api/reports/monthly/export
"""
import pytest
import requests
from datetime import date, timedelta

FLASK_BASE  = "http://localhost:6001"
LOGIN_USER  = "Mustafa"
LOGIN_PASS  = "Admin@123"
TEST_DATE   = str(date.today() - timedelta(days=1))   # yesterday — should have data


# ─── module-level fixtures ────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{FLASK_BASE}/api/auth/login",
                      json={"username": LOGIN_USER, "password": LOGIN_PASS},
                      timeout=10)
    body = r.json()
    if body.get("mfaRequired"):
        mfa = requests.post(
            f"{FLASK_BASE}/api/auth/mfa/verify",
            json={"token": "123456"},
            headers={"Authorization": f"Bearer {body['tempToken']}"},
            timeout=10
        )
        return mfa.json().get("token")
    return body.get("token")

@pytest.fixture(scope="module")
def H(token):
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture(scope="module")
def area_info(H):
    """Fetch the first available plant/area combo from the API."""
    r = requests.get(f"{FLASK_BASE}/api/reports/areas", headers=H, timeout=10)
    assert r.status_code == 200, f"Cannot fetch areas: {r.text}"
    areas = r.json().get("areas", [])
    if not areas:
        pytest.skip("No areas configured — all report tests skipped")
    return areas[0]   # {"plant": "...", "area": "..."}


# ─────────────────────────────────────────────────────────────────────────────
# AREAS
# ─────────────────────────────────────────────────────────────────────────────
def test_get_report_areas(H):
    r = requests.get(f"{FLASK_BASE}/api/reports/areas", headers=H, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "areas" in body, f"Missing 'areas' key: {body}"
    assert len(body["areas"]) > 0, "No areas returned — tag_master may be empty"

def test_report_areas_no_auth():
    r = requests.get(f"{FLASK_BASE}/api/reports/areas", timeout=10)
    assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# DAILY REPORT
# ─────────────────────────────────────────────────────────────────────────────
def test_daily_report_returns_200(H, area_info):
    r = requests.get(f"{FLASK_BASE}/api/reports/daily",
                     params={"date": TEST_DATE,
                             "plant": area_info["plant"],
                             "area": area_info["area"]},
                     headers=H, timeout=30)
    assert r.status_code == 200, f"Daily report failed: {r.text}"

def test_daily_report_has_rows(H, area_info):
    r = requests.get(f"{FLASK_BASE}/api/reports/daily",
                     params={"date": TEST_DATE,
                             "plant": area_info["plant"],
                             "area": area_info["area"]},
                     headers=H, timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert "rows" in body, f"No 'rows' key in response: {list(body.keys())}"

def test_daily_report_24_hourly_columns(H, area_info):
    """Every row must have exactly 24 hourly values (5AM→4AM cycle)."""
    r = requests.get(f"{FLASK_BASE}/api/reports/daily",
                     params={"date": TEST_DATE,
                             "plant": area_info["plant"],
                             "area": area_info["area"]},
                     headers=H, timeout=30)
    assert r.status_code == 200
    rows = r.json().get("rows", [])
    if not rows:
        pytest.skip("No data rows returned for the test date")
    first_row = rows[0]
    hourly = first_row.get("hourly") or first_row.get("hours") or []
    assert len(hourly) == 24, \
        f"Expected 24 hourly columns, got {len(hourly)}"

def test_daily_report_avg_calculation(H, area_info):
    """
    row['avg'] must equal round(sum(non-null hourly) / count(non-null hourly), 2).
    This is the critical calculation verification test.
    """
    r = requests.get(f"{FLASK_BASE}/api/reports/daily",
                     params={"date": TEST_DATE,
                             "plant": area_info["plant"],
                             "area": area_info["area"]},
                     headers=H, timeout=30)
    assert r.status_code == 200
    rows = r.json().get("rows", [])
    if not rows:
        pytest.skip("No data rows")

    failures = []
    for row in rows[:10]:   # check first 10 tags
        hourly = row.get("hourly") or row.get("hours") or []
        non_null = [v for v in hourly if v is not None]
        if not non_null:
            continue
        expected_avg = round(sum(non_null) / len(non_null), 2)
        actual_avg   = row.get("avg")
        if actual_avg is None:
            continue
        if abs(float(actual_avg) - expected_avg) > 0.02:
            failures.append(
                f"Tag {row.get('tag_id','?')}: "
                f"expected_avg={expected_avg}, API avg={actual_avg}"
            )
    assert not failures, "Avg calculation mismatch:\n" + "\n".join(failures)

def test_daily_report_max_is_max_of_hourly_maxes(H, area_info):
    """row['max'] must equal max of all hourly max values."""
    r = requests.get(f"{FLASK_BASE}/api/reports/daily",
                     params={"date": TEST_DATE,
                             "plant": area_info["plant"],
                             "area": area_info["area"]},
                     headers=H, timeout=30)
    assert r.status_code == 200
    rows = r.json().get("rows", [])
    if not rows:
        pytest.skip("No data rows")

    failures = []
    for row in rows[:10]:
        hourly_max = row.get("hourly_max") or []
        non_null   = [v for v in hourly_max if v is not None]
        if not non_null:
            continue
        expected = round(max(non_null), 2)
        actual   = row.get("max")
        if actual is not None and abs(float(actual) - expected) > 0.02:
            failures.append(
                f"Tag {row.get('tag_id','?')}: expected_max={expected}, API max={actual}"
            )
    assert not failures, "Max calculation mismatch:\n" + "\n".join(failures)

def test_daily_report_min_is_min_of_hourly_mins(H, area_info):
    """row['min'] must equal min of all hourly min values."""
    r = requests.get(f"{FLASK_BASE}/api/reports/daily",
                     params={"date": TEST_DATE,
                             "plant": area_info["plant"],
                             "area": area_info["area"]},
                     headers=H, timeout=30)
    assert r.status_code == 200
    rows = r.json().get("rows", [])
    if not rows:
        pytest.skip("No data rows")

    failures = []
    for row in rows[:10]:
        hourly_min = row.get("hourly_min") or []
        non_null   = [v for v in hourly_min if v is not None]
        if not non_null:
            continue
        expected = round(min(non_null), 2)
        actual   = row.get("min")
        if actual is not None and abs(float(actual) - expected) > 0.02:
            failures.append(
                f"Tag {row.get('tag_id','?')}: expected_min={expected}, API min={actual}"
            )
    assert not failures, "Min calculation mismatch:\n" + "\n".join(failures)

def test_daily_report_missing_params(H):
    r = requests.get(f"{FLASK_BASE}/api/reports/daily",
                     params={"date": TEST_DATE},  # missing plant & area
                     headers=H, timeout=10)
    assert r.status_code == 400

def test_daily_report_invalid_date(H, area_info):
    r = requests.get(f"{FLASK_BASE}/api/reports/daily",
                     params={"date": "not-a-date",
                             "plant": area_info["plant"],
                             "area": area_info["area"]},
                     headers=H, timeout=10)
    assert r.status_code == 400

def test_daily_report_empty_date(H, area_info):
    """Date with no data must return 200 with empty rows, not crash."""
    r = requests.get(f"{FLASK_BASE}/api/reports/daily",
                     params={"date": "2020-01-01",
                             "plant": area_info["plant"],
                             "area": area_info["area"]},
                     headers=H, timeout=15)
    assert r.status_code == 200
    body = r.json()
    rows = body.get("rows", [])
    assert isinstance(rows, list)

def test_daily_report_no_auth(area_info):
    r = requests.get(f"{FLASK_BASE}/api/reports/daily",
                     params={"date": TEST_DATE,
                             "plant": area_info["plant"],
                             "area": area_info["area"]},
                     timeout=10)
    assert r.status_code == 401

def test_daily_export_returns_excel(H, area_info):
    r = requests.get(f"{FLASK_BASE}/api/reports/daily/export",
                     params={"date": TEST_DATE,
                             "plant": area_info["plant"],
                             "area": area_info["area"]},
                     headers=H, timeout=30)
    assert r.status_code == 200
    ct = r.headers.get("Content-Type", "")
    assert "spreadsheet" in ct or "excel" in ct or "octet" in ct, \
        f"Expected Excel content-type, got: {ct}"


# ─────────────────────────────────────────────────────────────────────────────
# SHIFTS
# ─────────────────────────────────────────────────────────────────────────────
def test_get_shifts_list(H):
    r = requests.get(f"{FLASK_BASE}/api/reports/shifts", headers=H, timeout=10)
    assert r.status_code == 200
    body = r.json()
    shifts = body.get("shifts", [])
    assert len(shifts) >= 1, "Expected at least 1 shift defined"
    first = shifts[0]
    assert "shift_code" in first or "shift_name" in first, \
        f"Shift entry missing expected keys: {first}"

def test_shift_report_morning(H, area_info):
    r = requests.get(f"{FLASK_BASE}/api/reports/shift",
                     params={"date": TEST_DATE,
                             "shift_code": "A",
                             "plant": area_info["plant"],
                             "area": area_info["area"]},
                     headers=H, timeout=30)
    assert r.status_code in (200, 400), \
        f"Unexpected status {r.status_code}: {r.text}"

def test_shift_report_no_auth(area_info):
    r = requests.get(f"{FLASK_BASE}/api/reports/shift",
                     params={"date": TEST_DATE, "shift_code": "A",
                             "plant": area_info["plant"],
                             "area": area_info["area"]},
                     timeout=10)
    assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# MONTHLY REPORT
# ─────────────────────────────────────────────────────────────────────────────
def test_monthly_report_returns_200(H, area_info):
    today = date.today()
    r = requests.get(f"{FLASK_BASE}/api/reports/monthly",
                     params={"year": today.year,
                             "month": today.month,
                             "plant": area_info["plant"],
                             "area": area_info["area"]},
                     headers=H, timeout=30)
    assert r.status_code == 200

def test_monthly_report_day_matches_daily(H, area_info):
    """
    Monthly report value for a specific day must equal the daily report avg
    for that same day. Cross-report consistency check.
    """
    test_day = date.today() - timedelta(days=1)

    # 1. Get daily report avg for test_day
    daily_r = requests.get(f"{FLASK_BASE}/api/reports/daily",
                           params={"date": str(test_day),
                                   "plant": area_info["plant"],
                                   "area": area_info["area"]},
                           headers=H, timeout=30)
    if daily_r.status_code != 200:
        pytest.skip("Daily report unavailable")
    daily_rows = daily_r.json().get("rows", [])
    if not daily_rows:
        pytest.skip("No daily rows to cross-check")

    # 2. Get monthly report for that month
    monthly_r = requests.get(f"{FLASK_BASE}/api/reports/monthly",
                             params={"year": test_day.year,
                                     "month": test_day.month,
                                     "plant": area_info["plant"],
                                     "area": area_info["area"]},
                             headers=H, timeout=30)
    if monthly_r.status_code != 200:
        pytest.skip("Monthly report unavailable")
    monthly_rows = monthly_r.json().get("rows", [])
    if not monthly_rows:
        pytest.skip("No monthly rows to cross-check")

    # 3. Compare first tag that exists in both
    day_col = str(test_day.day)   # e.g. "19"
    mismatches = []
    for d_row in daily_rows[:5]:
        tag = d_row.get("tag_id")
        d_avg = d_row.get("avg")
        if d_avg is None:
            continue
        # find same tag in monthly
        m_row = next((x for x in monthly_rows if x.get("tag_id") == tag), None)
        if not m_row:
            continue
        daily_val = m_row.get("daily", {}).get(day_col) or \
                    m_row.get(day_col)
        if daily_val is None:
            continue
        if abs(float(d_avg) - float(daily_val)) > 0.05:
            mismatches.append(
                f"Tag {tag}: daily_avg={d_avg}, monthly_day{day_col}={daily_val}"
            )
    if mismatches:
        pytest.fail("Daily vs Monthly mismatch:\n" + "\n".join(mismatches))

def test_monthly_report_no_auth(area_info):
    today = date.today()
    r = requests.get(f"{FLASK_BASE}/api/reports/monthly",
                     params={"year": today.year, "month": today.month,
                             "plant": area_info["plant"],
                             "area": area_info["area"]},
                     timeout=10)
    assert r.status_code == 401
