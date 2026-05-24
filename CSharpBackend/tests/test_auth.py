"""
test_auth.py — Automated tests for Authentication & Session endpoints
  POST /api/auth/login
  POST /api/auth/mfa/verify
  GET  /api/auth/me
  POST /api/auth/logout
"""
import pytest
import requests

FLASK_BASE = "http://localhost:6001"
LOGIN_USER = "Mustafa"
LOGIN_PASS = "Admin@123"


# ─── helpers ──────────────────────────────────────────────────────────────────
def _login(username=LOGIN_USER, password=LOGIN_PASS):
    return requests.post(f"{FLASK_BASE}/api/auth/login",
                         json={"username": username, "password": password},
                         timeout=10)

def _get_token():
    r = _login()
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


# ─── TC-A01 : valid login ─────────────────────────────────────────────────────
def test_login_valid_credentials():
    r = _login()
    assert r.status_code in (200, 202), f"Expected 200/202, got {r.status_code}: {r.text}"
    body = r.json()
    # Either full token returned or MFA handshake started
    assert "token" in body or body.get("mfaRequired") is True


# ─── TC-A02 : wrong password ──────────────────────────────────────────────────
def test_login_wrong_password():
    r = _login(password="WrongPass999!")
    assert r.status_code == 401, f"Expected 401, got {r.status_code}"
    assert "invalid" in r.json().get("message", "").lower() or \
           "credentials" in r.json().get("message", "").lower()


# ─── TC-A03 : non-existent user ───────────────────────────────────────────────
def test_login_unknown_user():
    r = _login(username="ghost_user_zzz")
    assert r.status_code == 401


# ─── TC-A04 : empty username ──────────────────────────────────────────────────
def test_login_empty_username():
    r = requests.post(f"{FLASK_BASE}/api/auth/login",
                      json={"username": "", "password": LOGIN_PASS},
                      timeout=10)
    assert r.status_code in (400, 401)


# ─── TC-A05 : empty password ──────────────────────────────────────────────────
def test_login_empty_password():
    r = requests.post(f"{FLASK_BASE}/api/auth/login",
                      json={"username": LOGIN_USER, "password": ""},
                      timeout=10)
    assert r.status_code in (400, 401)


# ─── TC-A06 : SQL injection in username ──────────────────────────────────────
def test_login_sql_injection():
    r = _login(username="admin' OR '1'='1")
    assert r.status_code == 401, "SQL injection must not grant access"


# ─── TC-A07 : /api/auth/me with valid token ───────────────────────────────────
def test_auth_me_valid_token():
    token = _get_token()
    if not token:
        pytest.skip("Could not obtain token — check MFA setup")
    r = requests.get(f"{FLASK_BASE}/api/auth/me",
                     headers={"Authorization": f"Bearer {token}"},
                     timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "username" in body or "user" in body


# ─── TC-A08 : /api/auth/me without token ─────────────────────────────────────
def test_auth_me_no_token():
    r = requests.get(f"{FLASK_BASE}/api/auth/me", timeout=10)
    assert r.status_code == 401


# ─── TC-A09 : /api/auth/me with garbage token ────────────────────────────────
def test_auth_me_invalid_token():
    r = requests.get(f"{FLASK_BASE}/api/auth/me",
                     headers={"Authorization": "Bearer totallyinvalidtoken"},
                     timeout=10)
    assert r.status_code == 401


# ─── TC-A10 : missing Content-Type body ──────────────────────────────────────
def test_login_no_body():
    r = requests.post(f"{FLASK_BASE}/api/auth/login", timeout=10)
    assert r.status_code in (400, 415, 422)
