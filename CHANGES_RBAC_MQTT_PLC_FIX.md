# RBAC, MQTT & PLC Tag Fetching — Changes & Architecture

**Date**: 25 May 2026  
**Author**: AI-assisted development session  
**Files Changed**:
- `HMI/app.py`
- `HMI/controllers/system_controller.py`
- `HMI/apex-hmi/src/components/hmi/IndustrialHMIPrototype.tsx`
- `HMI/apex-hmi/src/components/hmi/AlarmPanel.tsx`
- `CSharpBackend/Services/StartupTagSeedService.cs`
- `CSharpBackend/Program.cs`

---

## 1. Problem Summary

| # | Symptom | Root Cause |
|---|---------|------------|
| 1 | Viewer user still saw Alarm panel after access removed | `AlarmPanel` rendered unconditionally — no `canView` guard |
| 2 | PLC tag values showed `---` on first load | PLC tags only came via MQTT; if MQTT not ready at login → no values |
| 3 | After revoking then restoring HMI access, data never came back | REST polling `useEffect` had empty `[]` deps — never restarted |
| 4 | PLC tags missing for restricted users even when MQTT was connected | `(None, None)` plant/area not in user's allowed set → silently dropped |
| 5 | Permission changes had no effect on active MQTT sessions | `allowed` captured once at Socket.IO connect time, never refreshed |
| 6 | `logging-config.json` had null `ServerProgId` on fresh install | No auto-seed from DB; manual edit required |

---

## 2. Fix 1 — Alarm Panel RBAC Guard

### Files: `IndustrialHMIPrototype.tsx`, `AlarmPanel.tsx`

### What Changed
Added `canViewAlarms = usePermission('alarms', 'canView')` in both files.

In `IndustrialHMIPrototype.tsx`:
```tsx
const canViewAlarms = usePermission('alarms', 'canView');

// In JSX — wrap AlarmPanel:
{canViewAlarms ? <AlarmPanel /> : (
  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center',
    height: '100%', color: '#6b7280', fontSize: '13px' }}>No alarm access</div>
)}
```

In `AlarmPanel.tsx` — stops REST polling when access removed:
```tsx
const canViewAlarms = usePermission('alarms', 'canView');

const fetchSnapshot = async (forceHardReload = false) => {
  if (!canViewAlarms) return; // user lost alarm view access
  ...
```

### How Permission System Works
- `usePermission(module, action)` reads from `user.permissions` (loaded at login via JWT)
- Admin users always return `true` (short-circuit in hook)
- DB table: `automation_db` → `role_module_permissions` (module=`alarms`, action=`can_view`)
- Admin UI: `PermissionsTab.tsx` → saves to DB → next login picks up change

### Effect
- Viewer with `alarms.canView = false` → sees "No alarm access" grey box
- AlarmPanel stops polling `/api/alarms/active` when access removed
- Admin always sees full alarm panel regardless of config

---

## 3. Fix 2 — PLC Tags Dropped for Restricted Users (MQTT broadcast filter)

### File: `HMI/app.py`

### Root Cause
In `on_mqtt_message()`, the per-SID broadcast filtered tags using:
```python
tag_meta_mqtt.get(t.get('tag_id'), (None, None)) in allowed
```
PLC tags come from the C# PLC gateway with **no `plant` or `area` fields** — so `tag_meta.get(tag_id)` returns `(None, None)`.  
`(None, None)` was never in the user's `allowed` set → **PLC tags silently dropped for all non-admin users.**

### Fix Applied
```python
user_tags = [
    t for t in filtered_tags
    if (
        # Tags with no plant/area (e.g. PLC tags) visible to all authenticated users
        tag_meta_mqtt.get(t.get('tag_id'), (None, None)) == (None, None)
        or tag_meta_mqtt.get(t.get('tag_id'), (None, None)) in allowed
    )
]
```
Same fix applied in `on_signalr_tag_update()` for OPC/SignalR tags.

