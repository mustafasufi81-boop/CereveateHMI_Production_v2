# Session Work Log — 25 May 2026
**Engineer:** GitHub Copilot AI  
**Project:** CereveateHMI Production — OPC/PLC Industrial HMI  
**Repo:** `shahbpcl/opc-da-web-historian` (branch: `main`)  
**Last Commit:** `95b6a39`

---

## Services Architecture (Quick Reference)
| # | Service | Port | Process |
|---|---------|------|---------|
| 1 | C# OPC/PLC Backend | 5001 | `OpcDaWebBrowser.exe` |
| 2 | Flask HMI Backend | 6001 | `python app.py` |
| 3 | React Vite HMI Frontend | 8090 | `npm run dev` (node) |

---

## Issue 1 — Vite Internal Server Error (Syntax Error in IndustrialHMIPrototype.tsx)

### Symptom
Browser console showed:
```
[vite] Internal Server Error
× Expected unicode escape
const headers = { 'Authorization': \Bearer \ };
Syntax Error
```
Line 851 of `IndustrialHMIPrototype.tsx`

### Investigation
- Checked file at `D:\CereveateHMI_Production\HMI\apex-hmi\src\components\hmi\IndustrialHMIPrototype.tsx`
- Line 859 already had **correct** backtick syntax: `` `Bearer ${token}` ``
- No TypeScript errors found by Pylance
- `get_errors` confirmed file was syntactically valid

### Root Cause
Vite dev server had **cached a stale broken transform** of the file from before the fix. The file itself was already correct but Vite's in-memory module cache still held the broken version.

### Fix Applied
Killed old Vite process (PID 32048) and restarted:
```powershell
Stop-Process -Id 32048 -Force
Start-Process "cmd.exe" -ArgumentList "/c npm run dev" -WorkingDirectory "D:\CereveateHMI_Production\HMI\apex-hmi" -WindowStyle Minimized
```

### Result ✅
Vite restarted clean on PID 28752, error cleared.

---

## Issue 2 — OPC and PLC Values Not Showing in HMI

### Symptom
HMI loaded but OPC tag values and PLC tag values were blank/not updating.

### Investigation
1. Confirmed all 3 services running on their ports (5001, 6001, 8090)
2. Tested C# backend APIs directly:
   - `GET http://localhost:5001/api/opc/values` → ✅ returned 27 tags, all `GOOD` quality
   - `GET http://localhost:5001/api/plc/values` → ✅ returned 60+ PLC tags, all `Good` quality
3. Checked `vite.config.ts` — found the problem:

### Root Cause
```ts
// WRONG — ALL /api/* routes proxied to Flask (6001)
proxy: {
  "/api": { target: "http://localhost:6001" }
}
```
`/api/opc/values` and `/api/plc/values` live on the **C# backend (5001)**, not Flask (6001). They were hitting Flask which returned errors.

### Fix Applied — `vite.config.ts`
Added specific proxy rules **before** the generic `/api` rule (order matters in Vite proxy):
```ts
proxy: {
  "/api/opc": { target: "http://localhost:5001", changeOrigin: true, secure: false },
  "/api/plc": { target: "http://localhost:5001", changeOrigin: true, secure: false },
  "/opcHub":  { target: "http://localhost:5001", changeOrigin: true, secure: false, ws: true },
  "/api":     { target: "http://localhost:6001", changeOrigin: true, secure: false },
  "/socket.io": { target: "http://localhost:6001", changeOrigin: true, secure: false, ws: true },
}
```

### Result ✅
OPC and PLC values now correctly routed to C# backend port 5001.

---

## Issue 3 — Edge Browser Showing Old Broken Page (Chrome Worked Fine)

### Symptom
After Vite restart, Chrome showed correct page, Edge showed old broken version.

### Root Cause
Edge had aggressively cached the old broken JS bundle.

### Fix Applied — `vite.config.ts`
Added `no-store` HTTP response headers to Vite dev server so **no browser ever caches** the dev bundle:
```ts
server: {
  headers: {
    "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
  },
  ...
}
```

### Result ✅
All browsers now always get fresh JS on every load. No manual cache clearing needed.

---

## Issue 4 — Garbled/Broken Characters in Navigation Tab Labels

### Symptom
Nav tabs showed: `ÐŸ"% TRENDS`, `ðŸ ANALYTICS`, `ÐŸ"® PREDICTIVE`, `ÐŸ"‹ REPORTS ↗`  
(emoji rendered as multi-byte garbage characters)

### Root Cause
Emoji characters (`📈`, `📊`, `🔮`, `📋`) were pasted into the `.tsx` file using Windows clipboard which caused UTF-8 encoding corruption. The file bytes showed mojibake sequences like `C3 B0 C5 B8 E2 80 9C` instead of proper 4-byte emoji codepoints.

### Files Affected
`D:\CereveateHMI_Production\HMI\apex-hmi\src\components\hmi\IndustrialHMIPrototype.tsx`  
Lines: 1572, 1596, 1626, 1659

### Fix Applied
Replaced corrupted emoji spans with clean plain text labels using direct `[System.IO.File]::WriteAllLines()` with explicit UTF-8 encoding:

