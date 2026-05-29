# Session Fix Log — 27 May 2026

---

## Fix 1 — Alarm CLEAR Permission Always Denied for Engineer Role

### Symptom
Engineer user clicked **Clear** on any alarm → red toast:  
> **"Clear failed: You do not have permission to clear alarms"**

### Root Cause
`rbac_service.py` → `can_user_clear_alarm()` was querying the **wrong table**.

| | Wrong (before) | Correct (after) |
|---|---|---|
| Table | `historian_meta.role_alarm_permissions` | `historian_meta.role_module_permissions` |
| Column | `can_clear` | `can_operate` |
| Filter | `alarm_category` | `module = 'alarms'` |

The table `role_alarm_permissions` is **never seeded** — it is always empty. So every non-admin user got `0 rows → False → 403 Forbidden`, regardless of what permissions were set in the admin UI.

The seeded table is `role_module_permissions` (column `can_operate = true` for Engineer on module `alarms`). This is what the admin UI writes to and reads from — the permission check was just looking in the wrong place.

### Secondary Bug (same function)
The `requires_approval_to_clear_alarm()` function was also querying `role_alarm_permissions` for a `requires_approval_to_clear` column that doesn't exist. On `0 rows` it defaulted to `return True` (require approval). Since no approval workflow is implemented, this silently blocked every clear even when `can_clear` was somehow true.

### Fix Applied
**File:** `HMI/services/rbac_service.py`

1. `can_user_clear_alarm()` — now queries `role_module_permissions WHERE module='alarms' AND can_operate=true`
2. `requires_approval_to_clear_alarm()` — now returns `False` (no approval workflow exists; old code returned `True` by default on missing rows, permanently blocking clears)

---

## Fix 2 — Alarm Stats Endpoint Crash (RealDictCursor)

### Symptom
`GET /api/alarms/stats` returned 500 error. Alarm panel stats section blank.

### Root Cause
`alarm_controller.py` → `get_alarm_stats()` called `cursor = db_service.connection.cursor(cursor_factory=RealDictCursor)` using:
- `db_service.connection` — a stale single connection object, not the pool
- `RealDictCursor` directly — crashes if `psycopg2.extras` is not importable

### Fix Applied
**File:** `HMI/controllers/alarm_controller.py`

Replaced with `db_pool.get_conn()` (pooled connection) and `HAS_REAL_DICT_CURSOR` guard. Added tuple fallback using `cursor.description` column names so it works even without psycopg2 extras.

---

## Fix 3 — AlarmPanel Snapshot Polls Missing Auth Headers

### Symptom
On page load, the alarm panel 5-second poll to `/api/alarms/active` and `/api/alarms/suppressed` returned 401 Unauthorized in some configurations. ACK/CLEAR worked (had auth) but the polling snapshot silently failed.

### Root Cause
`AlarmPanel.tsx` → `fetchSnapshot()` called `fetch('/api/alarms/active')` and `fetch('/api/alarms/suppressed')` with **no Authorization header**. ACK and CLEAR requests correctly sent `Bearer <token>` but the read polls did not.

### Fix Applied
**File:** `HMI/apex-hmi/src/components/hmi/AlarmPanel.tsx`

Added `localStorage.getItem('auth_token')` read and `Authorization: Bearer <token>` header to both snapshot fetch calls. React app rebuilt (`index-p0372xoK.js`).

---

## Fix 4 — Flask Startup Crash (Wrong Python Interpreter)

### Symptom
`python app.py` crashed at startup with dependency errors (gevent, psycopg2, etc.).

### Root Cause
Flask was being started with **Anaconda system Python** (`C:\Users\mussh\anaconda3\python.exe`) instead of the project `.venv`. The `.venv` has all the correct pinned packages for the HMI. Anaconda Python is missing or has incompatible versions.

### Fix Applied
No code change. Started Flask correctly per `HOW_TO_START.md`:
```cmd
cd D:\CereveateHMI_Production\HMI
start "Flask HMI" cmd /k ".venv\Scripts\activate && python app.py"
```

**Always use `.venv\Scripts\activate` before running `python app.py`.  
Never run it with Anaconda or system Python.**

---

## Current System State (verified 27 May 2026 ~19:40)

| Service | Port | Status |
|---------|------|--------|
| C# OPC/PLC Backend | 5001 | ✅ Running |
| Flask HMI | 6001 | ✅ Running (via .venv) |
| Nginx (React) | 8090 | ✅ Running |
| PostgreSQL | 5432 | ✅ Windows Service |
| Mosquitto MQTT | 1883 | ✅ Windows Service |

**HMI access:** `http://localhost:8090`

---

## Files Changed This Session

| File | Change |
|------|--------|
| `HMI/services/rbac_service.py` | Fixed `can_user_clear_alarm()` + `requires_approval_to_clear_alarm()` |
| `HMI/controllers/alarm_controller.py` | Fixed `get_alarm_stats()` — db pool + RealDictCursor guard |
| `HMI/apex-hmi/src/components/hmi/AlarmPanel.tsx` | Added auth headers to snapshot fetch |
| `HMI/apex-hmi/dist/assets/index-p0372xoK.js` | Rebuilt React bundle |