### Rule Going Forward
> Tags with **no plant/area assignment** in `tag_cache` are treated as **globally visible** to all authenticated users. Only tags with explicit plant/area assignments are subject to area-based RBAC filtering.

---

## 4. Fix 3 — Stale Permissions in Active Socket.IO Sessions

### File: `HMI/app.py`

### Root Cause
At Socket.IO connect time, user permissions were fetched once:
```python
# OLD — captured once, never updated
allowed = _get_user_allowed_areas(user_id, is_admin) if user_id else set()
_sid_sessions[sid] = {'user_id': user_id, 'is_admin': is_admin, 'allowed': allowed}
```
If admin changed user permissions while the user was connected, the active session kept old permissions for its entire lifetime.

### Fix Applied
In both broadcast loops, permissions are now re-fetched **on every MQTT batch**:
```python
for sid, session in list(_sid_sessions.items()):
    user_id  = session.get('user_id')
    is_admin = session.get('is_admin', False)
    # Re-fetch live — admin changes take effect on next MQTT message (≤1s delay)
    allowed = _get_user_allowed_areas(user_id, is_admin) if user_id else set()
    session['allowed'] = allowed  # keep session fresh for reconnect snapshots
```

### Performance Note
`_get_user_allowed_areas()` calls `area_access_service.get_user_area_access(user_id)` which hits the DB.  
With typical MQTT frequency (1s) and few connected users (<20), this is acceptable.  
If performance becomes an issue in future, add a 5s TTL cache per `user_id`.

---

## 5. Fix 4 — PLC REST Fallback Polling

### File: `HMI/controllers/system_controller.py`

