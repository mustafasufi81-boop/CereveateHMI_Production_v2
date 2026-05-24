# Connection Loss — Root Cause Audit & Fix Plan
**Date:** 23 May 2026  
**Status:** PENDING REVIEW — No code changed yet

---

## Architecture Overview (Current)

```
Browser (port 8090 — Vite dev server)
  │
  ├── REST API calls
  │     └── /api/*  →  Vite proxy  →  Flask :6001
  │
  ├── Socket.IO (real-time data)
  │     └── DIRECT to Flask :6001  (bypasses Vite proxy)
  │          URL built as: window.location.origin.replace(':8090', ':6001')
  │
  └── Health ping (every 30s)
        └── fetch('/api/health')  →  Vite proxy  →  Flask :6001
             ↑ This is the fragile path — explained below
```

Flask (`app.py`) runs with:
- `SocketIO(app, async_mode='threading')` — no ping settings configured → uses Socket.IO defaults
- `/api/health` endpoint that does a live `SELECT 1` on a bare psycopg2 connection
- `socketio.run(app, use_reloader=False)`

---

## Problem 1 — Health endpoint DB probe crashes on idle connection 🔴 CRITICAL

**Files:** `WEB_HMI_MFA/HMI/app.py` lines 174–185

**Code:**
```python
@app.route('/api/health', methods=['GET'])
def api_health():
    try:
        db_ok = False
        try:
            from container import container as _c
            with _c.historical_service.connection.cursor() as cur:
                cur.execute("SELECT 1")        # ← THE PROBLEM
            db_ok = True
        except Exception:
            db_ok = False
        return jsonify({'status': 'ok', ...}), 200
    except Exception as _e:
        return jsonify({'status': 'error', ...}), 500   # ← returns 500
```

**Why it fails:**  
`historical_service.connection` is a **bare psycopg2 connection** (not a pool).  
PostgreSQL drops idle connections after the server-side `tcp_keepalives_idle` timeout (default ~10 min on Windows, or when PostgreSQL is restarted/vacuumed).  
When this happens, the `SELECT 1` raises `psycopg2.OperationalError: server closed the connection unexpectedly`.  
The outer `except` catches it and returns **HTTP 500**.  
The React health check sees 500 → sets `flaskReachable = false` → banner shows **"CONNECTION LOST — Flask backend (port 6001) is not reachable"**.

**The lie:** Flask is 100% up and serving all other requests. The banner is completely wrong.  
**Trigger:** Happens reliably after ~10 min of no DB queries, or after any PostgreSQL restart.

**Proposed Fix:**
```python
@app.route('/api/health', methods=['GET'])
def api_health():
    """Lightweight liveness check — only confirms Flask process is alive."""
    db_ok = False
    try:
        conn = _c.historical_service.connection
        # Check connection status without a query — psycopg2 STATUS_READY = 1
        db_ok = (conn is not None and conn.closed == 0)
    except Exception:
        db_ok = False
    return jsonify({
        'status': 'ok',
        'uptime_s': round(_time.time() - _flask_start_time),
        'db': db_ok,
    }), 200   # ALWAYS 200 — Flask being alive IS the health check
```

**Key change:** Remove `SELECT 1`. Use `conn.closed == 0` (property check, no network round-trip).
**Always return 200.** If Flask is running enough to respond, it IS healthy.
The `db` field still reports DB status as informational — without it causing a false alarm.

---

## Problem 2 — One failed health ping = instant "CONNECTION LOST" banner 🔴 CRITICAL

**File:** `WEB_HMI_MFA/HMI/apex-hmi/src/services/mqtt-websocket.ts` lines 81–95

**Code:**
```typescript
private startFlaskHealthCheck() {
    const check = async () => {
        try {
            const r = await fetch('/api/health', { signal: AbortSignal.timeout(4_000) });
            this.updateHealth({ flaskReachable: r.ok, ... });
        } catch {
            this.updateHealth({ flaskReachable: false, ... });   // ← immediate false on ANY error
        }
    };
    check();
    this._flaskTimer = setInterval(check, 30_000);
}
```

**Why it fails:**  
A single network glitch, Vite proxy hiccup, or the DB probe problem (above) causes one failed fetch.  
`flaskReachable = false` is set **immediately** with no tolerance.  
Banner appears for up to 30 seconds until the next poll succeeds.  
This is a 0-tolerance system: **1 failure out of 1 attempt = alarm**.

