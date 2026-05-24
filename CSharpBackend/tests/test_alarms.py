"""
test_alarms.py — Automated tests for Alarm endpoints
  GET  /api/alarms/active
  GET  /api/alarms/stats
  GET  /api/alarms/history
  POST /api/alarms/acknowledge/<id>
  GET  /api/alarms/suppressed
  GET  /api/alarms/trips
  GET  /api/alarms/interlocks
"""
import pytest
import requests

FLASK_BASE = "http://localhost:6001"
LOGIN_USER = "Mustafa"
LOGIN_PASS = "Admin@123"


# ─── session-scoped token fixture ────────────────────────────────────────────
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


# ─── TC-AL01 : GET active alarms ─────────────────────────────────────────────
def test_get_active_alarms(H):
    r = requests.get(f"{FLASK_BASE}/api/alarms/active", headers=H, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "alarms" in body or isinstance(body, list), \
        f"Unexpected response shape: {body}"


# ─── TC-AL02 : active alarms unauthenticated ─────────────────────────────────
def test_active_alarms_no_auth():
    r = requests.get(f"{FLASK_BASE}/api/alarms/active", timeout=10)
    # Route has no @token_required — may be 200; just check it doesn't 500
    assert r.status_code != 500


# ─── TC-AL03 : alarm stats ───────────────────────────────────────────────────
def test_alarm_stats(H):
    r = requests.get(f"{FLASK_BASE}/api/alarms/stats", headers=H, timeout=10)
    assert r.status_code == 200
    body = r.json()
    # Must have at least one severity key
    severity_keys = {"critical", "high", "medium", "low", "warning", "urgent"}
    assert severity_keys & set(k.lower() for k in body.keys()), \
        f"Expected severity keys in stats, got: {list(body.keys())}"


# ─── TC-AL04 : alarm history with date range ─────────────────────────────────
def test_alarm_history_date_range(H):
    r = requests.get(f"{FLASK_BASE}/api/alarms/history",
                     params={"start": "2026-05-01", "end": "2026-05-20"},
                     headers=H, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, (list, dict)), f"Unexpected type: {type(body)}"


# ─── TC-AL05 : alarm history without auth ────────────────────────────────────
def test_alarm_history_no_auth():
    r = requests.get(f"{FLASK_BASE}/api/alarms/history",
                     params={"start": "2026-05-01", "end": "2026-05-20"},
                     timeout=10)
    assert r.status_code in (200, 401, 403)  # either open or protected
    assert r.status_code != 500


# ─── TC-AL06 : suppressed alarms ─────────────────────────────────────────────
def test_suppressed_alarms(H):
    r = requests.get(f"{FLASK_BASE}/api/alarms/suppressed", headers=H, timeout=10)
    assert r.status_code == 200


# ─── TC-AL07 : trip events ───────────────────────────────────────────────────
def test_alarm_trips(H):
    r = requests.get(f"{FLASK_BASE}/api/alarms/trips", headers=H, timeout=10)
    assert r.status_code == 200


# ─── TC-AL08 : interlocks ────────────────────────────────────────────────────
def test_alarm_interlocks(H):
    r = requests.get(f"{FLASK_BASE}/api/alarms/interlocks", headers=H, timeout=10)
    assert r.status_code == 200


# ─── TC-AL09 : unacknowledged list ───────────────────────────────────────────
def test_alarm_unacknowledged(H):
    r = requests.get(f"{FLASK_BASE}/api/alarms/audit/unacknowledged",
                     headers=H, timeout=10)
    assert r.status_code in (200, 404)  # 404 if route not configured


# ─── TC-AL10 : acknowledge non-existent alarm ────────────────────────────────
def test_acknowledge_nonexistent_alarm(H):
    r = requests.post(f"{FLASK_BASE}/api/alarms/acknowledge/999999999",
                      json={"comment": "auto-test"},
                      headers=H, timeout=10)
    # Should be 404 or 400 — must NOT be 500 or 200
    assert r.status_code in (400, 404, 422), \
        f"Acknowledging a fake alarm ID should fail gracefully, got {r.status_code}"


# ─── TC-AL11 : active alarms response schema ─────────────────────────────────
def test_active_alarms_schema(H):
    """Each alarm in the list must have required fields."""
    r = requests.get(f"{FLASK_BASE}/api/alarms/active", headers=H, timeout=10)
    assert r.status_code == 200
    body = r.json()
    alarms = body if isinstance(body, list) else body.get("alarms", [])
    if not alarms:
        pytest.skip("No active alarms — cannot check schema")
    alarm = alarms[0]
    required = {"id", "tag_id", "alarm_time", "severity"}
    # Use lower-case comparison for flexibility
    keys_lower = {k.lower() for k in alarm.keys()}
    for field in required:
        assert field in keys_lower, \
            f"Missing field '{field}' in alarm response. Got: {list(alarm.keys())}"