### What Changed
Added a new Flask endpoint `/api/plc/values` that proxies `http://127.0.0.1:5001/api/plc/values` (C# PLC gateway):

```python
@system_bp.route('/plc/values')
@token_required
def proxy_plc_values(current_user):
    req = urllib.request.Request('http://127.0.0.1:5001/api/plc/values')
    with urllib.request.urlopen(req, timeout=3) as response:
        data = json_lib.loads(response.read().decode('utf-8'))
    # Normalise to dict + apply RBAC filter
    ...
    return jsonify({'tags': tags_dict, 'count': len(tags_dict), 'source': 'plc'}), 200
```

### Why Needed
- PLC data originates from C# PLC gateway (`/api/plc/values` on port 5001)
- Previously only flowed via MQTT broker → Socket.IO → browser
- If MQTT not connected at login, user saw `---` for all PLC tags until MQTT sent a new message
- REST fallback polls every 1s independently of MQTT, ensuring values are always present

### Data Flow (Before Fix)
```
C# PLC Gateway → MQTT Broker → Flask MQTT subscriber → Socket.IO → Browser
                                (if not ready at login = blank values)
```

### Data Flow (After Fix)
```
Primary:   C# PLC Gateway → MQTT Broker → Flask MQTT subscriber → Socket.IO → Browser
Fallback:  C# PLC Gateway → Flask /api/plc/values → Browser (REST poll every 1s)
```

---

## 6. Fix 5 — Auto-Seed `logging-config.json` from Database

### Files: `CSharpBackend/Services/StartupTagSeedService.cs`, `CSharpBackend/Program.cs`

### Problem
On fresh install or after bin folder wipe, `logging-config.json` had:
```json
{ "ServerProgId": null, "MonitoredTags": [] }
```
OPC never connected automatically — operator had to manually edit the JSON.

### Solution
`StartupTagSeedService` runs once at startup (before `OpcAutoConnectService`):
1. Checks if `ServerProgId` is blank OR `MonitoredTags` is empty
2. If so, queries `historian_meta.tag_master` for OPC tags:
   ```sql
   SELECT DISTINCT server_progid
   FROM historian_meta.tag_master
   WHERE enabled = true
     AND server_progid IS NOT NULL
     AND (plc_ip_address IS NULL OR plc_ip_address = '')
   ```
3. Calls `_configService.SetServerConnection(progId, "localhost")`
4. Adds all matching tags via `AddMonitoredTag(tag_id)`
5. Idempotent — skips if config already populated
6. Never crashes startup (full try/catch)

### Registration Order in `Program.cs`
```csharp
// MUST be before OpcAutoConnectService
builder.Services.AddHostedService<StartupTagSeedService>();
builder.Services.AddHostedService<OpcAutoConnectService>();
```

### Important SQL Note
`tag_master` has **no `source_type` column**. OPC tags are identified by:
- `server_progid IS NOT NULL` — has an OPC server ProgID
- `plc_ip_address IS NULL OR plc_ip_address = ''` — not a PLC tag

---

## 7. Architecture Reference

### Full Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    C# OPC/PLC Backend (port 5001)           │
│  OpcDaService ──► /api/opc/values  (REST snapshot)         │
│  PlcConnectionManager ──► /api/plc/values  (REST snapshot) │
│  PlcConnectionManager ──► MQTT Broker :1883                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
          ┌────────────┴───────────────┐
          │  Flask HMI Backend (6001)  │
          │                            │
          │  MQTT subscriber           │
          │  on_mqtt_message()         │
          │   ├─ re-fetch permissions  │
          │   ├─ filter by plant/area  │  ← FIXED: (None,None) passes through
          │   └─ emit mqtt_tag_update  │
          │       via Socket.IO        │
          │                            │
          │  REST proxies:             │
          │  /api/opc/values ──────────┼──► C# :5001/api/opc/values
          │  /api/plc/values ──────────┼──► C# :5001/api/plc/values  ← NEW
          │  /api/alarms/active        │
          └────────────┬───────────────┘
                       │
          ┌────────────┴───────────────┐
          │  React/Vite HMI (8090)     │
          │                            │
          │  Socket.IO (primary)       │
          │   mqtt_tag_update event    │
          │   tag_update event         │
          │                            │
          │  REST fallback (1s poll):  │
          │   /api/opc/values          │
          │   /api/plc/values  ← NEW   │
          │                            │
          │  Permission checks:        │
          │  alarms.canView  ← NEW     │
          │  alarms.canOperate         │
          │  analytics.canView         │
          │  hmi.canView               │
          └────────────────────────────┘
```

### RBAC Enforcement Layers

| Layer | Where | What it controls |
|-------|-------|-----------------|
| Frontend component guard | `IndustrialHMIPrototype.tsx` | Hide AlarmPanel if `alarms.canView=false` |
| Frontend poll guard | `AlarmPanel.tsx fetchSnapshot()` | Stop API polling if `alarms.canView=false` |
| Backend area filter | `app.py on_mqtt_message()` | Filter MQTT tags by plant/area per user |
| Backend REST filter | `system_controller.py` | Filter OPC/PLC REST values by plant/area |
| Backend permission refresh | `app.py` both broadcast loops | Re-fetch permissions on every message |

### Permission DB Tables
```sql
-- Module permissions (view/operate/generate/configure per module)
role_module_permissions (role_id, module, can_view, can_operate, can_generate, can_configure)

-- Area access (which plant/area each user can see)
user_area_access (user_id, plant, area)

-- Tag master (source of OPC tags for auto-seed)
historian_meta.tag_master (tag_id, server_progid, plc_ip_address, enabled, ...)
```

---

## 8. Testing Checklist

- [ ] Admin user: sees all tags (OPC + PLC), full alarm panel
- [ ] Viewer with `alarms.canView=false`: sees "No alarm access", no alarm API calls
- [ ] Viewer with `alarms.canView=true`: sees alarms
- [ ] Restricted user (area access): sees only their area tags, PLC tags visible (no area filter)
- [ ] Remove HMI access then restore: data resumes within 1s (REST fallback)
- [ ] Fresh install (blank `logging-config.json`): OPC auto-connects from `tag_master` on startup
- [ ] MQTT disconnect: REST fallback shows last values within 1s
- [ ] Permission change while user connected: takes effect on next MQTT message (≤1s)