**Proposed Fix:**
```typescript
private _flaskFailCount = 0;
private readonly FLASK_FAIL_THRESHOLD = 2; // require 2 consecutive failures

private startFlaskHealthCheck() {
    const check = async () => {
        try {
            const r = await fetch('http://localhost:6001/api/health', {
                signal: AbortSignal.timeout(5_000)
            });
            if (r.ok) {
                this._flaskFailCount = 0;  // reset on success
                this.updateHealth({ flaskReachable: true, flaskLastCheckedAt: Date.now() });
            } else {
                this._flaskFailCount++;
            }
        } catch {
            this._flaskFailCount++;
        }
        // Only mark down after 2 consecutive failures
        if (this._flaskFailCount >= this.FLASK_FAIL_THRESHOLD) {
            this.updateHealth({ flaskReachable: false, flaskLastCheckedAt: Date.now() });
        }
    };
    check();
    this._flaskTimer = setInterval(check, 30_000);
}
```

**Key changes:**
1. Require **2 consecutive failures** before marking Flask as unreachable
2. Health check goes **direct to `:6001`** instead of through Vite proxy (see Problem 5)

---

## Problem 3 — Browser background tab throttling disconnects Socket.IO 🔴 CRITICAL

**File:** `WEB_HMI_MFA/HMI/app.py` lines 243–248

**Code:**
```python
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',
    logger=True,
    engineio_logger=False
    # ← NO ping_interval or ping_timeout configured
)
```

**Why it fails:**  
Socket.IO defaults: `ping_interval=25s`, `ping_timeout=60s`.  
Chrome/Firefox **throttle all JavaScript timers to fire no more than once per minute** when a tab is in the background (Page Visibility API + timer throttling).  
The Socket.IO client sends a heartbeat every 25s. When the tab goes to background, this heartbeat is delayed to >60s.  
The server sees no ping response for 60s → **server-side timeout fires** → server closes the socket → client gets `disconnect` event → banner shows "CONNECTION LOST".  
**This happens every single time an operator switches tabs for more than ~1 minute.**

**Proposed Fix:**

Server (`app.py`):
```python
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',
    logger=True,
    engineio_logger=False,
    ping_interval=60,    # server sends ping every 60s
    ping_timeout=180,    # allow 3 min for response (survives background throttle)
)
```

Client (`mqtt-websocket.ts`):
```typescript
this.socket = io(SOCKET_URL, {
    transports: ['websocket', 'polling'],
    reconnection: true,
    reconnectionDelay: 1_000,
    reconnectionDelayMax: 10_000,
    reconnectionAttempts: Infinity,
    timeout: 180_000,    // match server ping_timeout
    auth: { token },
});
```

**Key change:** Server waits 3 minutes for a ping response instead of 1 minute.
A tab in the background for up to ~2.5 min will **not** trigger a disconnect.
The connection auto-recovers instantly when the user returns to the tab anyway (Socket.IO auto-reconnect already works) — but increasing this eliminates the false disconnect entirely.

---

## Problem 4 — Stale data warning fires on a stable/quiet plant 🟡 MEDIUM

**File:** `WEB_HMI_MFA/HMI/apex-hmi/src/services/mqtt-websocket.ts` line 8

**Code:**
```typescript
const STALE_DATA_THRESHOLD_MS = 15_000;  // 15 seconds
```

**Why it fails:**  
If all monitored tags hold their value for >15 seconds (e.g., stable pressure, quiet shift, weekend), no Socket.IO data events fire (the OPC server only pushes changes).  
After 15s of silence, `dataIsStale = true` → banner: "No MQTT data received for >15 s — check OPC/MQTT pipeline".  
The pipeline is working perfectly. The plant is just not changing.

**Proposed Fix:**
```typescript
const STALE_DATA_THRESHOLD_MS = 60_000;  // 60 seconds — quiet plant won't false-alarm
```

60 seconds is a reasonable threshold. If there is truly a pipeline failure, 60s without any update from any tag is a valid concern.

---

## Problem 5 — Health check routed through Vite proxy instead of direct 🟡 MEDIUM

**File:** `WEB_HMI_MFA/HMI/apex-hmi/src/services/mqtt-websocket.ts` line 84

**Code:**
```typescript
const r = await fetch('/api/health', { ... });  // goes through Vite proxy on :8090
```

**Why it fails:**  
The Socket.IO connection is already going **direct to `:6001`** (correct, reliable).  
But the health check goes through Vite's HTTP proxy on `:8090`.  
Under any Vite HMR activity, hot reload, or proxy pool exhaustion, this adds latency and failure risk.  
A Vite proxy timeout = `flaskReachable = false` — even though Flask is fine.  
**The health check is measuring Vite proxy health, not Flask health.**

**Proposed Fix:**  
Use the same base URL as Socket.IO:
```typescript
// Use same origin as the socket connection — direct to Flask
const FLASK_BASE = import.meta.env.VITE_WS_URL?.replace(/^ws/, 'http') 
    || `http://localhost:6001`;

