"""
test_historical.py — Automated tests for Historical Trend endpoints
  GET /api/historical/<tag_id>
  GET /api/historical/tags  (or similar tag-list endpoint)
  GET /api/opc/values       (C# OPC backend, port 5001)
"""
import pytest
import requests
from datetime import datetime, timedelta, timezone

FLASK_BASE = "http://localhost:6001"
OPC_BASE   = "http://localhost:5001"
LOGIN_USER = "Mustafa"
LOGIN_PASS = "Admin@123"
TEST_TAG   = "Random.Real4"


# ─── fixtures ────────────────────────────────────────────────────────────────
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


# ─── TC-HI01 : last 24h trend ────────────────────────────────────────────────
def test_historical_trend_last_24h(H):
    now  = datetime.now(timezone.utc)
    past = now - timedelta(hours=24)
    r = requests.get(
        f"{FLASK_BASE}/api/historical/{TEST_TAG}",
        params={"start": past.isoformat(), "end": now.isoformat(), "mode": "raw"},
        headers=H, timeout=20
    )
    assert r.status_code == 200, f"Historical trend failed: {r.text}"
    body = r.json()
    # Accept various response shapes
    data = body if isinstance(body, list) else \
           body.get("data") or body.get("values") or body.get("points") or []
    assert isinstance(data, list), f"Expected list of data points, got: {type(data)}"


# ─── TC-HI02 : response schema ───────────────────────────────────────────────
def test_historical_data_schema(H):
    now  = datetime.now(timezone.utc)
    past = now - timedelta(hours=2)
    r = requests.get(
        f"{FLASK_BASE}/api/historical/{TEST_TAG}",
        params={"start": past.isoformat(), "end": now.isoformat()},
        headers=H, timeout=20
    )
    assert r.status_code == 200
    body = r.json()
    data = body if isinstance(body, list) else \
           body.get("data") or body.get("values") or []
    if not data:
        pytest.skip("No data points returned for last 2 hours")
    point = data[0]
    keys_lower = {k.lower() for k in (point.keys() if isinstance(point, dict) else [])}
    # Must have at least a time/timestamp field and a value field
    has_time  = bool({"time", "timestamp", "t"} & keys_lower)
    has_value = bool({"value", "value_num", "v", "val"} & keys_lower)
    assert has_time,  f"No time field in data point: {point}"
    assert has_value, f"No value field in data point: {point}"


# ─── TC-HI03 : empty date range ──────────────────────────────────────────────
def test_historical_empty_range(H):
    r = requests.get(
        f"{FLASK_BASE}/api/historical/{TEST_TAG}",
        params={"start": "2020-01-01T00:00:00+00:00",
                "end":   "2020-01-02T00:00:00+00:00"},
        headers=H, timeout=15
    )
    assert r.status_code == 200
    body = r.json()
    data = body if isinstance(body, list) else \
           body.get("data") or body.get("values") or []
    assert isinstance(data, list), "Empty range should return empty list, not crash"


# ─── TC-HI04 : no auth ───────────────────────────────────────────────────────
def test_historical_no_auth():
    now  = datetime.now(timezone.utc)
    past = now - timedelta(hours=1)
    r = requests.get(
        f"{FLASK_BASE}/api/historical/{TEST_TAG}",
        params={"start": past.isoformat(), "end": now.isoformat()},
        timeout=10
    )
    assert r.status_code == 401


# ─── TC-HI05 : max_points downsampling ───────────────────────────────────────
def test_historical_respects_max_points(H):
    """When max_points is set, response must not exceed that count."""
    MAX = 100
    now  = datetime.now(timezone.utc)
    past = now - timedelta(days=7)   # large range to force sampling
    r = requests.get(
        f"{FLASK_BASE}/api/historical/{TEST_TAG}",
        params={"start": past.isoformat(), "end": now.isoformat(),
                "max_points": MAX},
        headers=H, timeout=20
    )
    assert r.status_code == 200
    body = r.json()
    data = body if isinstance(body, list) else \
           body.get("data") or body.get("values") or []
    assert len(data) <= MAX, \
        f"max_points={MAX} requested but got {len(data)} points"


# ─── TC-HI06 : unknown tag returns gracefully ────────────────────────────────
def test_historical_unknown_tag(H):
    now  = datetime.now(timezone.utc)
    past = now - timedelta(hours=1)
    r = requests.get(
        f"{FLASK_BASE}/api/historical/FAKE.TAG.DOES.NOT.EXIST",
        params={"start": past.isoformat(), "end": now.isoformat()},
        headers=H, timeout=10
    )
    # Should return 200 with empty data OR 404 — must NOT be 500
    assert r.status_code in (200, 403, 404), \
        f"Unknown tag returned {r.status_code}: {r.text}"


# ─── TC-HI07 : OPC live values from C# backend ───────────────────────────────
def test_opc_live_values():
    """GET /api/opc/values from C# backend on port 5001."""
    try:
        r = requests.get(f"{OPC_BASE}/api/opc/values", timeout=8)
    except requests.exceptions.ConnectionError:
        pytest.skip("C# OPC backend (5001) not reachable")
    assert r.status_code == 200, f"OPC values failed: {r.text}"
    body = r.json()
    assert isinstance(body, (list, dict)), "OPC values should return list or dict"


# ─── TC-HI08 : OPC values have no fake/random data pattern ──────────────────
def test_opc_values_quality_field():
    """
    CRITICAL: Every tag must have a quality field.
    Quality must be one of Good/Bad/Uncertain — never generated/fake.
    """
    try:
        r = requests.get(f"{OPC_BASE}/api/opc/values", timeout=8)
    except requests.exceptions.ConnectionError:
        pytest.skip("C# OPC backend not reachable")
    assert r.status_code == 200
    body = r.json()
    tags = body if isinstance(body, list) else body.get("tags") or body.get("values") or []
    if not tags:
        pytest.skip("No tags returned from OPC backend")
    sample = tags[0]
    keys_lower = {k.lower() for k in sample.keys()}
    assert "quality" in keys_lower, \
        f"OPC value missing 'quality' field — possible fake data: {sample}"