| Before | After |
|--------|-------|
| `<span>ðŸ"‰</span> TRENDS` | `TRENDS` |
| `<span>âš </span> ANALYTICS` | `ANALYTICS` |
| `<span>ðŸ"®</span> PREDICTIVE` | `PREDICTIVE` |
| `<span>ðŸ"‹</span> REPORTS â†—` | `REPORTS ↗` |

> **NOTE for future:** If you want emoji back, use JSX Unicode escapes — NOT copy-paste:
> ```tsx
> {'\u{1F4C8}'} TRENDS      // 📈
> {'\u{1F4CA}'} ANALYTICS   // 📊
> {'\u{1F52E}'} PREDICTIVE  // 🔮
> {'\u{1F4CB}'} REPORTS     // 📋
> ```

### Result ✅
Tab labels now show clean text. Committed to GitHub.

---

## GitHub Push — Commit `95b6a39`

```
fix: remove broken emoji encoding in nav tabs; add no-cache headers and OPC/PLC proxy routes to vite config
```

Files committed:
- `src/components/hmi/IndustrialHMIPrototype.tsx`
- `vite.config.ts`

---

## ⚠️ CURRENT OPEN PROBLEM (Not Yet Fixed — Continue Next Session)

### Problem: `psycopg2.InterfaceError: connection already closed` in Alarm Controller

### Error Log
```
psycopg2.InterfaceError: connection already closed

File "D:\CereveateHMI_Production\HMI\controllers\alarm_controller.py", line 214, in get_active_alarms
    cursor = db_service.connection.cursor()
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
psycopg2.InterfaceError: connection already closed

GET /api/alarms/active HTTP/1.1  →  500
```

### Root Cause (Diagnosed, Not Yet Fixed)
`alarm_controller.py` uses the **OLD pattern**:
```python
db_service = container.historical_service
cursor = db_service.connection.cursor()   # ← BROKEN: raw persistent connection drops
```

The project already has a proper **connection pool** in `D:\CereveateHMI_Production\HMI\db_pool.py` with `get_conn()` context manager.  
This pool uses `psycopg2.pool.ThreadedConnectionPool` (min=2, max=15) and is the **correct** way to get connections.

### Fix Required
Replace all `db_service.connection.cursor()` calls in `alarm_controller.py` with `db_pool.get_conn()`:

```python
# ADD at top of alarm_controller.py
import db_pool
from psycopg2.extras import RealDictCursor

# REPLACE this pattern:
db_service = container.historical_service
if not db_service or not db_service.connection:
    return jsonify({'success': True, 'alarms': [], 'count': 0})
cursor = db_service.connection.cursor(cursor_factory=RealDictCursor)
cursor.execute(query)
rows = cursor.fetchall()

# WITH this pattern:
try:
    with db_pool.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
except RuntimeError as e:
    logger.warning(f"DB pool error: {e}")
    return jsonify({'success': True, 'alarms': [], 'count': 0, 'message': str(e)})
```

### Scope of Change
Need to audit ALL functions in `alarm_controller.py` that use `db_service.connection` and replace with `db_pool.get_conn()`. Functions likely affected:
- `get_active_alarms()` (confirmed broken at line 214)
- `get_suppressed_alarms()` 
- Any other function using `db_service.connection`

Also check other controllers in `D:\CereveateHMI_Production\HMI\controllers\` for the same pattern.

### How to Start Next Session
1. Open `D:\CereveateHMI_Production\HMI\controllers\alarm_controller.py`
2. Search for all occurrences of `db_service.connection` and `historical_service`
3. Replace each with `db_pool.get_conn()` pattern
4. Restart Flask (port 6001)
5. Test `GET http://localhost:6001/api/alarms/active` — should return 200

---

## Restart Commands (Quick Reference)

```powershell
# Kill & restart Vite (port 8090)
$p = (netstat -ano | Select-String ":8090.*LISTENING" | ForEach-Object { ($_ -split '\s+')[-1] } | Select-Object -First 1)
Stop-Process -Id ([int]$p.Trim()) -Force
Start-Sleep -Seconds 2
Start-Process "cmd.exe" -ArgumentList "/c npm run dev" -WorkingDirectory "D:\CereveateHMI_Production\HMI\apex-hmi" -WindowStyle Minimized

# Kill & restart Flask (port 6001)
$p2 = (netstat -ano | Select-String ":6001.*LISTENING" | ForEach-Object { ($_ -split '\s+')[-1] } | Select-Object -First 1)
Stop-Process -Id ([int]$p2.Trim()) -Force
Start-Sleep -Seconds 2
Start-Process python -ArgumentList "app.py" -WorkingDirectory "D:\CereveateHMI_Production\HMI" -WindowStyle Minimized
```

---

## File Locations (Key Files)
| File | Purpose |
|------|---------|
| `D:\CereveateHMI_Production\HMI\apex-hmi\vite.config.ts` | Vite proxy config — routes /api/opc and /api/plc to port 5001 |
| `D:\CereveateHMI_Production\HMI\apex-hmi\src\components\hmi\IndustrialHMIPrototype.tsx` | Main HMI component — nav tabs, OPC/PLC polling |
| `D:\CereveateHMI_Production\HMI\controllers\alarm_controller.py` | ⚠️ NEEDS FIX — uses stale connection pattern |
| `D:\CereveateHMI_Production\HMI\db_pool.py` | ✅ Correct DB pool — use `db_pool.get_conn()` |
| `D:\CereveateHMI_Production\HMI\app.py` | Flask entry point |