const r = await fetch(`${FLASK_BASE}/api/health`, { ... });
```

This is already addressed in the Fix for Problem 2 above (`fetch('http://localhost:6001/api/health', ...)`).

---

## Problem 6 — No CORS header on direct health check calls 🟡 MEDIUM (risk after fix 5)

**File:** `WEB_HMI_MFA/HMI/app.py` — health endpoint

**Why it matters:**  
Once the health check goes direct to `:6001` (fix for Problem 5), the browser enforces CORS.  
Flask already has `CORS(app)` which sets `Access-Control-Allow-Origin: *` on all routes.  
The `/api/health` route is registered on the Flask `app` object so it inherits CORS — **this should already work**.  
No code change needed, but worth verifying with browser DevTools (Network tab, check response headers on `/api/health`).

---

## Summary & Priority

| # | Problem | Root File | Severity | Fix Effort |
|---|---------|-----------|----------|------------|
| 1 | DB probe makes health return 500 | `app.py` `/api/health` | 🔴 Critical | 5 lines |
| 2 | 0-tolerance: 1 ping fail = instant alarm | `mqtt-websocket.ts` | 🔴 Critical | 15 lines |
| 3 | Background tab disconnects socket | `app.py` + `mqtt-websocket.ts` | 🔴 Critical | 4 lines |
| 4 | 15s stale threshold too aggressive | `mqtt-websocket.ts` | 🟡 Medium | 1 line |
| 5 | Health check via Vite proxy | `mqtt-websocket.ts` | 🟡 Medium | 1 line |
| 6 | CORS on direct health call | `app.py` (already ok) | 🟢 Low/None | 0 lines |

---

## Files That Will Be Changed

| File | What Changes |
|------|-------------|
| `WEB_HMI_MFA/HMI/app.py` | Fix `/api/health` (remove SELECT 1, always 200) + add `ping_interval=60, ping_timeout=180` to SocketIO init |
| `WEB_HMI_MFA/HMI/apex-hmi/src/services/mqtt-websocket.ts` | Add fail-count threshold, direct URL, raise stale threshold, raise socket timeout |

**Total lines changed: ~25 lines across 2 files.**  
No database changes. No architectural changes. No service restarts needed for the TypeScript changes (Vite HMR will apply them live). Flask will need a restart for the Python changes.

---

## What Will NOT Change

- Socket.IO auto-reconnect logic (already configured with `reconnectionAttempts: Infinity` — this is correct)
- The `ConnectionHealthBanner` component (no changes needed — it reacts correctly once health data is accurate)
- Vite proxy config (still needed for REST API calls from browser)
- Any backend services or DB schema

---

*Awaiting approval to apply all fixes.*

---

## ✅ CHANGE LOG — What Was Removed & What Was Added
*(24 May 2026 — Running record. Update here whenever features are removed so they can be restored.)*

### File: `src/App.tsx`
| Action | What | Reason |
|--------|------|--------|
| ❌ REMOVED | `import Analytics from "./pages/Analytics"` | Route removed — page still exists on disk |
| ❌ REMOVED | `import BIAnalytics from "./pages/BIAnalytics"` | Route removed — page still exists on disk |
| ❌ REMOVED | `<Route path="/analytics" element={<Analytics />} />` | Direct URL access blocked for all roles |
| ❌ REMOVED | `<Route path="/bi-analytics" element={<BIAnalytics />} />` | Direct URL access blocked for all roles |
| ✅ TO RESTORE | Re-add both imports + routes in App.tsx | If direct-URL access needed again |

### File: `src/components/hmi/IndustrialHMIPrototype.tsx`
| Action | What | Reason |
|--------|------|--------|
| ❌ REMOVED | `import { useEquipmentPermission }` | Hook called but ALL 4 return values were unused → caused 404 on every equipment click |
| ❌ REMOVED | `const { permissionLevel, capabilities, hasPermission, loading: isLoadingPermission } = useEquipmentPermission(selectedEquipment)` | See above — 4 vars never referenced in JSX |
| 🔧 FIXED | `useEffect` deps removed `selection.selectedTags` | Was causing infinite setState loop ("Maximum update depth exceeded") |
| ✅ ADDED | `import { HmiAnalyticsTab }` | For ⚠ ANALYTICS tab content |
| ✅ ADDED | `import PredictiveAlarmPanel` (default export) | For 🔮 PREDICTIVE tab content |
| ✅ ADDED | `import { usePermission }` | RBAC guard for tab visibility |
| ✅ ADDED | `centerTab` state `('trends' \| 'analytics' \| 'predictive')` | Drives tab switching |
| ✅ ADDED | `const canViewAnalytics = usePermission('analytics', 'canView')` | Reads directly from DB via Flask — single source of truth |
| ✅ ADDED | `⚠ ANALYTICS` tab button + `HmiAnalyticsTab` panel | Visible to Admin + Operator + Engineer; hidden from Viewer |
| ✅ ADDED | `🔮 PREDICTIVE` tab button + `PredictiveAlarmPanel` panel | Visible to Admin + Operator + Engineer; hidden from Viewer |
| 🔄 SWAPPED | `PredictiveAlertsPanel` → `PredictiveAlarmPanel` in PREDICTIVE tab | `PredictiveAlertsPanel` was compact PEWS list (wrong); `PredictiveAlarmPanel` is the real engine with minutes-to-alarm / EWM logic |
| 🔧 FIXED | Import changed from `{ PredictiveAlertsPanel }` (named) to `import PredictiveAlarmPanel` (default export) | Wrong import type caused compile error → page blank |

### File: `WEB_HMI_MFA/HMI/services/rbac_service.py`
| Action | What | Reason |
|--------|------|--------|
| 🔧 FIXED | `get_user_module_permissions()` fallback now fetches `role_name` | Was only fetching `is_admin` → could not distinguish Viewer from Operator in fallback |
| 🔧 FIXED | Fallback now gives Viewer `analytics: none_p` (canView=False) | Old fallback gave everyone `canView=True` including Viewer |
| ✅ ADDED | `seed_default_module_permissions()` method | Seeds all roles × modules at startup — enforces correct values |
| 🔧 FIXED | Seed changed from `ON CONFLICT DO NOTHING` → `ON CONFLICT DO UPDATE` | `DO NOTHING` silently left existing wrong rows (was root cause of Viewer seeing tabs) |

### File: `WEB_HMI_MFA/HMI/app.py`
| Action | What | Reason |
|--------|------|--------|
| ✅ ADDED | `container.rbac_service.seed_default_module_permissions()` call in `initialize_services()` | Ensures DB always has correct permissions on every Flask startup |

### DB: `historian_meta.role_module_permissions` — Final State (analytics module)
| Role | can_view | can_operate | can_generate | can_configure |
|------|----------|-------------|--------------|---------------|
| Admin | ✅ True | ✅ True | ✅ True | ✅ True |
| Engineer | ✅ True | ✅ True | ✅ True | ❌ False |
| Operator | ✅ True | ❌ False | ❌ False | ❌ False |
| **Viewer** | **❌ False** | ❌ False | ❌ False | ❌ False |

**Root cause (resolved 24 May 2026):** The DB had `Viewer | analytics | can_view = TRUE` pre-existing from an old admin UI action. The seed used `ON CONFLICT DO NOTHING` so it never corrected it. Fixed by direct UPDATE + changed seed to `DO UPDATE`.

### File: `src/components/hmi/AlarmHistoryModal.tsx`
| Action | What | Reason |
|--------|------|--------|
| ✅ ADDED | `import { usePermission }` | RBAC guard for CSV button |
| ✅ ADDED | `const canExport = usePermission('reports', 'canGenerate')` | Only Admin/Operator/Engineer see CSV button |
| ✅ RESTORED | `⬇ CSV` download button (was removed for all users) | Now role-gated: Viewer cannot see it |

### Components Still On Disk (NOT Deleted — Can Be Re-enabled)
| File | Status | How to Re-enable |
|------|--------|-----------------|
| `src/pages/Analytics.tsx` | ✅ Exists | Add route back in App.tsx |
| `src/pages/BIAnalytics.tsx` | ✅ Exists | Add route back in App.tsx |
| `src/components/hmi/HmiAnalyticsTab.tsx` | ✅ Exists + in use | Already wired to ANALYTICS tab |
| `src/components/hmi/PredictiveAlertsPanel.tsx` | ✅ Exists (NOT in use) | Was in PREDICTIVE tab — replaced by PredictiveAlarmPanel. Re-enable by swapping import back in IndustrialHMIPrototype |
| `src/components/hmi/PredictiveAlarmPanel.tsx` | ✅ Exists + **IN USE** | Wired to PREDICTIVE tab — default export, no props, uses useAuth internally |
| `src/components/hmi/PredictiveTrendModal.tsx` | ✅ Exists + in use | Opens as modal on row click |
| `src/services/equipment-permission-service.ts` | ✅ Exists | Re-add import + hook call in IndustrialHMIPrototype if equipment RBAC needed |
| `src/hooks/useEquipmentPermission.ts` | ✅ Exists | Same as above |
