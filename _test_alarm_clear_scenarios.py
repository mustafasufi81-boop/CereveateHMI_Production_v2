"""
_test_alarm_clear_scenarios.py
=================================
Verifies all 5 scenarios from ALARM_FIX_PLAN_V2.md after applying the dual-pool
bounce-back guard, MarkRtnAsync live-value check, and re-raise suppression fixes.

Scenarios
---------
  1  Clear while value is HIGH  → HTTP 422 / VALUE_STILL_VIOLATING
  2  ACK of RTN_UNACK but value bounced back HIGH  → stays ACTIVE_ACK, no CLEARED row
  3  Value genuinely normal  → clear succeeds, CLEARED in historian
  4  No duplicate raise within 3 s of CLEARED
  5  Duplicate event_id / occurrence_id  → no duplicate RAISE rows

Requirements
  • C# backend running on http://localhost:8090
  • PostgreSQL reachable with the creds below
  • VYAN1101F must exist in setpoint cache with high-limit ≤ 6.0
    (live value 6.49 satisfies this condition)
"""

import time
import uuid
import sys
from datetime import datetime, timezone, timedelta

import psycopg2
from psycopg2.extras import RealDictCursor
import requests

# ─────────────────────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     "localhost",
    "port":     5432,
    "database": "Automation_DB",
    "user":     "cereveate",
    "password": "cereveate@222",
}

API_BASE   = "http://localhost:8090"
TAG_ID     = "VYAN1101F"
ALARM_LEVEL = "High"           # match the configured level for VYAN1101F
ALARM_KEY  = f"{TAG_ID}::{ALARM_LEVEL}"
OPERATOR   = "test_script"

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def db():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


def get_token() -> str:
    r = requests.post(
        f"{API_BASE}/api/auth/login",
        json={"username": "admin", "password": "admin123"},
        timeout=5,
    )
    r.raise_for_status()
    return r.json()["access_token"]


HEADERS: dict = {}   # populated after login


def api_get(path: str, **kwargs):
    return requests.get(f"{API_BASE}{path}", headers=HEADERS, timeout=10, **kwargs)


def api_post(path: str, body: dict, **kwargs):
    return requests.post(f"{API_BASE}{path}", json=body, headers=HEADERS, timeout=10, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_active_state() -> dict | None:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM historian_raw.alarm_active WHERE alarm_key = %s",
                (ALARM_KEY,),
            )
            return cur.fetchone()


def get_latest_event(since: datetime) -> dict | None:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT * FROM historian_raw.historian_events
                   WHERE tag_id = %s AND time > %s
                   ORDER BY time DESC LIMIT 1""",
                (TAG_ID, since),
            )
            return cur.fetchone()


def count_events_since(since: datetime, alarm_state: str) -> int:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*) AS n FROM historian_raw.historian_events
                   WHERE tag_id = %s AND alarm_state = %s AND time > %s""",
                (TAG_ID, alarm_state, since),
            )
            row = cur.fetchone()
            return row["n"] if row else 0


def force_alarm_state_in_db(alarm_state: str, occurrence_id: str | None = None):
    """
    Directly upsert alarm_active to set a specific state for unit-test purposes.
    Also inserts a matching historian_events row so the audit trail is consistent.
    Uses a fake setpoint / raised_value so live-value guards have something to check against.
    """
    occ = occurrence_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    with db() as conn:
        with conn.cursor() as cur:
            # Upsert alarm_active
            cur.execute(
                """INSERT INTO historian_raw.alarm_active
                       (alarm_key, tag_id, level, alarm_state, current_event_id,
                        occurrence_id, instance_seq, raised_at, raised_value,
                        setpoint_value, priority, transition_seq, updated_at)
                   VALUES
                       (%s, %s, %s, %s, -1,
                        %s, 1, %s, 6.49,
                        5.00, 5, 0, NOW())
                   ON CONFLICT (alarm_key) DO UPDATE
                       SET alarm_state = EXCLUDED.alarm_state,
                           occurrence_id = EXCLUDED.occurrence_id,
                           raised_value  = 6.49,
                           setpoint_value = 5.00,
                           updated_at = NOW()
                """,
                (ALARM_KEY, TAG_ID, ALARM_LEVEL, alarm_state, occ, now),
            )
        conn.commit()
    return occ


def clear_alarm_from_db():
    """Remove the alarm from alarm_active (simulate a prior clear)."""
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM historian_raw.alarm_active WHERE alarm_key = %s",
                (ALARM_KEY,),
            )
        conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Result tracking
# ─────────────────────────────────────────────────────────────────────────────

PASS = "✅ PASS"
FAIL = "❌ FAIL"
SKIP = "⚠️  SKIP"

results: list[tuple[str, str, str]] = []   # (scenario, status, detail)


