"""
Pool Audit Script
=================
Run from:  WEB_HMI_MFA\HMI\
  python _audit_pool.py

Checks:
  1. db_pool.py can be imported
  2. Pool initialises successfully with real DB creds
  3. A real query works through the pool
  4. Every service that was migrated can import db_pool (no leftover psycopg2.connect)
  5. Verifies no service still calls psycopg2.connect() directly in _get_conn
  6. Verifies alarm_controller._get_db_conn uses the pool
  7. Confirms pool returns connections correctly (acquire + release 15x)
"""

import sys
import os
import json
import importlib
import inspect

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

PASS = "\033[92m  PASS\033[0m"
FAIL = "\033[91m  FAIL\033[0m"
INFO = "\033[94m  INFO\033[0m"

results = []

def check(label, ok, detail=""):
    status = PASS if ok else FAIL
    print(f"{status}  {label}" + (f"  →  {detail}" if detail else ""))
    results.append((label, ok))


# ── 1. Load config ─────────────────────────────────────────────────────────────
print("\n=== 1. Load config.json ===")
try:
    with open(os.path.join(ROOT, "config.json")) as f:
        cfg = json.load(f)
    db_cfg = cfg["database"]
    check("config.json loaded", True, f"db={db_cfg.get('database')} host={db_cfg.get('host')}")
except Exception as e:
    check("config.json loaded", False, str(e))
    sys.exit(1)


# ── 2. Import db_pool ──────────────────────────────────────────────────────────
print("\n=== 2. Import db_pool ===")
try:
    import db_pool
    check("import db_pool", True)
except Exception as e:
    check("import db_pool", False, str(e))
    sys.exit(1)


# ── 3. Init pool ───────────────────────────────────────────────────────────────
print("\n=== 3. Initialise pool ===")
try:
    db_pool.init_pool(db_cfg, minconn=2, maxconn=15)
    status = db_pool.pool_status()
    check("init_pool()", True, str(status))
except Exception as e:
    check("init_pool()", False, str(e))
    sys.exit(1)


# ── 4. Real query through pool ────────────────────────────────────────────────
print("\n=== 4. Real query through pool ===")
try:
    from psycopg2.extras import RealDictCursor
    with db_pool.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT current_database() AS db, current_user AS usr, version() AS ver")
            row = cur.fetchone()
    check("SELECT current_database()", True,
          f"db={row['db']} user={row['usr']}")
    print(f"{INFO}  PG version: {row['ver'][:60]}")
except Exception as e:
    check("SELECT current_database()", False, str(e))


# ── 5. Acquire all 15 connections, then release ───────────────────────────────
print("\n=== 5. Pool stress — acquire 15 connections simultaneously ===")
try:
    import db_pool as _dp
    conns = []
    for i in range(15):
        conns.append(_dp._pool.getconn())
    check("Acquired 15/15 connections", True)
    for c in conns:
        _dp._pool.putconn(c)
    check("Released all 15 connections", True)
except Exception as e:
    check("Pool stress test", False, str(e))


# ── 6. Verify each service uses pool (no raw psycopg2.connect in _get_conn) ───
print("\n=== 6. Service migration audit ===")
SERVICES = [
    ("services.rbac_service",                  "RBACService"),
    ("services.audit_service",                 "AuditService"),
    ("services.session_service",               "SessionService"),
    ("services.equipment_permission_service",  "EquipmentPermissionService"),
    ("services.shift_service",                 "ShiftService"),
    ("services.approval_service",              "ApprovalService"),
    ("services.temporary_permission_service",  "TemporaryPermissionService"),
    ("services.area_access_service",           "AreaAccessService"),
    ("services.auth_service",                  "AuthService"),
    ("services.license_service",               "LicenseService"),
]

for mod_name, class_name in SERVICES:
    try:
        mod = importlib.import_module(mod_name)
        cls = getattr(mod, class_name)
        src = inspect.getsource(cls._get_conn)
        uses_pool    = "db_pool" in src
        uses_raw     = "psycopg2.connect" in src
        ok = uses_pool and not uses_raw
        check(
            f"{class_name}._get_conn uses pool",
            ok,
            ("OK" if ok else f"uses_pool={uses_pool} raw_connect={uses_raw}")
        )
    except Exception as e:
        check(f"{class_name}._get_conn uses pool", False, str(e))


# ── 7. alarm_controller._get_db_conn ─────────────────────────────────────────
print("\n=== 7. alarm_controller._get_db_conn audit ===")
try:
    alarm_path = os.path.join(ROOT, "controllers", "alarm_controller.py")
    with open(alarm_path, encoding="utf-8") as f:
        src = f.read()
    # Find just the _get_db_conn function body
    start = src.find("def _get_db_conn()")
    snippet = src[start:start+400]
    uses_pool = "db_pool" in snippet
    uses_raw  = "psycopg2.connect" in snippet
    ok = uses_pool and not uses_raw
    check("alarm_controller._get_db_conn uses pool", ok,
          ("OK" if ok else f"uses_pool={uses_pool} raw_connect={uses_raw}"))
except Exception as e:
    check("alarm_controller._get_db_conn audit", False, str(e))


# ── 8. Confirm no other _get_conn still calls psycopg2.connect ───────────────
print("\n=== 8. Full scan — any remaining raw psycopg2.connect in _get_conn ===")
import re
scan_dirs = [
    os.path.join(ROOT, "services"),
    os.path.join(ROOT, "controllers"),
]
found_raw = []
for d in scan_dirs:
    for fname in os.listdir(d):
        if not fname.endswith(".py"):
            continue
        fpath = os.path.join(d, fname)
        with open(fpath, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        in_get_conn = False
        for i, line in enumerate(lines):
            if re.search(r"def _get_conn\b|def _get_db_conn\b", line):
                in_get_conn = True
            if in_get_conn and "psycopg2.connect" in line:
                found_raw.append(f"{fname}:{i+1}  {line.strip()}")
                in_get_conn = False
            if in_get_conn and line.strip().startswith("def ") and "_get_conn" not in line and "_get_db_conn" not in line:
                in_get_conn = False

if found_raw:
    for f in found_raw:
        print(f"\033[91m  STILL RAW\033[0m  {f}")
    check("No remaining raw psycopg2.connect in _get_conn/_get_db_conn", False,
          f"{len(found_raw)} file(s) still raw")
else:
    check("No remaining raw psycopg2.connect in _get_conn/_get_db_conn", True)


# ── Summary ────────────────────────────────────────────────────────────────────
print("\n=== SUMMARY ===")
passed = sum(1 for _, ok in results if ok)
failed = sum(1 for _, ok in results if not ok)
print(f"  Passed: {passed}   Failed: {failed}   Total: {len(results)}")
if failed:
    print("\n  FAILED checks:")
    for label, ok in results:
        if not ok:
            print(f"    ✗ {label}")
    sys.exit(1)
else:
    print("\n  \033[92mAll checks passed — shared pool is fully wired.\033[0m")
