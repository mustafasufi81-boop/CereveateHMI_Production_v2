"""
conftest.py — shared fixtures for the entire test suite.

Provides:
  - flask_api_base  : http://localhost:6001
  - opc_api_base    : http://localhost:5001
  - auth_headers    : valid JWT for Mustafa (admin)
  - db_conn         : live psycopg2 connection to Automation_DB
  - test_tag        : a known tag_id that has recent data
  - test_date       : a date string known to have a full day of data
"""

import os
import pytest
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import date, timedelta

# ─── configuration ────────────────────────────────────────────────────────────
FLASK_BASE  = os.environ.get("FLASK_BASE",  "http://localhost:6001")
OPC_BASE    = os.environ.get("OPC_BASE",    "http://localhost:5001")
DB_DSN      = os.environ.get("DB_DSN",
    "host=localhost port=5432 dbname=Automation_DB user=cereveate password=cereveate@222")
LOGIN_USER  = os.environ.get("TEST_USER",   "Mustafa")
LOGIN_PASS  = os.environ.get("TEST_PASS",   "Admin@123")
MFA_CODE    = os.environ.get("TEST_MFA",    "123456")   # default/fallback MFA token
TEST_TAG    = os.environ.get("TEST_TAG",    "Random.Real4")
TEST_DATE   = os.environ.get("TEST_DATE",   str(date.today() - timedelta(days=1)))


# ─── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def flask_base():
    return FLASK_BASE

@pytest.fixture(scope="session")
def opc_base():
    return OPC_BASE

@pytest.fixture(scope="session")
def test_tag():
    return TEST_TAG

@pytest.fixture(scope="session")
def test_date():
    return TEST_DATE

@pytest.fixture(scope="session")
def db_conn():
    """psycopg2 connection — shared across entire test session."""
    conn = psycopg2.connect(DB_DSN, cursor_factory=RealDictCursor)
    conn.set_session(autocommit=True)
    # Set timezone for all queries
    with conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'Asia/Kolkata'")
    yield conn
    conn.close()

@pytest.fixture(scope="session")
def auth_token(flask_base):
    """
    Perform a full login (+ MFA if required) and return JWT token string.
    """
    resp = requests.post(f"{flask_base}/api/auth/login",
                         json={"username": LOGIN_USER, "password": LOGIN_PASS},
                         timeout=10)
    assert resp.status_code in (200, 202), \
        f"Login failed: {resp.status_code} {resp.text}"

    body = resp.json()

    # MFA required → submit TOTP
    if body.get("mfaRequired"):
        temp = body["tempToken"]
        mfa_resp = requests.post(
            f"{flask_base}/api/auth/mfa/verify",
            json={"token": MFA_CODE},
            headers={"Authorization": f"Bearer {temp}"},
            timeout=10
        )
        # If TOTP path fails, try security-question path
        if mfa_resp.status_code != 200:
            mfa_resp = requests.post(
                f"{flask_base}/api/auth/mfa/verify-security",
                json={"code": MFA_CODE},
                headers={"Authorization": f"Bearer {temp}"},
                timeout=10
            )
        assert mfa_resp.status_code == 200, \
            f"MFA failed: {mfa_resp.status_code} {mfa_resp.text}"
        return mfa_resp.json()["token"]

    return body["token"]

@pytest.fixture(scope="session")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}

# ─── helpers (importable from tests) ──────────────────────────────────────────

def get(flask_base, path, headers, **kwargs):
    return requests.get(f"{flask_base}{path}", headers=headers, timeout=15, **kwargs)

def post(flask_base, path, headers, body=None, **kwargs):
    return requests.post(f"{flask_base}{path}", json=body, headers=headers, timeout=15, **kwargs)