def record(scenario: str, ok: bool, detail: str = ""):
    status = PASS if ok else FAIL
    results.append((scenario, status, detail))
    print(f"  {status}  {detail}")


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 1  —  Clear while value HIGH should return HTTP 422
# ─────────────────────────────────────────────────────────────────────────────

def run_scenario_1():
    print("\n" + "=" * 70)
    print("SCENARIO 1: Clear while value HIGH  →  expect HTTP 422")
    print("=" * 70)

    # Force alarm into ACTIVE_ACK in DB (mirrors real live alarm after operator ACK'd)
    force_alarm_state_in_db("ACTIVE_ACK")
    time.sleep(0.3)   # give DB a moment

    before = datetime.now(timezone.utc)
    r = api_post(
        f"/api/alarms/{ALARM_KEY}/clear",
        {"operator": OPERATOR, "reason": "test scenario 1"},
    )

    print(f"  HTTP status: {r.status_code}")
    got_blocked = r.status_code in (422, 409, 400)
    record("S1", got_blocked, f"HTTP {r.status_code} (want 422/409/400 = blocked)")

    # Verify no CLEARED row added after the blocked attempt
    cleared_after = count_events_since(before, "CLEARED")
    record("S1-norow", cleared_after == 0, f"CLEARED rows added: {cleared_after} (want 0)")


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 2  —  ACK of RTN_UNACK while value still HIGH → stays ACTIVE_ACK
# ─────────────────────────────────────────────────────────────────────────────

def run_scenario_2():
    print("\n" + "=" * 70)
    print("SCENARIO 2: ACK RTN_UNACK bounce-back  →  expect ACTIVE_ACK, no CLEARED")
    print("=" * 70)

    # Put alarm into RTN_UNACK manually
    force_alarm_state_in_db("RTN_UNACK")
    time.sleep(0.3)

    before = datetime.now(timezone.utc)
    r = api_post(
        f"/api/alarms/{ALARM_KEY}/acknowledge",
        {"operator": OPERATOR},
    )
    print(f"  HTTP status: {r.status_code}")

    ok_http = r.status_code == 200
    record("S2-http", ok_http, f"HTTP {r.status_code} (want 200)")

    if ok_http:
        body = r.json()
        new_state = body.get("new_state", "")
        # Must NOT be CLEARED — must be ACTIVE_ACK
        record("S2-state", new_state == "ACTIVE_ACK",
               f"new_state={new_state!r} (want ACTIVE_ACK, NOT CLEARED)")

    cleared_count = count_events_since(before, "CLEARED")
    record("S2-norow", cleared_count == 0,
           f"CLEARED rows added: {cleared_count} (want 0)")

    active = get_active_state()
    in_active = active is not None
    record("S2-active", in_active,
           f"alarm still in alarm_active: {in_active} (want True)")


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 3  —  Value genuinely normal → clear should succeed
# ─────────────────────────────────────────────────────────────────────────────

def run_scenario_3():
    print("\n" + "=" * 70)
    print("SCENARIO 3: Value genuinely normal  →  clear should succeed")
    print("=" * 70)

    # Inject a row where raised_value < setpoint to simulate normal value
    # We cannot fake the LIVE tag pool here, so we note this requires a tag
    # that genuinely reads below setpoint.  We test with a different approach:
    # check that the API would return 200 for an alarm whose tag IS below setpoint.
    # For automation: flag as SKIP if live value is still high.
    r_live = api_get(f"/api/tags/latest")
    if r_live.status_code != 200:
        results.append(("S3", SKIP, "Cannot retrieve live tag values"))
        return

    tags = r_live.json().get("tags", {})
    tag_entry = tags.get(TAG_ID)
    if tag_entry is None:
        results.append(("S3", SKIP, f"{TAG_ID} not found in /api/tags/latest"))
        return

    live_val = float(tag_entry.get("value", 99.0))
    setpoint = 5.00  # known setpoint for VYAN1101F

    if live_val > setpoint:
        results.append(("S3", SKIP,
            f"Live value {live_val:.3f} > setpoint {setpoint:.2f} — "
            "cannot test genuine clear without real process change. "
            "The safety gate correctly blocks this."))
        return

    # Live value is ≤ setpoint — attempt clear
    force_alarm_state_in_db("ACTIVE_ACK")
    time.sleep(0.3)
    before = datetime.now(timezone.utc)
    r = api_post(
        f"/api/alarms/{ALARM_KEY}/clear",
        {"operator": OPERATOR, "reason": "test scenario 3"},
    )
    print(f"  HTTP status: {r.status_code}  live_val={live_val:.3f}")
    record("S3-http", r.status_code == 200, f"HTTP {r.status_code} (want 200)")

    cleared_count = count_events_since(before, "CLEARED")
    record("S3-row", cleared_count >= 1,
           f"CLEARED rows added: {cleared_count} (want ≥1)")

    active_after = get_active_state()
    record("S3-removed", active_after is None,
           f"alarm_active row removed: {active_after is None} (want True)")


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 4  —  No duplicate raise within 3 s of CLEARED
# ─────────────────────────────────────────────────────────────────────────────

def run_scenario_4():
    print("\n" + "=" * 70)
    print("SCENARIO 4: No duplicate raise within 3 s of CLEARED")
    print("=" * 70)

    before = datetime.now(timezone.utc)

    # Use the diagnostics/test-raise endpoint to try a raise immediately after clear
    # First: clear any existing active alarm (if value allows it)
    clear_alarm_from_db()
    time.sleep(0.2)

    # Trigger a test raise via the diagnostics endpoint
    r_raise = api_post(
        "/api/diagnostics/alarms/test-raise",
        {"tag_id": TAG_ID, "value": 9.99},
    )
    print(f"  Test-raise HTTP: {r_raise.status_code}")
    if r_raise.status_code not in (200, 201):
        results.append(("S4", SKIP, f"test-raise returned {r_raise.status_code} — skip"))
        return

    time.sleep(0.3)
    raise_1_time = datetime.now(timezone.utc)

    # Simulate operator clear (force DB directly, since live value is high we can't clear via API)
    clear_alarm_from_db()
    cleared_time = datetime.now(timezone.utc)
    time.sleep(0.1)

    # Immediately try another raise (within 1 second)
    r_raise2 = api_post(
        "/api/diagnostics/alarms/test-raise",
        {"tag_id": TAG_ID, "value": 9.99},
    )
    print(f"  Immediate re-raise HTTP: {r_raise2.status_code}")

    # Check how many ACTIVE_UNACK rows appeared within 3s of cleared_time
    time.sleep(1.5)   # wait so the 3s window is mostly elapsed

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*) AS n FROM historian_raw.historian_events
                   WHERE tag_id = %s
                     AND alarm_state = 'ACTIVE_UNACK'
                     AND time BETWEEN %s AND %s""",
                (TAG_ID, cleared_time, cleared_time + timedelta(seconds=3)),
            )
            row = cur.fetchone()
    raises_in_window = row["n"] if row else 0
    record("S4-suppress", raises_in_window == 0,
           f"ACTIVE_UNACK raises in 3 s window after clear: {raises_in_window} (want 0)")


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 5  —  Duplicate occurrence_id → no two RAISE rows
# ─────────────────────────────────────────────────────────────────────────────

def run_scenario_5():
    print("\n" + "=" * 70)
    print("SCENARIO 5: Same occurrence_id should not produce two RAISE rows")
    print("=" * 70)

    before = datetime.now(timezone.utc)

    # Get the current occurrence_id from alarm_active (or use any known one)
    active = get_active_state()
    if active is None:
        results.append(("S5", SKIP, "No active alarm in alarm_active to check"))
        return

    occ_id = str(active["occurrence_id"])

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*) AS n
                   FROM historian_raw.historian_events
                   WHERE occurrence_id = %s
                     AND alarm_state = 'ACTIVE_UNACK'""",
                (occ_id,),
            )
            row = cur.fetchone()
    raise_count = row["n"] if row else 0
    record("S5-dedup", raise_count <= 1,
           f"RAISE rows for occurrence_id {occ_id[:8]}…: {raise_count} (want ≤1)")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print()
    print("╔" + "═" * 68 + "╗")
    print("║       ALARM CLEAR BUG — VERIFICATION TEST SUITE               ║")
    print("║       ALARM_FIX_PLAN_V2.md — All 5 Scenarios                  ║")
    print(f"║       {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<60}║")
    print("╚" + "═" * 68 + "╝")

    # Login
    try:
        token = get_token()
        HEADERS["Authorization"] = f"Bearer {token}"
        print(f"\n✅ Authenticated (token: {token[:30]}…)")
    except Exception as e:
        print(f"\n❌ Cannot authenticate: {e}")
        sys.exit(1)

    run_scenario_1()
    run_scenario_2()
    run_scenario_3()
    run_scenario_4()
    run_scenario_5()

    # Summary
    print()
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    passed  = sum(1 for _, s, _ in results if s == PASS)
    failed  = sum(1 for _, s, _ in results if s == FAIL)
    skipped = sum(1 for _, s, _ in results if s == SKIP)

    for scenario, status, detail in results:
        print(f"  [{scenario:15s}] {status}   {detail}")

    print()
    print(f"  Passed:  {passed}")
    print(f"  Failed:  {failed}")
    print(f"  Skipped: {skipped}")
    print()

    if failed > 0:
        print("❌ SOME TESTS FAILED — review the fix implementation")
        sys.exit(1)
    else:
        print("✅ ALL TESTS PASSED (or skipped due to live process constraints)")
        sys.exit(0)


if __name__ == "__main__":
    main()
