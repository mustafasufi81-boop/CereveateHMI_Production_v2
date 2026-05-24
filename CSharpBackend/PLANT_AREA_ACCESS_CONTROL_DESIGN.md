# Plant/Area-Based Access Control — Full Design & Requirements

**Date**: May 24, 2026  
**Status**: Design / Pre-Implementation — Reviewed & Hardened  
**Scope**: `historian_meta` schema, Flask HMI backend, React HMI frontend, C# OPC backend APIs

> **Revision note (May 24 2026)**: Ten critical improvements incorporated after security/architecture review.  
> **Revision note (May 24 2026 — Architecture Audit)**: 15-point architectural audit performed. Critical gaps fixed: immutable tag PK (`tag_uid`), ALLOW/BLOCK service-layer enforcement, resolved-tag-set cache, historian composite indexes, centralized `AuthorizationService`, signed license payload, admin hierarchy scaffold, historian partition guidance. See §24–§26.

---

## 1. Core Concept (The Three-Tier Access Model)

Every user gets **three tiers of access control** assigned by the Admin:

| Tier | Answers | Granularity | Stored In |
|------|---------|-------------|----------|
| **Role** | *What can this user DO?* (view / operate / generate / configure) | Feature-level | `historian_meta.roles` + `role_module_permissions` |
| **Plant + Area Assignment** | *Which zones can this user see?* (one or more Plant+Area pairs, across multiple plants) | Zone-level | `historian_meta.user_area_assignments` |
| **Tag-Level Access** | *Which specific tags within an area can this user see?* (allow-list or block-list per tag) | Tag-level | `historian_meta.user_tag_access` |

These three tiers are **independent and cumulative** — all three must pass for data to be visible:

```
 Role PERMITS the module  →  Area PERMITS the zone  →  Tag-Level PERMITS the individual tag
    (Feature Gate)                 (Zone Gate)                   (Tag Gate)
```

**Multi-Plant, Multi-Area**: A single user can be assigned to areas across **different plants simultaneously**.  
There is no concept of a "primary plant" — a user's scope is the explicit set of (plant, area) pairs assigned to them.  
Adding Plant2/AreaB does NOT automatically grant anything from Plant2/AreaC — every pair is an explicit independent assignment.

Two users can share the same Role but see **completely different plants and areas**.  
Two users can share the same Plant+Area but have **completely different tag-level visibility**.

---

## 2. Concrete Examples

### Example A — Same Plant, Different Areas (KEY RULE)

```
Plant1 has two areas: Area1 and Area-2

User: Lokesh    Role: Operator    Assigned: [ Plant1/Area1 ]                ← Area1 ONLY
User: Uzair     Role: Operator    Assigned: [ Plant1/Area-2 ]               ← Area-2 ONLY
User: Jhon      Role: Engineer    Assigned: [ Plant1/Area1, Plant1/Area-2 ] ← BOTH areas

All three users belong to Plant1.
But Lokesh CANNOT see Area-2 tags — even though they are in the SAME plant.
Uzair CANNOT see Area1 tags — even though they are in the SAME plant.
Jhon sees BOTH areas because he has TWO explicit assignment rows.

→ Same plant does NOT mean same visibility. Area assignment is the gatekeeper.
→ Two assignment rows in user_area_assignments = two areas visible simultaneously.
```

### Example D — Multiple Plants, Multiple Areas (MULTI-PLANT SCOPE)

```
User: Jhon      Role: Engineer

Assigned areas (3 rows in user_area_assignments):
  Row 1 → Plant1    / Area1      (OPC tags — Matrikon server)
  Row 2 → Plant1    / Area-2     (PLC tags — PLC_GATEWAY_01)
  Row 3 → FTP-1     / POTLINE    (PLC tags — Rockwell PLC)

Jhon spans TWO different plants: Plant1 and FTP-1.
Jhon sees tags from ALL THREE areas in his HMI simultaneously (UNION of all assigned areas).

Jhon does NOT see:
  ✗ BlastFurnace / Equipment   (different plant, not assigned)
  ✗ Plant1 / Area3             (same plant but area not assigned)

→ Scope = explicit set of (plant, area) pairs — cross-plant is fully supported.
→ Each additional pair is a NEW explicit row, not inherited from plant membership.
```

### Example E — Tag-Level Restriction Within an Area

```
User: shayaan   Role: Viewer    Assigned: [ Plant1/Area1 ]

Plant1/Area1 has 119 tags. Admin restricts shayaan further at tag level:
  ALLOWED:   Temperature tags, Pressure tags        (30 tags)
  BLOCKED:   Flow tags, Vibration tags              (89 tags hidden)

shayaan sees Plant1/Area1 in their area list,
but the HMI only shows the 30 allowed tags — the other 89 are never returned by the API.

→ Tag-level restriction applies ON TOP of area assignment — both gates must pass.
→ If tag_access table has no rows for this user+area, all tags in the area are visible (default open).
```

### Example B — Same Role, Different Plants

```
User: Lokesh    Role: Operator    Areas: Plant1/Area1
User: sourav    Role: Operator    Areas: FTP-1/POTLINE

Both are Operators (identical role_module_permissions).
Lokesh sees:  Matrikon.OPC.Simulation.1 tags + PLC_GATEWAY_01 tags in Plant1/Area1
sourav sees:  Rockwel_PLC_001 tags in FTP-1/POTLINE

→ Same capabilities, completely different plant data.
```

### Example C — Same Area, Different Role Capabilities

```
User: Jhon      Role: Engineer    Areas: Plant1/Area1
User: shayaan   Role: Viewer      Areas: Plant1/Area1

Both see identical Plant1/Area1 tags.
Jhon CAN generate reports from that area.
shayaan CANNOT generate reports — role forbids it.

→ Same area scope, different actions allowed.
```

### Summary Rule

> **Plant assignment alone does NOT grant access to all areas within that plant.**  
> Each area inside a plant must be explicitly assigned.  
> A user sees ONLY the areas explicitly listed in their `user_area_assignments` rows.

---

## 3. What "Area" Controls (Scope of Visibility)

When a user is assigned to a Plant+Area, **every data-returning API** must filter by that scope:

| Module | What Gets Filtered |
|--------|--------------------|
| **HMI Live Tags** | Only tags where `tag_master.plant = user's plant AND tag_master.area = user's area` |
| **Historian Trends** | Only tag time-series for tags in user's plant/area |
| **Reports** | Only report data sourced from user's plant/area tags |
| **Alarms** | Only alarms raised by tags in user's plant/area |
| **Analytics** | Only trend/BI data for user's plant/area |
| **Admin Panel** | Only Admin role can access; sees ALL plants |

A user assigned to **multiple areas** sees the **union** of all their assigned areas.  
Admin role (`is_admin = true`) bypasses all area filters — sees everything.

---

## 4. Current Database State

### Existing (keep unchanged):
```
historian_meta.users              (id, username, password_hash, role_id, status, ...)
historian_meta.roles              (id, name, description, is_admin, ...)
historian_meta.role_module_permissions (role_id, module, can_view, can_operate, can_generate, can_configure)
```

### Existing roles:
| id | name | is_admin |
|----|------|---------|
| 1 | Admin | true |
| 2 | Operator | false |
| 3 | Viewer | false |
| 13 | Engineer | false |

### Existing plants/areas in tag_master:
| plant | area | server_progid | protocol | tag count |
|-------|------|---------------|----------|-----------|
| FTP-1 | POTLINE | Rockwel_PLC_001 | Rockwell | 128 |
| Plant1 | Area1 | Matrikon.OPC.Simulation.1 | OPC | 27 |
| Plant1 | Area1 | PLC_GATEWAY_01 | — | 30 |
| Plant1 | Area1 | PLC_SENSORS_01 | Modbus | 62 |
| Plant1 | Area-2 | PLC_GATEWAY_01 | — | 10 |

---

## 5. New Database Tables Required

### 5.1 `historian_meta.plants_areas` — Master Registry

> **CRITICAL IMPROVEMENT #1 — Immutable surrogate codes**  
> Do NOT use raw `plant`/`area` text as the only key. Admin may rename display names over time.  
> Introduce `plant_code` + `area_code` as immutable identifiers. `display_name` can change freely without breaking any foreign key or historical reference.

```sql
CREATE TABLE historian_meta.plants_areas (
    id           SERIAL PRIMARY KEY,
    plant_code   VARCHAR(50)  NOT NULL,   -- immutable, e.g. "PLANT1", "FTP1"
    area_code    VARCHAR(50)  NOT NULL,   -- immutable, e.g. "AREA1", "POTLINE"
    plant        VARCHAR(100) NOT NULL,   -- legacy/display — kept for tag_master JOIN
    area         VARCHAR(100) NOT NULL,   -- legacy/display — kept for tag_master JOIN
    display_name VARCHAR(200),            -- human label, safe to rename
    description  TEXT,
    is_active    BOOLEAN NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (plant_code, area_code),
    UNIQUE (plant, area)                  -- still needed for tag_master JOIN
);

-- Critical index for tag_master JOIN performance
CREATE INDEX idx_plants_areas_plant_area ON historian_meta.plants_areas(plant, area);
```

**Rule**: `plant_code` and `area_code` are set once at creation and **never changed**.  
`display_name` is what the UI shows and can be freely edited by admin.

### 5.2 `historian_meta.user_area_assignments` — The Mapping Table

> **Naming note**: `plants_areas.id` is the canonical primary key of that table.
> Throughout this document `plant_area_id` always refers to `plants_areas.id`.
> In queries always write `pa.id AS plant_area_id` — `pa.plant_area_id` is **not** a real column.

```sql
CREATE TABLE historian_meta.user_area_assignments (
    id             SERIAL PRIMARY KEY,
    user_id        INTEGER NOT NULL REFERENCES historian_meta.users(id) ON DELETE CASCADE,
    plant_area_id  INTEGER NOT NULL REFERENCES historian_meta.plants_areas(id) ON DELETE CASCADE,
    assigned_by    INTEGER REFERENCES historian_meta.users(id),
    assigned_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at     TIMESTAMPTZ,           -- NULL = still active
    notes          TEXT
    -- ⚠ No inline UNIQUE — revoked rows must be preserved for history.
    -- Uniqueness is enforced via partial index below (active rows only).
);
-- Only one ACTIVE assignment per user per area; revoked duplicates are allowed.
CREATE UNIQUE INDEX idx_user_area_active_unique
    ON historian_meta.user_area_assignments(user_id, plant_area_id)
    WHERE revoked_at IS NULL;
CREATE INDEX ON historian_meta.user_area_assignments(user_id);
```

### 5.3 `historian_meta.access_audit_log` — Audit Trail

> **CRITICAL IMPROVEMENT #9 — Audit logging**  
> Industrial systems require full audit trail of who granted/revoked access, when, from which IP.

```sql
CREATE TABLE historian_meta.access_audit_log (
    id              BIGSERIAL PRIMARY KEY,
    event_time      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    admin_user_id   INTEGER NOT NULL,
    admin_username  VARCHAR(100) NOT NULL,
    admin_ip        VARCHAR(45),
    target_user_id  INTEGER NOT NULL,
    target_username VARCHAR(100) NOT NULL,
    action          VARCHAR(20) NOT NULL,  -- 'ASSIGN' | 'REVOKE' | 'REPLACE' | 'ROLE_CHANGED' | ...
    old_state       JSONB,   -- e.g. {"areas":["Plant1/Area1"],"role":"Operator","quota":3}
    new_state       JSONB,   -- e.g. {"areas":["Plant1/Area1","FTP-1/POTLINE"],"role":"Engineer"}
    -- ⚠ old_areas TEXT / new_areas TEXT were removed — JSONB allows structured queries:
    --   SELECT * WHERE new_state @> '{"role":"Engineer"}'
    notes           TEXT
);
CREATE INDEX ON historian_meta.access_audit_log(target_user_id, event_time DESC);
CREATE INDEX idx_audit_old_state ON historian_meta.access_audit_log USING gin(old_state);
CREATE INDEX idx_audit_new_state ON historian_meta.access_audit_log USING gin(new_state);
```

### 5.4 Critical Index on `tag_master`

> **CRITICAL IMPROVEMENT #5 — tag_master must be indexed on (plant, area)**  
> Without this, every HMI poll, historian query, and report query will full-scan 500+ tags.

```sql
CREATE INDEX idx_tag_master_plant_area ON historian_meta.tag_master(plant, area);
```

### 5.5 Seed `plants_areas` from existing tag_master data

```sql
INSERT INTO historian_meta.plants_areas (plant_code, area_code, plant, area, display_name)
SELECT DISTINCT
    UPPER(REGEXP_REPLACE(plant, '[^A-Za-z0-9]', '', 'g')) AS plant_code,
    UPPER(REGEXP_REPLACE(area,  '[^A-Za-z0-9]', '', 'g')) AS area_code,
    plant,
    area,
    plant || ' — ' || area
FROM historian_meta.tag_master
WHERE plant IS NOT NULL AND area IS NOT NULL
ON CONFLICT (plant, area) DO NOTHING;
```

---

## 6. Admin UI — Two-Step Assignment Workflow

### Step 1: Assign Role to User
*Already implemented. Admin opens User Management → selects role from dropdown → saves.*

**Role defines: what modules user can access and what actions they can perform.**

### Step 2: Assign Areas to User
*New screen. Admin opens User Management → selects user → clicks "Area Access" tab → assigns one or more Plant+Area combinations.*

**Area defines: which plant's data the user will see everywhere in the system.**

---

## 7. Admin Settings UI — Screens Required

### 7.1 User Management (existing — extend with Area tab)
```
[User List]
  ┌─────────────────────────────────────────────┐
  │ User: Lokesh        Role: [Operator ▼]      │
  │ Status: Approved                            │
  │                                             │
  │ Tabs: [Profile] [Role] [Area Access] [Log]  │
  │                                             │
  │ ── Area Access Tab ──────────────────────── │
  │  Assigned Areas:                            │
  │   ✅ Plant1 / Area1          [Remove]       │
  │   ☐ Plant1 / Area-2         [Add]          │
  │   ☐ FTP-1 / POTLINE         [Add]          │
  │                                             │
  │  [Save Area Assignments]                    │
  └─────────────────────────────────────────────┘
```

### 7.2 Plants & Areas Registry (new admin sub-page)
```
[Admin → System → Plants & Areas]

  ┌─────────────────────────────────────────────┐
  │  Plant       Area       Tags   Active       │
  │  ─────────────────────────────────────────  │
  │  Plant1      Area1      119    ✅           │
  │  Plant1      Area-2     10     ✅           │
  │  FTP-1       POTLINE    129    ✅           │
  │                                             │
  │  [+ Add New Plant/Area]  [Sync from Tags]   │
  └─────────────────────────────────────────────┘
```

"Sync from Tags" button = runs the INSERT ... SELECT DISTINCT from `tag_master`.

### 7.3 Access Matrix View (read-only overview, admin only)
```
[Admin → Access Control → Matrix View]

  User          Role        Areas Assigned
  ─────────────────────────────────────────────────
  Mustafa       Admin       ALL (is_admin)
  Lokesh        Operator    Plant1/Area1
  sourav        Operator    FTP-1/POTLINE
  Jhon          Engineer    Plant1/Area1, Plant1/Area-2
  shayaan       Viewer      Plant1/Area1
  gufran        Viewer      (none assigned — sees nothing)
```

---

## 8. Backend API Changes Required

### 8.1 New Admin Endpoints (Flask)

```
GET    /api/admin/plants-areas
       → Returns list of all active plant/area combinations

GET    /api/admin/users/{id}/areas
       → Returns areas currently assigned to a user

PUT    /api/admin/users/{id}/areas
       body: { "plant_area_ids": [1, 3] }
       → Full replace of user's area assignments + writes access_audit_log row

POST   /api/admin/plants-areas
       body: { "plant_code": "FTP2", "area_code": "SMELTER", "plant": "FTP-2", "area": "Smelter", "display_name": "..." }
       → Creates new plant/area entry

GET    /api/admin/access-matrix
       → Returns full user→role→areas overview (admin only)
```

### 8.2 Area Filter Helper — CORRECT Implementation

> **CRITICAL IMPROVEMENT #4 — The `plant IN (...) AND area IN (...)` pattern is a SECURITY BUG.**  
>  
> Example: user assigned `Plant1/Area1` and `FTP-1/POTLINE`.  
> Wrong query: `WHERE plant IN ('Plant1','FTP-1') AND area IN ('Area1','POTLINE')`  
> This incorrectly allows `Plant1/POTLINE` and `FTP-1/Area1` — data the user must NOT see.  
>  
> **Correct pattern**: always JOIN through the assignment tables so the DB enforces the exact (plant, area) pairs.

```python
# ❌ WRONG — do not use this pattern
def get_area_filter_wrong(user_id):
    plants = [...]
    areas  = [...]
    return f"plant IN {plants} AND area IN {areas}"   # BUG: cross-product

# ✅ CORRECT — JOIN-based filter, exact pairs only
AREA_FILTER_JOIN = """
    JOIN historian_meta.plants_areas pa
      ON pa.plant = tm.plant
     AND pa.area  = tm.area
     AND pa.is_active = true
    JOIN historian_meta.user_area_assignments uaa
      ON uaa.plant_area_id = pa.id
     AND uaa.user_id = %(user_id)s
     AND uaa.revoked_at IS NULL
"""
# Usage: append AREA_FILTER_JOIN to any FROM clause that has tag_master aliased as tm
```

> **CRITICAL IMPROVEMENT #2 — Always check `pa.is_active = true`**  
> A user may remain assigned to a plant/area after it is decommissioned.  
> Every query must add `AND pa.is_active = true` to exclude inactive areas.  
> Inactive areas must never expose data — even if the assignment row still exists.

### 8.3 Area Assignment Fetch — ALWAYS from DB, Never from JWT

> **CRITICAL IMPROVEMENT #3 — NEVER trust JWT area lists for authorization.**  
>  
> Problem: Admin revokes user's access at 10:00. User's JWT expires at 18:00.  
> If backend trusts JWT `area_access` array, the revoked user keeps seeing data for 8 hours.  
> This is a serious industrial security flaw.  
>  
> **Rule**: JWT carries `user_id` only. Backend re-fetches area assignments from DB (or short-TTL cache) on every request.

```python
# ✅ CORRECT auth flow
def get_user_area_assignments(user_id: int) -> list[dict] | None:
    """
    Returns list of {plant, area, plant_area_id} for the user.
    Returns None  → user is Admin (bypass all filters).
    Returns []    → user has no assigned areas (sees nothing).
    Uses in-memory cache with 30s TTL. Invalidated on area update.
    NEVER reads from JWT payload for authorization decisions.
    """
    # 1. Check cache
    cached = _area_cache.get(user_id)
    if cached is not None:
        return cached

    # 2. Fetch from DB
    rows = db.execute("""
        SELECT pa.plant, pa.area, pa.id AS plant_area_id, r.is_admin
        FROM historian_meta.users u
        JOIN historian_meta.roles r ON r.id = u.role_id
        LEFT JOIN historian_meta.user_area_assignments uaa ON uaa.user_id = u.id AND uaa.revoked_at IS NULL
        LEFT JOIN historian_meta.plants_areas pa ON pa.id = uaa.plant_area_id AND pa.is_active = true
        WHERE u.id = %s AND u.status = 'approved'
    """, [user_id])

    if not rows:
        return []
    if rows[0]['is_admin']:
        return None   # bypass signal

    result = [{'plant': r['plant'], 'area': r['area']} for r in rows if r['plant']]
    _area_cache.set(user_id, result, ttl=30)
    return result
```

> **CRITICAL IMPROVEMENT #7 — Cache area assignments (30–60s TTL)**  
> Area assignment query runs on every API call. Under HMI polling load (1s interval, many users)  
> this would overload PostgreSQL. Use in-memory dict with TTL or Redis.  
> Cache must be **invalidated immediately** when admin saves a new area assignment via `PUT /api/admin/users/{id}/areas`.

### 8.4 JWT / Session Payload — display only, NOT for authorization

```json
{
  "user_id": 12,
  "username": "Lokesh",
  "role": "Operator",
  "is_admin": false,
  "module_permissions": {
    "hmi": { "can_view": true, "can_operate": false },
    "reports": { "can_view": true, "can_generate": true }
  },
  "area_access": [
    { "plant": "Plant1", "area": "Area1", "display_name": "Plant1 — Area1" }
  ]
}
```

> `area_access` in JWT is **for UI display only** (populate dropdowns, show user their scope).  
> **Backend must NEVER use this array as an authorization check.** Always re-fetch from DB/cache.

### 8.5 OPC Backend Security Boundary

> **CRITICAL IMPROVEMENT — OPC backend must not be directly callable by frontend.**  
>  
> ❌ Wrong flow: `Frontend → C# OPC /api/opc/values?plant=X&area=Y`  
> User can fabricate any plant/area in the query string, bypassing Flask auth entirely.  
>  
> ✅ Correct flow:
> ```
> Frontend → Flask API (validates JWT + re-fetches area from DB)
>                     → Flask calls C# OPC backend internally (server-to-server, no user token)
>                     → Flask filters the OPC response by user's area assignments
>                     → Flask returns filtered data to frontend
> ```
> The C# OPC backend `/api/opc/values` must only be reachable from localhost or internal network — never exposed directly to the browser.

### 8.6 WebSocket / Live Session Revalidation

> **CRITICAL IMPROVEMENT #10 — Revoked users must not keep receiving live updates.**  
>  
> Scenario: user has open WebSocket/SignalR connection. Admin revokes their area at 10:00.  
> Without revalidation, the socket keeps pushing live tag data.  
>  
> **Rule**: Every live push endpoint (SignalR hub, WebSocket) must revalidate area assignments every 60 seconds.  
> On area cache invalidation (admin saved new assignments), force-disconnect affected sessions immediately.

| Endpoint | Filter Applied | Method |
|----------|---------------|--------|
| `GET /api/opc/values` | `tag_uid = ANY(visible_uids)` | `authz.get_visible_tag_uids()` |
| `GET /api/plc/values` | `tag_uid = ANY(visible_uids)` | `authz.get_visible_tag_uids()` |
| `GET /api/tags` | `tag_uid = ANY(visible_uids)` | `authz.get_visible_tag_uids()` |
| `GET /api/reports/*` | `tag_uid = ANY(visible_uids)` | `authz.get_visible_tag_uids()` |
| `GET /api/alarms/*` | `tag_uid = ANY(visible_uids)` | `authz.get_visible_tag_uids()` |
| `GET /api/analytics/*` | `tag_uid = ANY(visible_uids)` | `authz.get_visible_tag_uids()` |
| `GET /api/historian/trends` | `tag_uid = ANY(visible_uids)` | `authz.get_visible_tag_uids()` |
| SignalR / WebSocket push | Revalidate every 60s via TTL cache + **immediate disconnect on cache invalidation event** |

> **WebSocket revocation**: 60s TTL is the baseline. For immediate revocation, `authz.invalidate_user_cache(user_id)` (called by admin endpoints) should emit an internal pub/sub event (e.g., in-process `threading.Event` or Redis pub/sub if multi-process) that the active WebSocket handler for that user subscribes to. On event: close the socket immediately. TTL-only approach leaves a maximum 60s window of stale access.

> **Centralised filter enforcement**: Every endpoint in the table above must call `authz.get_visible_tag_uids()`. No endpoint constructs its own filter. Code review must reject any PR that bypasses `AuthorizationService`.

---

## 9. Frontend (React HMI) Changes Required

### 9.1 Tag/HMI View — Area Filter
- On login, store `area_access` from JWT in auth context **for display only** (dropdowns, labels)
- HMI polls `GET /api/opc/values` — Flask applies DB-level filter, frontend gets only its data
- Tags from other areas are **not fetched** — filtered at DB/API level, not hidden in UI
- Area selector dropdown (if user has multiple areas) switches the active view

> **CRITICAL IMPROVEMENT #8 — Multi-Area UX: do NOT auto-load all areas at once.**  
> If user has Plant1/Area1 + Plant1/Area-2 + FTP-1/POTLINE, loading all simultaneously:
> - Clutters HMI with 300+ tags
> - Triples polling load  
>  
> **Rule**: Default to `last_used_area` (stored in localStorage). Load tags for selected area only.  
> Provide an explicit "All Areas" toggle for Engineers/Admin only.

### 9.2 Reports Page — Area Filter
- Plant/Area dropdown shows only user's `area_access` list from JWT (display)
- Report queries send selected `plant_area_id` — backend validates it against DB before executing

### 9.3 Admin Panel — Area Assignment UI
- New "Area Access" tab in User Edit form
- Checklist from `GET /api/admin/plants-areas` (active only)
- Currently assigned ones pre-checked
- Save → `PUT /api/admin/users/{id}/areas` → backend writes audit log + invalidates that user's cache

### 9.4 No Data State
- If user has 0 active area assignments → show banner: *"No areas assigned to your account. Contact administrator."*
- All data views show empty state — never crash, never silently show all data

---

## 10. Access Control Logic — Decision Tree

```
User makes request to any data endpoint
         │
         ▼
Is user.role.is_admin?  [via AuthorizationService.is_admin()]
    YES → bypass all area/tag filters → return ALL data
    NO  ↓
         ▼
Does role have can_view for this module?  [role_module_permissions]
    NO  → return 403 Forbidden
    YES ↓
         ▼
Call AuthorizationService.get_visible_tag_uids(user_id)
    Returns None    → admin bypass (should not reach here)
    Returns []      → return 200 empty + "No areas assigned" warning
    Returns [uid..] ↓
         ▼
Apply scoped filter via pre-resolved tag_uid set:
    WHERE tm.tag_uid = ANY(:visible_tag_uids)
    ─────────────────────────────────────────────────
    ⚠ NEVER use: WHERE plant IN (...) AND area IN (...)
    That is a SECURITY BUG — cross-product allows wrong areas.
    The resolved tag_uid set was produced by JOIN through
    user_area_assignments → plants_areas (exact pair matching).
    ─────────────────────────────────────────────────
         │
         ▼
Return filtered data (only tag_uids in the resolved set)
```

> **Why pre-resolution instead of inline JOIN?**  
> `get_visible_tag_uids()` runs the area+tag JOIN **once** and caches the result (60s TTL).  
> All historian, alarm, analytics, and HMI queries then use `tag_uid = ANY(array)` — a single indexed lookup.  
> Inline JOINs on historian timeseries tables at millions of rows is a performance hazard. See §24 Audit Item 3.

---

## 11. Implementation Order (Step-by-Step)

### Phase 1 — Database (do first, no code risk)
1. Create `historian_meta.plants_areas` table
2. Seed it from existing `tag_master` distinct plant/area values
3. Create `historian_meta.user_area_assignments` table
4. Assign initial areas to existing users (manual SQL for now)

### Phase 2 — Backend APIs
5. Add `get_user_area_filter()` helper function in Flask auth utils
6. Implement `GET/PUT /api/admin/plants-areas` endpoints
7. Implement `GET/PUT /api/admin/users/{id}/areas` endpoints
8. Modify `GET /api/tags` and `GET /api/opc/values` to apply area filter
9. Modify reports, alarms, analytics, historian endpoints
10. Add `area_access` to JWT/session payload on login

### Phase 3 — Frontend
11. Store `area_access` in auth context on login
12. Add "Area Access" tab in Admin → User Edit
13. Apply area filter in HMI tag list component
14. Apply area filter in Reports plant/area dropdown
15. Add "no areas assigned" empty state

### Phase 4 — Testing
16. Login as Lokesh (Operator / Plant1/Area1) → confirm only Plant1/Area1 tags visible
17. Login as sourav (Operator / FTP-1/POTLINE) → confirm only FTP-1 tags visible
18. Login as Mustafa (Admin) → confirm all areas visible (admin bypass)
19. Create user with 0 areas → confirm empty state shown

---

## 12. Rules That Must Not Be Broken

1. **Admin role always bypasses area filter** — `is_admin = true` → no filter applied
2. **Area filter is enforced at DB level via JOIN** — never `plant IN (...) AND area IN (...)`; use JOIN through `user_area_assignments → plants_areas`
3. **Zero area assignment = zero data** — empty assignment list returns empty dataset, never all data
4. **Role permissions still apply within area scope** — a Viewer assigned to FTP-1 can see but not operate
5. **C# OPC backend is internal only** — Flask validates user and filters; OPC backend never called directly by browser
6. **Plant access does NOT imply access to all areas in that plant** — `Plant1/Area1` does NOT grant `Plant1/Area-2`; every area is a separate explicit assignment row
7. **New plants/areas are OFF by default** — new tags with new plant/area values do not auto-expose; admin must add to `plants_areas` and assign
8. **Inactive areas are invisible** — `plants_areas.is_active = false` means ALL queries must exclude it even if assignment row still exists
9. **JWT `area_access` is for display only** — backend NEVER uses it for authorization; always re-fetch from DB/cache
10. **Audit every assignment change** — every `PUT /api/admin/users/{id}/areas` call writes a row to `access_audit_log` with old areas, new areas, admin identity, IP
11. **Live sessions revalidate every 60s** — SignalR/WebSocket connections check area assignments periodically; revoked users are disconnected immediately on cache invalidation
12. **Consistent soft-delete strategy** — each table uses its own archival column; never physically delete access-control rows (required for audit compliance)

| Table | Archival Column | Meaning |
|-------|----------------|---------|
| `users` | `status` | `'approved'` / `'deactivated'` / `'pending'` / `'rejected'` |
| `plants_areas` | `is_active` | `false` = decommissioned, excluded from all JOINs |
| `active_sessions` | `is_active` + `revoked_reason` | `false` = superseded/expired/revoked |
| `user_area_assignments` | `revoked_at` | `NOT NULL` = revoked; `NULL` = still active |
| `access_audit_log` | — | Append-only, never deleted; retain minimum 2 years |
| `user_tag_access` | — | Full replace via `set_tag_access()` (no soft delete needed — row absence = OPEN) |

---

## 13. SQL Reference — Complete Setup

```sql
-- ── 1. Master plant/area registry ─────────────────────────────────────────
CREATE TABLE historian_meta.plants_areas (
    id           SERIAL PRIMARY KEY,
    plant_code   VARCHAR(50)  NOT NULL,
    area_code    VARCHAR(50)  NOT NULL,
    plant        VARCHAR(100) NOT NULL,
    area         VARCHAR(100) NOT NULL,
    display_name VARCHAR(200),
    description  TEXT,
    is_active    BOOLEAN NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (plant_code, area_code),
    UNIQUE (plant, area)
);
CREATE INDEX idx_plants_areas_plant_area ON historian_meta.plants_areas(plant, area);

-- ── 2. User → area mapping ─────────────────────────────────────────────────
CREATE TABLE historian_meta.user_area_assignments (
    id             SERIAL PRIMARY KEY,
    user_id        INTEGER NOT NULL REFERENCES historian_meta.users(id) ON DELETE CASCADE,
    plant_area_id  INTEGER NOT NULL REFERENCES historian_meta.plants_areas(id) ON DELETE CASCADE,
    assigned_by    INTEGER REFERENCES historian_meta.users(id),
    assigned_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at     TIMESTAMPTZ,
    notes          TEXT
    -- ⚠ No inline UNIQUE — see partial index below
);
CREATE UNIQUE INDEX idx_user_area_active_unique
    ON historian_meta.user_area_assignments(user_id, plant_area_id)
    WHERE revoked_at IS NULL;
CREATE INDEX ON historian_meta.user_area_assignments(user_id);

-- ── 3. Audit log ───────────────────────────────────────────────────────────
CREATE TABLE historian_meta.access_audit_log (
    id              BIGSERIAL PRIMARY KEY,
    event_time      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    admin_user_id   INTEGER NOT NULL,
    admin_username  VARCHAR(100) NOT NULL,
    admin_ip        VARCHAR(45),
    target_user_id  INTEGER NOT NULL,
    target_username VARCHAR(100) NOT NULL,
    action          VARCHAR(20) NOT NULL,   -- 'ASSIGN' | 'REVOKE' | 'REPLACE' | 'ROLE_CHANGED' | ...
    old_state       JSONB,   -- e.g. {"areas":["Plant1/Area1"],"role":"Operator","quota":3}
    new_state       JSONB,   -- e.g. {"areas":["Plant1/Area1","FTP-1/POTLINE"],"role":"Operator","quota":3}
    notes           TEXT
);
CREATE INDEX ON historian_meta.access_audit_log(target_user_id, event_time DESC);
CREATE INDEX idx_audit_log_old_state ON historian_meta.access_audit_log USING gin(old_state);
CREATE INDEX idx_audit_log_new_state ON historian_meta.access_audit_log USING gin(new_state);
-- JSONB GIN indexes allow: SELECT * FROM access_audit_log WHERE new_state @> '{"role":"Engineer"}'

-- ── 4. Performance index on tag_master ────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_tag_master_plant_area
    ON historian_meta.tag_master(plant, area);

-- ── 5. Seed plants_areas from tag_master ──────────────────────────────────
INSERT INTO historian_meta.plants_areas (plant_code, area_code, plant, area, display_name)
SELECT DISTINCT
    UPPER(REGEXP_REPLACE(plant, '[^A-Za-z0-9]', '', 'g')),
    UPPER(REGEXP_REPLACE(area,  '[^A-Za-z0-9]', '', 'g')),
    plant, area,
    plant || ' — ' || area
FROM historian_meta.tag_master
WHERE plant IS NOT NULL AND area IS NOT NULL
ON CONFLICT (plant, area) DO NOTHING;

-- ── 6. Admin overview view ────────────────────────────────────────────────
CREATE OR REPLACE VIEW historian_meta.v_user_access_matrix AS
SELECT
    u.id AS user_id,
    u.username,
    r.name AS role_name,
    r.is_admin,
    STRING_AGG(pa.display_name, ', ' ORDER BY pa.plant, pa.area)
        FILTER (WHERE pa.is_active = true AND uaa.revoked_at IS NULL) AS assigned_areas,
    COUNT(uaa.id) FILTER (WHERE pa.is_active = true AND uaa.revoked_at IS NULL) AS area_count
FROM historian_meta.users u
JOIN historian_meta.roles r ON r.id = u.role_id
LEFT JOIN historian_meta.user_area_assignments uaa ON uaa.user_id = u.id
LEFT JOIN historian_meta.plants_areas pa ON pa.id = uaa.plant_area_id
GROUP BY u.id, u.username, r.name, r.is_admin;
```

### Correct JOIN-Based Filter Pattern (use in ALL data queries)

```sql
-- Replace "tm" with the alias for tag_master in any specific query
-- Replace %(user_id)s with actual parameter binding

SELECT tm.*
FROM historian_meta.tag_master tm
JOIN historian_meta.plants_areas pa
  ON pa.plant = tm.plant
 AND pa.area  = tm.area
 AND pa.is_active = true                        -- ← CRITICAL: exclude decommissioned
JOIN historian_meta.user_area_assignments uaa
  ON uaa.plant_area_id = pa.id
 AND uaa.user_id = %(user_id)s
 AND uaa.revoked_at IS NULL                     -- ← CRITICAL: exclude revoked
WHERE tm.enabled = true;
```

### Future Hierarchy Extension (no breaking changes needed)

```
-- When system grows to: Enterprise → Plant → Area → Unit → Line
-- Just add columns to plants_areas:
ALTER TABLE historian_meta.plants_areas ADD COLUMN unit_code VARCHAR(50);
ALTER TABLE historian_meta.plants_areas ADD COLUMN line_code VARCHAR(50);
-- Existing rows default to NULL (backward compatible)
```

---

## 14. Summary Table — What Each Role Sees

| Role | Module Access (from role_module_permissions) | Data Scope (from area assignments) |
|------|---------------------------------------------|-------------------------------------|
| **Admin** | All modules, all actions | ALL plants/areas (bypass) |
| **Engineer** | HMI view, Reports view+generate, Analytics view, Alarms view | Only assigned areas |
| **Operator** | HMI view, Reports view+generate, Alarms full | Only assigned areas |
| **Viewer** | HMI view, Alarms view only | Only assigned areas |

Two Operators with different area assignments **see completely different data** despite identical role permissions.

---

## 15. Critical Fixes Priority Table

| Priority | # | Issue | Status |
|----------|---|-------|--------|
| 🔴 CRITICAL | 4 | `plant IN (...) AND area IN (...)` is a security bug — cross-product allows wrong areas | **Fixed in §8.2** |
| 🔴 CRITICAL | 3 | JWT `area_access` must never be used for backend authorization | **Fixed in §8.3** |
| 🔴 CRITICAL | 5 | Missing indexes on `tag_master(plant,area)` and `plants_areas(plant,area)` | **Fixed in §13** |
| 🔴 CRITICAL | 1 | plant/area text used as key — rename breaks references | **Fixed in §5.1 (plant_code/area_code)** |
| 🟠 HIGH | 2 | Inactive areas still expose data if assignment row exists | **Fixed — `pa.is_active=true` in all JOINs** |
| 🟠 HIGH | 7 | Area assignment queried per-request overloads DB | **Fixed — 30s TTL cache, invalidate on update** |
| 🟠 HIGH | 9 | No audit trail of who granted/revoked access | **Fixed — `access_audit_log` table in §5.3** |
| 🟠 HIGH | 10 | Revoked users keep live WebSocket data until token expiry | **Fixed — 60s revalidation in §8.6** |
| 🟡 FUTURE | 6 | PostgreSQL Row Level Security for DB-layer protection | Compatible — add RLS later without schema change |
| 🟡 FUTURE | — | Hierarchical areas (Plant→Area→Unit→Line) | Compatible — extend `plants_areas` columns |

---

*This document is the binding specification for Plant/Area Access Control implementation.*  
*Do not begin Phase 2 (backend code) until the Phase 1 SQL (§13) is executed and verified.*

---

## 16. Activation Key — License-Based User Creation Limit

### 16.1 Concept

The system enforces a **maximum number of active users** based on a license activation key stored in the database.  
An administrator cannot create more users than the seat count embedded in the activation key.  
This prevents unlimited account creation on-premises without a valid license upgrade.

### 16.2 Database Table

```sql
-- ── historian_meta.license_keys ──────────────────────────────────────────
-- ⚠ SECURITY NOTE: max_users stored in DB is a CACHED DISPLAY value only.
-- It MUST NOT be trusted without first verifying signed_payload with the embedded public key.
-- A DB admin running UPDATE license_keys SET max_users=9999 cannot bypass enforcement
-- because all runtime limit checks call _get_verified_max_users() which extracts
-- max_users from the ECDSA-verified signed_payload — never from the raw DB column.
CREATE TABLE historian_meta.license_keys (
    id               SERIAL PRIMARY KEY,
    key_hash         VARCHAR(128) NOT NULL UNIQUE,   -- SHA-256 of raw activation key
    key_label        VARCHAR(200),                   -- human description e.g. "Plant1 Licence v2"
    signed_payload   TEXT NOT NULL,                  -- ECDSA-signed JSON blob (base64url) — authoritative
    max_users        INTEGER NOT NULL DEFAULT 5,     -- ⚠ CACHED from signed_payload for display ONLY
    max_areas        INTEGER,                        -- optional: max areas per user (NULL = unlimited)
    issued_to        VARCHAR(200),                   -- organisation name
    issued_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_until      TIMESTAMPTZ,                    -- NULL = perpetual
    is_active        BOOLEAN NOT NULL DEFAULT true,
    activated_by     INTEGER REFERENCES historian_meta.users(id),
    activated_at     TIMESTAMPTZ,
    notes            TEXT
);

-- Only one key can be active at any time
CREATE UNIQUE INDEX idx_license_keys_active
    ON historian_meta.license_keys(is_active)
    WHERE is_active = true;
```

### 16.3 User Count Enforcement Logic

The check is performed **inside the user-creation endpoint** (`POST /api/admin/users`) before the `INSERT` is executed.

```python
# Flask — admin_controller.py (create user endpoint)

def _get_verified_max_users() -> int:
    """
    ⚠ AUTHORITATIVE license limit check.
    Reads signed_payload from DB, verifies ECDSA signature using embedded public key,
    then extracts max_users from the verified JSON payload.
    NEVER reads max_users column directly — that column is cached display-only
    and can be tampered by a DB admin without breaking this function.

    Payload format (signed by vendor private key):
        { "customer": "ABC Steel", "max_users": 50, "expiry": "2027-01-01", "max_areas": null }

    Returns 0 if no active key found, signature invalid, or key expired.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    import base64, json
    # Public key is embedded in source code / config — NOT in DB
    PUBLIC_KEY_BYTES = bytes.fromhex(current_app.config['LICENSE_PUBLIC_KEY_HEX'])
    public_key = Ed25519PublicKey.from_public_bytes(PUBLIC_KEY_BYTES)

    with db.cursor() as cur:
        cur.execute("""
            SELECT signed_payload
            FROM historian_meta.license_keys
            WHERE is_active = true
              AND (valid_until IS NULL OR valid_until > NOW())
            LIMIT 1
        """)
        row = cur.fetchone()
    if not row:
        return 0

    try:
        # signed_payload format: base64url(payload_json) + '.' + base64url(signature)
        parts = row['signed_payload'].split('.')
        payload_bytes = base64.urlsafe_b64decode(parts[0] + '==')
        signature     = base64.urlsafe_b64decode(parts[1] + '==')
        public_key.verify(signature, payload_bytes)   # raises InvalidSignature on tamper
        payload = json.loads(payload_bytes)
        return int(payload['max_users'])
    except Exception:
        return 0   # tampered or malformed — treat as no valid license


def _check_user_limit() -> tuple[bool, int, int]:
    """
    Returns (allowed: bool, current_count: int, max_users: int).
    Admin users (is_admin=true) are never counted toward the seat limit.
    Deactivated / deleted users are not counted.
    max_users is extracted from the ECDSA-verified signed_payload — not from the DB column.
    """
    with db.cursor() as cur:
        # Count currently active non-admin users
        cur.execute("""
            SELECT COUNT(*) AS current_count
            FROM historian_meta.users u
            JOIN historian_meta.roles r ON r.id = u.role_id
            WHERE u.status IN ('approved', 'pending')
              AND r.is_admin = false
        """)
        current_count = cur.fetchone()['current_count']

    max_users = _get_verified_max_users()   # ← verified from signed payload, not DB column
    return (current_count < max_users), current_count, max_users


@admin_bp.route('/api/admin/users', methods=['POST'])
@require_admin
def create_user():
    allowed, current, maximum = _check_user_limit()
    if not allowed:
        return jsonify({
            'success': False,
            'error': f'User creation limit reached. '
                     f'License allows {maximum} users, currently {current} active. '
                     f'Contact administrator to upgrade license.'
        }), 403

    # ... proceed with INSERT ...
```

**Counting rules**:
- `Admin` role users (`is_admin = true`) are **excluded** from seat count — they are always allowed
- Users with `status = 'deactivated'` or `'rejected'` are **not counted**
- `status = 'pending'` users **are counted** (reservation hold — prevents abuse of pending-spam)

### 16.4 Activation Key Endpoint

```
POST /api/admin/license/activate
     body: { "activation_key": "<raw key string>" }
     → Validates key signature, extracts seat count, stores hash in license_keys
     → Deactivates any previously active key before inserting new one

GET  /api/admin/license/status
     → Returns { max_users, current_users, valid_until, key_label, is_valid }
     → Used by Admin Console to show license status banner
```

### 16.5 UI — License Status Banner (Admin Console)

```
┌─────────────────────────────────────────────────────────────┐
│  🔑 License: Plant1 Licence v2  │  Users: 7 / 10  │  ✅ Active  │
│  Valid until: 2027-12-31          [Change Key]              │
└─────────────────────────────────────────────────────────────┘
```

If `current_users / max_users >= 0.9`:  
→ Show **amber warning**: *"9 of 10 user seats used. Consider upgrading your license."*

If limit is reached and admin tries to create user:  
→ The "Add User" button is **disabled** with tooltip: *"User limit reached (10/10). Upgrade license to add more users."*

### 16.6 Rules

| Rule | Detail |
|------|--------|
| No active license | System blocks ALL new non-admin user creation |
| Expired license (`valid_until < NOW()`) | Block new user creation; existing users continue to work |
| Deactivating a user | Frees one seat immediately |
| Admin accounts | Never consume a seat — always creatable by existing admin |
| License key format | Raw key is never stored — only `SHA-256(raw_key)` is persisted |
| Multiple keys | Only one `is_active = true` key allowed at any time (partial index enforces) |

---

## 17. Single Concurrent Session Enforcement (One Login Per User)

### 17.1 Concept

A user **cannot be logged in from more than one device or browser simultaneously**.  
If they authenticate from a second system, the **first (old) session is automatically invalidated**.  
The old device immediately receives a `401 Session superseded` response on the next API call.

This rule applies to **all non-admin users** by default.  
Admin accounts are configurable (default: allow concurrent sessions, can be restricted per user).

### 17.2 Database Table

```sql
-- ── historian_meta.active_sessions ───────────────────────────────────────
CREATE TABLE historian_meta.active_sessions (
    id              BIGSERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES historian_meta.users(id) ON DELETE CASCADE,
    session_token   VARCHAR(256) NOT NULL UNIQUE,   -- opaque random token (not the JWT)
    jwt_jti         VARCHAR(128),                   -- JWT ID for correlation (optional)
    ip_address      VARCHAR(45),
    user_agent      TEXT,
    device_name     VARCHAR(150),                   -- e.g. 'Control Room PC-3', 'Mobile-iOS'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    superseded_by   BIGINT REFERENCES historian_meta.active_sessions(id),
    revoked_reason  VARCHAR(50)   -- 'LOGOUT' | 'SUPERSEDED' | 'ADMIN_REVOKE' | 'EXPIRED'
);

CREATE INDEX idx_active_sessions_user_id ON historian_meta.active_sessions(user_id);
CREATE INDEX idx_active_sessions_token   ON historian_meta.active_sessions(session_token);
CREATE INDEX idx_active_sessions_active  ON historian_meta.active_sessions(user_id, is_active)
    WHERE is_active = true;
```

### 17.3 Login Flow — Session Enforcement

```
User POSTs /api/auth/login
    │
    ▼
Validate credentials (password hash) ✓
    │
    ▼
SELECT id, allow_concurrent_sessions  ← fetch flag needed for supersede decision
FROM historian_meta.users WHERE id = ?
    │
    ▼
BEGIN TRANSACTION  ← required to prevent race condition
    │
    ▼
SELECT id FROM active_sessions
WHERE user_id = ? AND is_active = true
FOR UPDATE  ← row-level lock: if two logins race, second waits here
    │
    ├── Row(s) found (existing session)?
    │       YES ──▶ Check user.allow_concurrent_sessions:
    │               IF false (default) ──▶ UPDATE active_sessions
    │                   SET is_active = false,
    │                       revoked_reason = 'SUPERSEDED',
    │                       superseded_by = <will be set after INSERT>
    │                   WHERE user_id = ? AND is_active = true
    │                   (invalidates ALL previous sessions for this user)
    │               IF true (admin/concurrent allowed) ──▶ skip supersede,
    │                   proceed to INSERT new session alongside existing ones
    │
    ▼
INSERT INTO active_sessions (user_id, session_token, ip_address, user_agent,
                              device_name, expires_at)
VALUES (...)
RETURNING id  → use this id to backfill superseded_by
    │
    ▼
COMMIT TRANSACTION
    │
    ▼
Generate JWT with { user_id, jti: session_token }
Return JWT + session_token to client
```

> **Why `FOR UPDATE`?** Without it, two simultaneous login requests both read 0 active sessions,
> both proceed to INSERT, and both become active — violating the single-session rule.
> `FOR UPDATE` ensures the second login blocks until the first transaction commits.

### 17.4 Per-Request Session Validation Middleware

Every protected API endpoint runs this check **after JWT signature validation**:

```python
# utils/decorators.py — @require_auth decorator (MODIFIED)

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Step 1: Validate JWT signature + expiry (existing logic)
        payload = verify_jwt(request.headers.get('Authorization'))
        if not payload:
            return jsonify({'error': 'Invalid or expired token'}), 401

        # Step 2: ── NEW ── Validate session is still active in DB
        session_token = payload.get('jti')   # JWT ID = session_token
        if session_token:
            session = _get_active_session(session_token)   # 10s TTL cache
            # ⚠ Check BOTH is_active=true AND expires_at > NOW():
            # is_active alone is not sufficient — background cleanup may be delayed
            # by minutes, leaving expired rows with is_active=true in the table.
            if (not session
                    or not session['is_active']
                    or session['expires_at'] <= datetime.utcnow()):
                return jsonify({
                    'error': 'Session superseded',
                    'code':  'SESSION_SUPERSEDED',
                    'message': 'Your account was logged in from another device. '
                               'Please log in again.'
                }), 401

            # Update last_seen_at (throttled — max once per 30s to avoid DB write storm)
            _maybe_refresh_session(session_token)

        g.user_id = payload['user_id']
        return f(*args, **kwargs)
    return decorated
```

### 17.5 Frontend Handling — Session Superseded

When the frontend receives `HTTP 401` with `code: "SESSION_SUPERSEDED"`:

```typescript
// api service interceptor — apex-hmi/src/services/api.ts

if (error.response?.status === 401) {
  const code = error.response?.data?.code;

  if (code === 'SESSION_SUPERSEDED') {
    // Clear local auth state
    authStore.logout();
    // Show specific message (NOT generic "session expired")
    toast.error(
      'Your session was terminated because your account logged in from another device.',
      { duration: 8000 }
    );
    router.push('/login');
    return;
  }

  // Generic 401 (expired token)
  authStore.logout();
  router.push('/login');
}
```

### 17.6 Admin Session Management

Admin can forcibly terminate any user's session:

```
GET  /api/admin/users/{id}/sessions
     → Returns { active_session: { ip, user_agent, created_at, last_seen_at } | null }

DELETE /api/admin/users/{id}/sessions
     → Invalidates all active sessions for that user
     → Writes to access_audit_log with action = 'SESSION_REVOKED'
     → Next API call from that user returns SESSION_SUPERSEDED
```

### 17.7 Session Lifecycle Diagram

```
User A logs in (Device 1, IP: 192.168.1.10)
    │  session_id=101, is_active=true
    │
    ├─── makes API calls → session validated ✓
    │
User A logs in (Device 2, IP: 10.0.0.5)   ← NEW LOGIN
    │
    ├─── server detects session_id=101 still active
    │
    ├─── session_id=101 → is_active=false, revoked_reason='SUPERSEDED'
    │
    ├─── new session_id=102 created (Device 2)
    │
    └─── Device 1 makes next API call
             │  JWT still valid (not expired)
             │  session_token=101 → is_active=false
             └─ returns 401 SESSION_SUPERSEDED
                Device 1 user is shown: "Logged in from another device"
```

### 17.8 Session Rules

| Rule | Detail |
|------|--------|
| Default | Single session per user for all non-admin roles |
| Admin role | Concurrent sessions allowed by default (configurable per user via `allow_concurrent_sessions` flag) |
| Session expiry | Matches JWT expiry — both cleaned up on logout |
| Forced logout | Admin revoke → `revoked_reason = 'ADMIN_REVOKE'` → same 401 flow |
| Inactivity | If `last_seen_at < NOW() - 30 minutes` → session auto-marked expired (background job) |
| Audit | Every session creation, supersession, and revocation is logged in `access_audit_log` |
| Cache | `is_active` checked via 10s TTL in-memory cache per session_token (avoid per-request DB hit) |

---

## 18. Multi-Area Assignment Based on Role Privilege Level

### 18.1 Concept

The **Role** defines not only *what modules* a user can access, but also **how many plant/area scopes** they can be assigned to simultaneously.  
This prevents over-scoping lower-privilege users while allowing Engineers/Supervisors to span multiple areas.

### 18.2 Role-Level Area Quota

Add a column to the `roles` table:

```sql
ALTER TABLE historian_meta.roles
    ADD COLUMN max_area_assignments INTEGER DEFAULT NULL;
-- NULL = no limit (Admin / Senior Engineer)
-- 1    = Viewer can only be assigned to one area
-- 3    = Operator can be assigned to up to 3 areas
-- 10   = Engineer can be assigned to up to 10 areas
```

### 18.3 Per-Role Defaults

| Role | `max_area_assignments` | Rationale |
|------|------------------------|-----------|
| **Admin** | `NULL` (unlimited) | Sees everything — bypass applies |
| **Engineer** | `NULL` or 10 | Multi-site supervision scope |
| **Operator** | 3 | Typically responsible for one line + adjacent buffer |
| **Viewer** | 1 | Read-only, narrow scope by policy |

These are **defaults set by the Admin** and can be overridden per individual user if needed.

### 18.4 Per-User Override (Optional)

For exceptional cases, individual users can have their own quota that **overrides** the role default:

```sql
ALTER TABLE historian_meta.users
    ADD COLUMN max_area_override INTEGER DEFAULT NULL;
-- NULL = use role's max_area_assignments
-- Non-null = this specific user's ceiling (can be higher OR lower than role default)
```

**Effective limit calculation**:
```python
def get_effective_area_limit(user_id: int) -> int | None:
    """
    Returns max area count for this user.
    None = unlimited.
    Precedence: user.max_area_override > role.max_area_assignments > None
    """
    user = get_user_with_role(user_id)
    if user['max_area_override'] is not None:
        return user['max_area_override']        # explicit per-user override
    if user['role_max_area_assignments'] is not None:
        return user['role_max_area_assignments'] # role-level default
    return None                                  # unlimited
```

### 18.5 Enforcement at Assignment Time

The quota is checked **inside `PUT /api/admin/users/{id}/areas`** before committing the new assignment list:

```python
# services/area_access_service.py — set_user_areas() method

def set_user_areas(self, user_id, plant_area_ids, admin_user_id, admin_ip=None):
    limit = get_effective_area_limit(user_id)

    if limit is not None and len(plant_area_ids) > limit:
        role_name = get_user_role_name(user_id)
        raise AreaLimitExceededError(
            f"Cannot assign {len(plant_area_ids)} areas to this user. "
            f"Role '{role_name}' allows a maximum of {limit} area assignment(s). "
            f"To increase the limit, update the role's max_area_assignments "
            f"or set a per-user override."
        )

    # ... proceed with assignment replace ...
```

**Admin Console behaviour** when the limit is about to be exceeded:
```
┌──────────────────────────────────────────────────────┐
│  Assign Areas to: Lokesh (Operator)                  │
│  Role limit: 3 areas maximum                         │
│                                                      │
│  ✅ Plant1 / Area1          (assigned)               │
│  ✅ Plant1 / Area-2         (assigned)               │
│  ☐  FTP-1 / POTLINE         ← would reach limit (3)  │
│  ☐  BlastFurnace / Equipment  ← disabled (over limit) │
│                                                      │
│  Areas selected: 2 / 3  ← live counter              │
│  [Save Assignments]                                  │
└──────────────────────────────────────────────────────┘
```

Checkboxes beyond the limit are **disabled** in the UI as the counter is reached.  
The "Save Assignments" button shows `(2/3 areas)` as a live counter.

### 18.6 Multiple-Area Access in Data Queries

When a user has multiple area assignments, **every data endpoint returns the UNION** of all assigned areas.  
`AuthorizationService.get_visible_tag_uids()` resolves the UNION of all assigned areas (and applies tag-level filtering) in a single call. The result is a deduplicated `int[]` of `tag_uid` values.

```sql
-- A user assigned to Plant1/Area1 AND Plant1/Area-2 AND FTP-1/POTLINE sees all three
-- via the pre-resolved tag_uid set. No runtime JOIN or DISTINCT needed:
SELECT tm.tag_uid, tm.tag_name, tm.plant, tm.area
FROM historian_meta.tag_master tm
WHERE tm.tag_uid = ANY(:visible_uids)   -- :visible_uids = result of get_visible_tag_uids()
  AND tm.enabled = true;
-- Returns tags from ALL three areas. No duplicate rows (tag_uid is unique per tag).
-- No DISTINCT needed — DISTINCT on large tables hides join problems and hurts performance.
```

> **DISTINCT caution**: `SELECT DISTINCT` masks duplicate-producing JOINs and is expensive on
> historian timeseries tables. The resolved-uid approach eliminates the need for DISTINCT entirely.

### 18.7 UI — Multi-Area Selector in HMI

When a user has **more than one active area**, the HMI header shows an area selector:

```
┌─────────────────────────────────────────────────────────┐
│  HMI Dashboard                                          │
│  Viewing area: [Plant1 / Area1  ▼]  ← dropdown         │
│                 Plant1 / Area-2                         │
│                 FTP-1 / POTLINE                         │
│                 ── All Areas ──  (Engineers only)       │
└─────────────────────────────────────────────────────────┘
```

Rules:
- Default view = `last_used_area` from `localStorage` (avoids loading all tags on every login)
- **"All Areas"** option is only shown if `role.name IN ('Admin', 'Engineer')` — avoids overloading Operators with 300+ tags
- Switching area: updates `localStorage` + re-fetches tags for newly selected area only
- Area assignment changes by Admin propagate in ≤ 30s (cache TTL) without requiring re-login

### 18.8 Access Matrix — Shows Multi-Area Correctly

The access matrix view (§7.3) displays all assigned areas per user:

```
User          Role        Area Quota    Areas Assigned
──────────────────────────────────────────────────────────────────────
Mustafa       Admin       Unlimited     ALL (is_admin bypass)
Jhon          Engineer    Unlimited     Plant1/Area1, Plant1/Area-2, FTP-1/POTLINE
Lokesh        Operator    3 max         Plant1/Area1, Plant1/Area-2  (2/3)
sourav        Operator    3 max         FTP-1/POTLINE  (1/3)
shayaan       Viewer      1 max         Plant1/Area1  (1/1)  ← fully used
gufran        Viewer      1 max         (none — 0/1)  ← sees nothing
```

### 18.9 Rules Summary

| Rule | Detail |
|------|--------|
| Role defines the ceiling | `roles.max_area_assignments` sets the maximum per role |
| Per-user override wins | `users.max_area_override` takes precedence over role default if set |
| `NULL` = unlimited | Applicable to Admin and Engineer roles; never use 0 (that means "none") |
| Admin bypass | Admin role: area filter skipped entirely regardless of assignment count |
| Enforcement point | Backend `set_user_areas()` — never rely on UI-only enforcement |
| Live counter in UI | AreaAccessTab.tsx shows `(n / limit)` counter and disables checkboxes at limit |
| Union of areas | Multiple assignments produce UNION of tag sets via the JOIN-based filter |
| Downgrade protection | If role is changed to a lower quota (e.g., Engineer→Viewer), existing assignments above the new limit are **not auto-revoked** but a warning is shown to the Admin and future saves enforce the new limit |

---

## 19. Consolidated New Database Schema (Features 16–18)

```sql
-- ── Feature 16: License key table ─────────────────────────────────────────
CREATE TABLE historian_meta.license_keys (
    id               SERIAL PRIMARY KEY,
    key_hash         VARCHAR(128) NOT NULL UNIQUE,
    key_label        VARCHAR(200),
    max_users        INTEGER NOT NULL DEFAULT 5,
    max_areas        INTEGER,
    issued_to        VARCHAR(200),
    issued_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_until      TIMESTAMPTZ,
    is_active        BOOLEAN NOT NULL DEFAULT false,
    activated_by     INTEGER REFERENCES historian_meta.users(id),
    activated_at     TIMESTAMPTZ,
    notes            TEXT
);
CREATE UNIQUE INDEX idx_license_keys_active
    ON historian_meta.license_keys(is_active) WHERE is_active = true;

-- ── Feature 17: Active sessions table ─────────────────────────────────────
CREATE TABLE historian_meta.active_sessions (
    id              BIGSERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES historian_meta.users(id) ON DELETE CASCADE,
    session_token   VARCHAR(256) NOT NULL UNIQUE,
    jwt_jti         VARCHAR(128),
    ip_address      VARCHAR(45),
    user_agent      TEXT,
    device_name     VARCHAR(150),                   -- e.g. 'Control Room PC-3', 'Mobile-iOS'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    superseded_by   BIGINT REFERENCES historian_meta.active_sessions(id),
    revoked_reason  VARCHAR(50)
);
CREATE INDEX idx_active_sessions_user_id ON historian_meta.active_sessions(user_id);
CREATE INDEX idx_active_sessions_token   ON historian_meta.active_sessions(session_token);
CREATE INDEX idx_active_sessions_active  ON historian_meta.active_sessions(user_id, is_active)
    WHERE is_active = true;

-- ── Feature 18: Role area quota + per-user override ────────────────────────
ALTER TABLE historian_meta.roles
    ADD COLUMN IF NOT EXISTS max_area_assignments INTEGER DEFAULT NULL;

ALTER TABLE historian_meta.users
    ADD COLUMN IF NOT EXISTS max_area_override INTEGER DEFAULT NULL;

ALTER TABLE historian_meta.users
    ADD COLUMN IF NOT EXISTS allow_concurrent_sessions BOOLEAN NOT NULL DEFAULT false;

-- Set defaults for existing roles
UPDATE historian_meta.roles SET max_area_assignments = NULL  WHERE name = 'Admin';
UPDATE historian_meta.roles SET max_area_assignments = NULL  WHERE name = 'Engineer';
UPDATE historian_meta.roles SET max_area_assignments = 3     WHERE name = 'Operator';
UPDATE historian_meta.roles SET max_area_assignments = 1     WHERE name = 'Viewer';
```

---

## 20. Updated Implementation Order (Phases 1–6)

> **Last updated**: May 24, 2026 — Phases 1–5e fully implemented and audited. Phase 6 is next.

| Phase | Item | Status |
|-------|------|--------|
| 1 | DB migration — `plants_areas`, `user_area_assignments`, `access_audit_log` | ✅ Done |
| 2a | `area_access_service.py` — JOIN filter, 30s cache, invalidation, audit log | ✅ Done |
| 2b | 7 admin endpoints in `admin_controller.py` (`/plants-areas`, `/users/{id}/areas`, `/access-matrix`, `/license/*`) | ✅ Done |
| 2c | `container.py` registration of all new services | ✅ Done |
| 2d | `decorators.py` — `get_area_filter_sql_join()`, `get_current_user_area_access()` | ✅ Done |
| 3a | `AreaAccessTab.tsx` React component — checklist, quota counter | ✅ Done |
| 3b | `Admin.tsx` — Area Access tab + LicenseBanner wired | ✅ Done |
| 4a | Migration 027 — `license_keys`, `allow_concurrent_sessions`, `device_name`, JSONB audit columns | ✅ Done |
| 4b | `license_service.py` — Ed25519 verify, 366-day cap, mandatory expiry, 60s cache | ✅ Done |
| 4c | `session_service.py` — create/supersede/validate/end sessions, `end_all_user_sessions` | ✅ Done |
| 4d | `admin_controller.py` — `/license/status`, `/license/activate`, session endpoints | ✅ Done |
| 4e | `decorators.py` — `@token_required` checks session DB state, returns `SESSION_SUPERSEDED` | ✅ Done |
| 4f | Migration 028 + `set_user_areas()` — role `max_areas_per_user` quota enforcement | ✅ Done |
| 5a | `LicenseBanner.tsx` — status banner, activate/renew dialog, near-limit badge | ✅ Done |
| 5b | `api.ts` — `SESSION_SUPERSEDED` 401 interceptor; `login.tsx` — superseded toast | ✅ Done |
| 5c | `AreaAccessTab.tsx` — `max_areas_per_user` in matrix + `(n / max)` live counter | ✅ Done |
| 5d | `UserHeader.tsx` — area switcher dropdown, localStorage persistence, reload on switch | ✅ Done |
| 5e | `session_controller.py` + `end_all_user_sessions` method in `session_service.py` | ✅ Done |
| **6a** | **DB migration — `user_tag_access` table + `tag_uid` surrogate PK on `tag_master` + `tag_group` column** | ⏳ Pending |
| **6b** | **`tag_access_service.py`** — ALLOW / BLOCK resolver, 60s cache, audit log | ⏳ Pending |
| **6c** | **Extend `AuthorizationService.get_visible_tag_uids()`** with tag-level gate (three-tier filter) | ⏳ Pending |
| **6d** | **Frontend — Tag Access panel in Admin user edit** (group-level + individual tag assign) | ⏳ Pending |

### Known defects fixed during audit (May 24 2026)
- **Duplicate Flask route** — `/api/admin/plants-areas GET` was registered twice (old `rbac_service` stub conflicted with correct `area_access_service` version). Old stub removed.
- **Stray self-import** — `from services.session_service import SessionService` inside `end_all_user_sessions()` method body. Removed.

---

## 21. Multi-Plant, Multi-Area Access — Definitive Specification

### 21.1 What "Multi-Plant, Multi-Area" Means

A user can be assigned to **any combination of (plant, area) pairs — regardless of whether the plants are different**.

```
Valid assignment sets:

  [A] Single plant, single area
      Plant1 / Area1

  [B] Single plant, multiple areas
      Plant1 / Area1
      Plant1 / Area-2

  [C] Multiple plants, single area each
      Plant1 / Area1
      FTP-1  / POTLINE

  [D] Multiple plants, multiple areas
      Plant1         / Area1
      Plant1         / Area-2
      FTP-1          / POTLINE
      BlastFurnace   / Equipment

  [E] All areas (Admin only — bypass, not via assignment rows)
```

All four combinations [A]–[D] are stored identically: as rows in `user_area_assignments`.  
The backend JOIN filter automatically returns the UNION of all matching tags — no special code path per combination.

### 21.2 Data Returns — UNION Semantics

When a user has N area assignments, every data endpoint returns:

```
Visible tags = UNION(
    tags in Plant1/Area1,
    tags in Plant1/Area-2,
    tags in FTP-1/POTLINE
)
```

**No duplication** — `get_visible_tag_uids()` returns `list(set(visible_uids))`, so each `tag_uid` appears exactly once. Queries use `WHERE tag_uid = ANY(:uids)` — no `DISTINCT` needed or used.  
**No cross-product** — the JOIN through `user_area_assignments → plants_areas` inside `get_visible_tag_uids()` ensures only the exact (plant, area) pairs are matched (§8.2 security rule preserved).

### 21.3 Assignment Matrix — Concrete User Examples

```
User         Plant1/Area1  Plant1/Area-2  FTP-1/POTLINE  BlastFurnace/Equipment  Sees
──────────────────────────────────────────────────────────────────────────────────────
Mustafa      —             —              —               —                       ALL (admin bypass)
Jhon         ✅            ✅             ✅              ✅                      all 4 areas
Lokesh       ✅            ✗              ✗               ✗                       Plant1/Area1 only
Uzair        ✗             ✅             ✗               ✗                       Plant1/Area-2 only
sourav       ✗             ✗              ✅              ✗                       FTP-1/POTLINE only
shayaan      ✅            ✗              ✗               ✗                       Plant1/Area1 only
gufran       ✗             ✗              ✗               ✗                       nothing (no assignments)
```

`✅` = one row in `user_area_assignments` for that user+plant_area_id pair  
`✗`  = no row = no access to that area, period.

### 21.4 HMI Display When User Has Multiple Areas

The HMI handles multi-area users at two levels:

**Level 1 — Unified view (default for 2 areas)**
```
HMI Dashboard — Jhon (Engineer)
┌───────────────────────────────────────────────────────────┐
│  Active scope: [All My Areas ▼]                           │
│                                                           │
│  Plant1 / Area1     │  Plant1 / Area-2  │  FTP-1/POTLINE  │
│  ─────────────────────────────────────────────────────    │
│  Tag: TEMP_001  23°C │  Tag: FLOW_021  12m³/h             │
│  Tag: PRESS_003 4bar │  Tag: VALVE_01  OPEN               │
│  ...                 │  ...                               │
└───────────────────────────────────────────────────────────┘
All assigned areas shown side-by-side, grouped by area label.
```

**Level 2 — Focused area view (default for 3+ areas)**
```
HMI Dashboard — Jhon (Engineer)
┌───────────────────────────────────────────────────────────┐
│  Active scope: [Plant1 / Area1  ▼]                        │
│                 Plant1 / Area-2                           │
│                 FTP-1 / POTLINE                           │
│                 BlastFurnace / Equipment                  │
│                 ─────────────────                         │
│                 All My Areas  (Engineer/Admin only)       │
│                                                           │
│  Showing: Plant1 / Area1 tags only                        │
│  [Tag list for selected area]                             │
└───────────────────────────────────────────────────────────┘
Dropdown lets user switch focus. localStorage saves last selection.
```

**Threshold rule**: If `area_count <= 2` → default to unified view. If `area_count >= 3` → default to focused view.

### 21.5 Admin Assignment Panel — Multi-Plant Display

The `AreaAccessTab.tsx` groups checkboxes by plant to make multi-plant assignment clear:

```
Assign Areas to: Jhon (Engineer)   Role limit: Unlimited

  PLANT: Plant1
    ✅ Plant1 / Area1          (119 tags)  [active]
    ✅ Plant1 / Area-2         (10 tags)   [active]

  PLANT: FTP-1
    ✅ FTP-1 / POTLINE         (131 tags)  [active]

  PLANT: BlastFurnace
    ✅ BlastFurnace / Equipment (45 tags)  [active]

  PLANT: TestPlant
    ☐  TestPlant / Line1        (0 tags)  [inactive — grayed out]

  [Select All]  [Clear All]    Areas selected: 4 / Unlimited
  [Save Assignments]
```

Grouping by plant heading makes it immediately clear when a user spans multiple plants.

---

## 22. Tag-Level Access Control

### 22.1 Purpose

Plant/Area assignment is a **zone gate** — it controls which physical areas of the plant a user can see.  
Tag-level access is a **signal gate** — it controls which individual measurements within an area the user can see.

Both gates are independent and additive:
```
 User must pass BOTH to see a tag:
   Gate 1: user_area_assignments → area is in user's scope
   Gate 2: user_tag_access       → tag is in user's allow-list (if tag-level is configured)
```

If **no tag-level rules exist** for a user+area combination, all tags in that area are visible (default open).  
Tag-level rules only apply when explicitly configured by the Admin.

### 22.2 Use Cases

| Scenario | Without Tag-Level | With Tag-Level |
|----------|-------------------|----------------|
| Contractor access | Sees ALL 119 Plant1/Area1 tags | Sees only 15 allowed tags (e.g., only temperature sensors) |
| Trainee | Sees all tags in area | Sees read-only tags, high-voltage tags hidden |
| Shift supervisor | Same area as operator | Supervisor also sees KPI/aggregate tags operator cannot |
| Security policy | Flow meter values visible to all | Custody-transfer flow meters restricted to Finance role only |

### 22.3 Database Table

```sql
-- ── Step 0: Add immutable surrogate PK to tag_master (REQUIRED FIRST) ───
-- tag_id VARCHAR is a mutable display name — it cannot be a stable FK.
-- tag_uid is a BIGSERIAL assigned once at row creation and NEVER changes.
ALTER TABLE historian_meta.tag_master
    ADD COLUMN IF NOT EXISTS tag_uid BIGSERIAL;
ALTER TABLE historian_meta.tag_master
    ADD CONSTRAINT uq_tag_master_tag_uid UNIQUE (tag_uid);

-- ── historian_meta.user_tag_access ───────────────────────────────────────
CREATE TABLE historian_meta.user_tag_access (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES historian_meta.users(id) ON DELETE CASCADE,
    plant_area_id   INTEGER NOT NULL REFERENCES historian_meta.plants_areas(id) ON DELETE CASCADE,
    access_mode     VARCHAR(10) NOT NULL DEFAULT 'ALLOW',
                    -- 'ALLOW': only listed tag_uids are visible (allow-list)
                    -- 'BLOCK': all area tags visible EXCEPT listed tag_uids (block-list)
    tag_uid         BIGINT NOT NULL
                        REFERENCES historian_meta.tag_master(tag_uid) ON DELETE CASCADE,
    -- ⚠ NEVER use tag_id VARCHAR here — tag renames would silently orphan access rules
    granted_by      INTEGER REFERENCES historian_meta.users(id),
    granted_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes           TEXT,
    UNIQUE (user_id, plant_area_id, tag_uid)  -- one row per tag per user+area
    -- ⚠ No unique index on (user_id, plant_area_id, access_mode) — that cannot
    --   prevent ALLOW+BLOCK mixing. Mode consistency is enforced in set_tag_access().
);

CREATE INDEX idx_user_tag_access_user_area
    ON historian_meta.user_tag_access(user_id, plant_area_id);
CREATE INDEX idx_user_tag_access_tag_uid
    ON historian_meta.user_tag_access(tag_uid);

CREATE INDEX idx_user_tag_access_tag
    ON historian_meta.user_tag_access(tag_id);
```

### 22.4 Access Mode: ALLOW vs BLOCK

**ALLOW mode (allow-list — restrictive)**
```
Rows in user_tag_access for user=Lokesh, area=Plant1/Area1, mode=ALLOW:
  tag_id = 'TEMP_001'
  tag_id = 'TEMP_002'
  tag_id = 'PRESS_001'

Result: Lokesh sees ONLY those 3 tags in Plant1/Area1.
All other 116 tags in the area are invisible to him.
```

**BLOCK mode (block-list — permissive)**
```
Rows in user_tag_access for user=shayaan, area=Plant1/Area1, mode=BLOCK:
  tag_id = 'CUSTODY_FLOW_001'
  tag_id = 'CUSTODY_FLOW_002'

Result: shayaan sees ALL 119 Plant1/Area1 tags EXCEPT the 2 blocked ones.
```

**No rows (default)**
```
No rows in user_tag_access for user=Jhon, area=Plant1/Area1.

Result: Jhon sees ALL 119 Plant1/Area1 tags — no tag-level restriction.
Default = open (area assignment is the sole gate for this user).
```

> **Rule**: ALLOW and BLOCK cannot be mixed for the same `(user_id, plant_area_id)` combination.  
> All rows for a given user+area must have the same `access_mode`.  

> ⚠ **WHY A UNIQUE INDEX CANNOT ENFORCE THIS**:  
> `UNIQUE(user_id, plant_area_id, access_mode)` only prevents two *identical* rows.  
> It does NOT prevent one `ALLOW` row and one `BLOCK` row for the same user+area — those have different `access_mode` values, so the index lets both through.  
> **Do NOT create that index.** Enforcement is in `set_tag_access()` via full DELETE + INSERT.

```python
# set_tag_access() enforces mode consistency by design:
# Step 1: DELETE ALL existing rows for (user_id, plant_area_id)  ← wipes any old mode
# Step 2: INSERT new rows all with the same access_mode          ← only one mode survives
# Result:  physically impossible to have mixed modes after any set_tag_access() call
#
# Optional service-layer pre-check (defensive):
# existing_mode = SELECT DISTINCT access_mode FROM user_tag_access
#                 WHERE user_id=? AND plant_area_id=?
# if existing_mode and existing_mode != new_mode: raise ModeConflictError
# (This check is redundant given full-replace semantics, but adds clarity for reviewers.)
```

### 22.5 Tag Groups — Bulk Assignment

Assigning individual tag IDs for users with many tags is impractical.  
Add a `tag_group` column to `tag_master` so Admin can assign a whole group at once:

```sql
ALTER TABLE historian_meta.tag_master
    ADD COLUMN IF NOT EXISTS tag_group VARCHAR(100) DEFAULT NULL;
-- Examples: 'Temperature', 'Pressure', 'Flow', 'Vibration', 'KPI', 'Custody'

CREATE INDEX idx_tag_master_tag_group ON historian_meta.tag_master(tag_group);
```

Admin UI supports **group-level assignment** in addition to individual tag selection:

```
Tag Access for: Lokesh (Operator) — Plant1/Area1
Mode: ALLOW  ← dropdown: ALLOW / BLOCK / NONE (no restriction)

  Assign by group:
    ✅ Temperature   (23 tags)  [select all in group]
    ✅ Pressure      (12 tags)  [select all in group]
    ☐  Flow          (18 tags)
    ☐  Vibration     (31 tags)
    ☐  KPI           (5 tags)
    ☐  Custody       (2 tags)
    ☐  (ungrouped)   (28 tags)

  Or select individual tags:
    ✅ TEMP_001   Temperature sensor 1
    ✅ TEMP_002   Temperature sensor 2
    ☐  FLOW_001   Flow meter 1
    ...

  Tags in allow-list: 35 / 119
  [Save Tag Access]
```

### 22.6 SQL Filter — Three-Tier Query Pattern

The complete data query applying all three access tiers:

The three-tier filter is **not executed as a single inline JOIN** at query time. That approach would produce a heavy 3-table join on every historian, alarm, and analytics query — dangerous at scale.

**Correct pattern**: Resolve the tag set once via `AuthorizationService.get_visible_tag_uids()`, then use a simple array filter in all queries.

```python
# ── In every data endpoint ─────────────────────────────────────────────────
# Tier 1 (Role) — checked by decorator
authz.assert_can_access_module(g.user_id, 'hmi', 'view')

# Tiers 2 + 3 (Area + Tag) — resolved once, cached 60s
visible_uids = authz.get_visible_tag_uids(g.user_id)
#   None  → admin bypass (no filter)
#   []    → no areas/tags assigned
#   [..] → immutable tag_uid list, produced by area+tag JOIN (runs once, not per request)

if visible_uids is None:
    where, params = "WHERE tm.enabled = true", {}
elif not visible_uids:
    return jsonify({'data': [], 'warning': 'No areas assigned to your account'}), 200
else:
    where, params = "WHERE tm.tag_uid = ANY(%(uids)s) AND tm.enabled = true", {'uids': visible_uids}
```

```sql
-- Resulting query for tag list (no runtime JOIN needed):
SELECT tm.tag_uid, tm.tag_id, tm.tag_name, tm.plant, tm.area, tm.tag_group
FROM historian_meta.tag_master tm
WHERE tm.tag_uid = ANY(:visible_uids)
  AND tm.enabled = true;
-- Uses btree index on tag_uid. No multi-table join. No DISTINCT needed.

-- Historian trend query:
SELECT timestamp, value, quality
FROM historian_raw.historian_timeseries
WHERE tag_uid = ANY(:visible_uids)
  AND timestamp BETWEEN :from AND :to
ORDER BY tag_uid, timestamp DESC;
-- Uses composite index (tag_uid, timestamp DESC). Fast at 100M+ rows.
```

> **When is the area+tag JOIN actually run?**  
> Inside `get_visible_tag_uids()` — once per 60 seconds per user, in `AuthorizationService`.  
> The JOIN cost is paid at resolution time, not at query time.  
> All historian, alarm, analytics, and HMI queries receive a pre-resolved `int[]` and use `= ANY()`.

> **Why no DISTINCT?**  
> The resolved `visible_uids` list is deduplicated (`list(set(...))`) inside `get_visible_tag_uids()`.  
> Queries on `historian_timeseries` filter by `tag_uid` — no duplicate rows possible.  
> `DISTINCT` on large historian tables is expensive and hides data-model problems. Avoid it.

### 22.7 Service Layer — Tag Access Resolver

```python
# services/tag_access_service.py  (NEW)

class TagAccessService:
    """
    Resolves tag-level access for a user within a specific plant/area.
    Works in conjunction with AreaAccessService (area gate must pass first).
    Cache: 60s TTL per (user_id, plant_area_id).  Invalidated on admin save.
    """

    def get_tag_access_mode(self, user_id: int, plant_area_id: int) -> str:
        """
        Returns: 'OPEN'  → no tag restriction (default)
                 'ALLOW' → only listed tags visible
                 'BLOCK' → all tags except listed visible
        """

    def get_allowed_tag_uids(self, user_id: int, plant_area_id: int) -> list[int] | None:
        """
        Returns None      → OPEN (no restriction — all area tags visible)
                list[int] → tag_uids in allow-list (ALLOW) or block-list (BLOCK)
        Uses immutable tag_uid — never tag_id VARCHAR.
        """

    def set_tag_access(
        self,
        user_id: int,
        plant_area_id: int,
        access_mode: str,           # 'ALLOW' | 'BLOCK' | 'OPEN'
        tag_uids: list[int],        # immutable tag_uid values — NEVER tag_id strings
        admin_user_id: int,
        admin_ip: str = None
    ) -> None:
        """
        Full replace — DELETE all existing rows for (user_id, plant_area_id),
        then INSERT new rows all with the same access_mode.
        This is the ONLY enforcement mechanism for mode consistency.
        No unique index on access_mode column — see §22.4 for why that approach is wrong.
        Writes JSONB old_state/new_state to access_audit_log.
        """
        # Before INSERT, writes audit row:
        # old_state = {"mode": "ALLOW", "tag_uids": [...], "area": "Plant1/Area1"}
        # new_state = {"mode": "BLOCK", "tag_uids": [...], "area": "Plant1/Area1"}

    def get_tag_access_summary(self, user_id: int) -> list[dict]:
        """
        Returns per-area summary:
        [
          { plant_area_id: 1, display_name: 'Plant1/Area1', mode: 'ALLOW', tag_count: 35 },
          { plant_area_id: 5, display_name: 'FTP-1/POTLINE', mode: 'OPEN',  tag_count: 0 },
        ]
        """
```

### 22.8 Admin Endpoints for Tag Access

```
GET  /api/admin/users/{id}/tag-access
     → Returns per-area tag access summary for the user
     → Response: [ { plant_area_id, display_name, mode, tag_ids, tag_count } ]

PUT  /api/admin/users/{id}/tag-access/{plant_area_id}
     body: { "access_mode": "ALLOW", "tag_ids": ["TEMP_001", "PRESS_001"] }
     → Full replace for that user+area combination
     → Writes to access_audit_log with action = 'TAG_ACCESS_UPDATED'
     → Invalidates tag access cache for (user_id, plant_area_id)

DELETE /api/admin/users/{id}/tag-access/{plant_area_id}
     → Removes ALL tag-level rules for that user+area (resets to OPEN)
     → Logs to access_audit_log with action = 'TAG_ACCESS_CLEARED'

GET  /api/admin/tags?plant_area_id={id}
     → Returns all tags in a plant/area with their tag_group
     → Used to populate the tag assignment checklist
```

### 22.9 Decision Tree — Three-Tier Access Check

```
User makes request to any data endpoint
         │
         ▼
[ TIER 1 — ROLE CHECK ]
Is user.role.is_admin?
    YES → skip Tier 2 + Tier 3 → return ALL data
    NO  ↓
Does role have can_view for this module?
    NO  → 403 Forbidden
    YES ↓
         ▼
[ TIER 2 — AREA CHECK ]
Get user's area assignments from user_area_assignments (30s cache)
    EMPTY → return 200 empty + "No areas assigned" banner
    HAS AREAS ↓
Apply JOIN filter → tag_master rows matching user's (plant, area) pairs
    RESULT is the "area-visible" tag set
         ↓
         ▼
[ TIER 3 — TAG CHECK ]
For each area in user's scope:
    Get tag access mode for (user_id, plant_area_id) (60s cache)
    OPEN  → all area tags pass through (no filter)
    ALLOW → keep only tags in allow-list
    BLOCK → remove tags in block-list
    RESULT is the "tag-visible" set within that area
         ↓
         ▼
UNION all per-area results → return to caller
```

### 22.10 Tag Access Rules Summary

| Rule | Detail |
|------|--------|
| Default | No `user_tag_access` rows = OPEN (all area tags visible) |
| ALLOW mode | Only listed tags visible — all others hidden |
| BLOCK mode | All tags visible EXCEPT listed ones |
| ALLOW + BLOCK mixed | ❌ Forbidden for same user+area — enforced at DB + service layer |
| Admin bypass | Admin role skips tag-level check entirely |
| Inactive tags | `tag_master.enabled = false` always excluded regardless of tag access rules |
| Tag group assign | Admin can bulk-select all tags in a group (Temperature, Pressure, etc.) |
| Cache TTL | 60s per (user_id, plant_area_id) — invalidated immediately on admin save |
| Audit | Every `set_tag_access()` call writes to `access_audit_log` with old/new tag lists |
| Area gate first | Tag-level check only runs if the area gate already passed — no tag leakage |
| Cross-area isolation | Tag rules for Plant1/Area1 have zero effect on FTP-1/POTLINE tags |

---

## 23. Complete Three-Tier Model — Summary Table

| Gate | Table | Controls | Default if no rows | Admin bypass |
|------|-------|----------|--------------------|--------------|
| **Tier 1 — Role** | `roles` + `role_module_permissions` | Which modules/actions | Deny (no role = no access) | `is_admin = true` skips all |
| **Tier 2 — Area** | `user_area_assignments` + `plants_areas` | Which plant+area zones | Deny (0 areas = 0 data) | `is_admin = true` skips all |
| **Tier 3 — Tag** | `user_tag_access` | Which specific tags | Allow (no rows = all area tags) | `is_admin = true` skips all |

### Assignment Possibilities Matrix

```
                       Tag-Level
                  OPEN    ALLOW   BLOCK
              ┌────────┬───────┬───────┐
  Area  SINGLE│ All    │ N     │ All   │
              │ tags   │ tags  │ except│
              │        │       │ N     │
              ├────────┼───────┼───────┤
  Area MULTI  │ Union  │ Union │ Union │
              │ of all │ of    │ of    │
              │ area   │ ALLOW │ ~BLOCK│
              │ tags   │ per   │ per   │
              │        │ area  │ area  │
              └────────┴───────┴───────┘

Each cell shows what the user sees.
ALLOW and BLOCK are configured INDEPENDENTLY per (user, plant_area_id) pair.
User can have ALLOW in Plant1/Area1 and BLOCK in FTP-1/POTLINE simultaneously.
```

### Concrete Final Example

```
User: Lokesh    Role: Operator    Role limit: 3 areas

Area assignments:
  Row 1: Plant1 / Area1     (119 tags total)
  Row 2: FTP-1  / POTLINE   (131 tags total)

Tag-level rules:
  Plant1/Area1  → ALLOW [TEMP_001, TEMP_002, PRESS_001]   → sees 3 tags
  FTP-1/POTLINE → OPEN  (no rules)                        → sees all 131 tags

Lokesh's final visible set:
  3 tags from Plant1/Area1   (tag-level filtered)
  131 tags from FTP-1/POTLINE (no tag filter)
  ─────────────────────────
  134 tags total

Lokesh cannot see:
  ✗ Plant1/Area1 — the other 116 tags (blocked by ALLOW list)
  ✗ Plant1/Area-2 — not in area assignments
  ✗ BlastFurnace/Equipment — not in area assignments
```

---

## 24. Architecture Audit — 15-Point Review & Fixes

> **Audit Date**: May 24, 2026. All 15 points reviewed against current design.
> Status: 🔴 CRITICAL fix required before implementation · 🟠 HIGH fix in next phase · 🟡 FUTURE scheduled

---

### Audit Item 1 🔴 — Immutable Tag Primary Key (`tag_uid`)

**Problem**: `user_tag_access.tag_id VARCHAR(200)` uses the mutable display name as a foreign key.
A tag rename or historian migration silently orphans all access rules for that tag.

**Fix**: Add a `BIGSERIAL` surrogate PK to `tag_master` and reference it everywhere.

```sql
-- Add surrogate PK to tag_master (if not already present)
ALTER TABLE historian_meta.tag_master
    ADD COLUMN IF NOT EXISTS tag_uid BIGSERIAL;

ALTER TABLE historian_meta.tag_master
    ADD CONSTRAINT uq_tag_master_tag_uid UNIQUE (tag_uid);

-- Recreate user_tag_access referencing tag_uid instead of tag_id
CREATE TABLE historian_meta.user_tag_access (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES historian_meta.users(id) ON DELETE CASCADE,
    plant_area_id   INTEGER NOT NULL REFERENCES historian_meta.plants_areas(id) ON DELETE CASCADE,
    access_mode     VARCHAR(10) NOT NULL DEFAULT 'ALLOW', -- 'ALLOW' | 'BLOCK'
    tag_uid         BIGINT NOT NULL REFERENCES historian_meta.tag_master(tag_uid) ON DELETE CASCADE,
    granted_by      INTEGER REFERENCES historian_meta.users(id),
    granted_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes           TEXT,
    UNIQUE (user_id, plant_area_id, tag_uid)
);

CREATE INDEX idx_user_tag_access_user_area ON historian_meta.user_tag_access(user_id, plant_area_id);
CREATE INDEX idx_user_tag_access_tag_uid   ON historian_meta.user_tag_access(tag_uid);
```

**Rule**: All internal service code and SQL must reference `tag_uid`. `tag_id` (the human name) is for display only, never used as a FK.
**Impact**: Replaces `tag_id VARCHAR(200)` in §22.3. The `tag_uid` survives renames, historian migrations, and table rebuilds.

---

### Audit Item 2 🔴 — ALLOW/BLOCK Mode Consistency: Service-Layer Enforcement

**Problem**: A `UNIQUE INDEX` on `(user_id, plant_area_id, access_mode)` does NOT prevent mixing modes. Inserting one ALLOW row and one BLOCK row for the same user+area succeeds because they have different `access_mode` values — the index only blocks *identical* rows.

**Fix**: Remove the incorrect index. Enforce via **full DELETE + INSERT** in the service layer.

```sql
-- Do NOT create idx_user_tag_access_mode_consistency — it is logically wrong.
-- The correct enforcement is in set_tag_access() below.
```

```python
# services/tag_access_service.py — set_tag_access() CORRECTED

def set_tag_access(self, user_id, plant_area_id, access_mode, tag_uids,
                   admin_user_id, admin_ip=None):
    """
    Full replace for (user_id, plant_area_id).
    DELETE all existing rows first, then INSERT only the new mode's rows.
    This physically prevents mixed modes — only the latest call's mode survives.
    """
    if access_mode not in ('ALLOW', 'BLOCK', 'OPEN'):
        raise ValueError(f"Invalid access_mode: {access_mode}")

    with self._db.cursor() as cur:
        # Step 1: Always delete ALL existing rows for this user+area
        cur.execute(
            "DELETE FROM historian_meta.user_tag_access "
            "WHERE user_id = %s AND plant_area_id = %s",
            (user_id, plant_area_id)
        )
        # Step 2: OPEN mode = no rows = default open (done)
        if access_mode != 'OPEN' and tag_uids:
            # Validate tag_uids belong to this plant_area_id
            cur.execute("""
                SELECT tm.tag_uid FROM historian_meta.tag_master tm
                JOIN historian_meta.plants_areas pa
                  ON pa.plant = tm.plant AND pa.area = tm.area
                WHERE pa.id = %s AND tm.tag_uid = ANY(%s)
            """, (plant_area_id, tag_uids))
            valid_uids = {r['tag_uid'] for r in cur.fetchall()}
            invalid = set(tag_uids) - valid_uids
            if invalid:
                raise ValueError(
                    f"tag_uids {invalid} do not belong to plant_area_id={plant_area_id}"
                )
            args = [
                (user_id, plant_area_id, access_mode, uid, admin_user_id)
                for uid in tag_uids
            ]
            cur.executemany(
                "INSERT INTO historian_meta.user_tag_access "
                "(user_id, plant_area_id, access_mode, tag_uid, granted_by) "
                "VALUES (%s,%s,%s,%s,%s)",
                args
            )

    self._invalidate_cache(user_id, plant_area_id)
    self._audit_log(admin_user_id, user_id,
                    'TAG_ACCESS_UPDATED' if access_mode != 'OPEN' else 'TAG_ACCESS_CLEARED',
                    admin_ip, notes=f"mode={access_mode} tags={len(tag_uids)}")
```

---

### Audit Item 3 🔴 — Resolved Tag-Set Cache (Prevent JOIN Explosion)

**Problem**: A `LEFT JOIN user_tag_access` on every historian, alarm, analytics, and polling query creates a 3-table join that degrades severely at 50k+ tags.

**Fix**: Resolve the user's complete visible tag set **once per 60 seconds**, cache it, and use `tag_uid = ANY(:ids)` in all data queries.

```python
# services/authorization_service.py

def get_visible_tag_uids(self, user_id: int) -> list[int] | None:
    """
    None  → Admin bypass (do not filter at all)
    []    → No areas assigned (return empty data set)
    [..] → Resolved list of tag_uids the user may see
    Cache: 60s TTL. Invalidated immediately on any area or tag-access change.
    """
    cached = self._tag_uid_cache.get(user_id)
    if cached is not None:
        return None if cached is _BYPASS else cached

    areas = self._area_service.get_user_area_access(user_id)  # None = admin
    if areas is None:
        self._tag_uid_cache.set(user_id, _BYPASS, ttl=60)
        return None

    if not areas:
        self._tag_uid_cache.set(user_id, [], ttl=60)
        return []

    visible_uids = []
    for area in areas:
        plant_area_id = area['plant_area_id']
        mode = self._tag_service.get_tag_access_mode(user_id, plant_area_id)

        with self._db.cursor() as cur:
            if mode == 'OPEN':
                cur.execute("""
                    SELECT tm.tag_uid FROM historian_meta.tag_master tm
                    JOIN historian_meta.plants_areas pa
                      ON pa.plant=tm.plant AND pa.area=tm.area AND pa.is_active=true
                    WHERE pa.id=%s AND tm.enabled=true
                """, (plant_area_id,))
            elif mode == 'ALLOW':
                cur.execute("""
                    SELECT tag_uid FROM historian_meta.user_tag_access
                    WHERE user_id=%s AND plant_area_id=%s AND access_mode='ALLOW'
                """, (user_id, plant_area_id))
            else:  # BLOCK
                cur.execute("""
                    SELECT tm.tag_uid FROM historian_meta.tag_master tm
                    JOIN historian_meta.plants_areas pa
                      ON pa.plant=tm.plant AND pa.area=tm.area AND pa.is_active=true
                    WHERE pa.id=%s AND tm.enabled=true
                      AND tm.tag_uid NOT IN (
                          SELECT tag_uid FROM historian_meta.user_tag_access
                          WHERE user_id=%s AND plant_area_id=%s AND access_mode='BLOCK'
                      )
                """, (plant_area_id, user_id, plant_area_id))
            visible_uids += [r['tag_uid'] for r in cur.fetchall()]

    result = list(set(visible_uids))
    self._tag_uid_cache.set(user_id, result, ttl=60)
    return result
```

**Data query pattern — ALL endpoints use this single pattern**:
```python
visible_uids = authz.get_visible_tag_uids(user_id)

if visible_uids is None:          # admin bypass
    where = "WHERE tm.enabled = true"
    params = {}
elif len(visible_uids) == 0:      # no areas assigned
    return jsonify({'data': [], 'warning': 'No areas assigned'}), 200
else:
    where = "WHERE tm.tag_uid = ANY(%(uids)s) AND tm.enabled = true"
    params = {'uids': visible_uids}
```

**Performance**: `tag_uid = ANY(array)` uses the btree index on `tag_uid`. No multi-table join at query time. The resolution cost (JOIN) is paid once per 60s, not per request.

---

### Audit Item 4 🔴 — Historian Composite Indexes

**Problem**: `historian_raw.historian_timeseries` has no composite index on `(tag_uid, timestamp)`. Trend and report queries will full-scan the table.

**Fix**:
```sql
-- Add tag_uid column to historian tables (backfill from tag_id)
ALTER TABLE historian_raw.historian_timeseries
    ADD COLUMN IF NOT EXISTS tag_uid BIGINT
        REFERENCES historian_meta.tag_master(tag_uid);

UPDATE historian_raw.historian_timeseries ht
SET tag_uid = tm.tag_uid
FROM historian_meta.tag_master tm
WHERE ht.tag_id = tm.tag_id AND ht.tag_uid IS NULL;

-- Primary composite index for trend/report queries
CREATE INDEX IF NOT EXISTS idx_hist_ts_tag_uid_time
    ON historian_raw.historian_timeseries(tag_uid, timestamp DESC);

-- Covering index includes value + quality — avoids heap fetch for trend queries
CREATE INDEX IF NOT EXISTS idx_hist_ts_covering
    ON historian_raw.historian_timeseries(tag_uid, timestamp DESC)
    INCLUDE (value, quality);

-- Same for PLC historian table
CREATE INDEX IF NOT EXISTS idx_plc_ts_tag_uid_time
    ON plc_gateway.plc_timeseries(tag_uid, timestamp DESC);
```

**Rule**: All historian trend, report, and alarm queries must filter by `tag_uid`, never by `tag_id` VARCHAR.

---

### Audit Item 5 🟠 — Active Sessions: Add `device_name`

```sql
ALTER TABLE historian_meta.active_sessions
    ADD COLUMN IF NOT EXISTS device_name VARCHAR(200) DEFAULT NULL;
```

Derived server-side on login from the `User-Agent` header. Admin session panel shows `device_name` instead of the raw `user_agent` string:

```
Admin → Users → Lokesh → Active Session
┌────────────────────────────────────────────────────────┐
│  Device:      Chrome / Windows 11                     │
│  IP:          192.168.1.10                            │
│  Logged in:   2026-05-24 08:14                        │
│  Last seen:   2 min ago                               │
│  [Force Logout]                                        │
└────────────────────────────────────────────────────────┘
```

---

### Audit Item 6 🟠 — Session Revocation: 10s Lag — Documented + Immediate Flush

> **Documented Behaviour**: Admin force-revoke takes effect within **at most 10 seconds** (session cache TTL).
> For immediate effect, the `force_revoke_sessions()` method flushes the in-memory cache entry directly.

```python
def force_revoke_sessions(self, user_id: int, admin_user_id: int, admin_ip: str = None):
    with self._db.cursor() as cur:
        cur.execute("""
            UPDATE historian_meta.active_sessions
            SET is_active=false, revoked_reason='ADMIN_REVOKE'
            WHERE user_id=%s AND is_active=true
            RETURNING session_token
        """, (user_id,))
        revoked_tokens = [r['session_token'] for r in cur.fetchall()]

    # ── Immediate cache flush — no 10s wait ─────────────────────
    for token in revoked_tokens:
        self._session_cache.delete(token)

    self._audit('SESSION_REVOKED', admin_user_id, user_id, admin_ip)
```

---

### Audit Item 7 🟡 — Admin Hierarchy Scaffold (SuperAdmin vs PlantAdmin)

**Current**: `is_admin = true` = global god mode. Not scalable for multi-site.
**Action now**: Add the column scaffold but do not implement logic yet.

```sql
ALTER TABLE historian_meta.roles
    ADD COLUMN IF NOT EXISTS admin_scope VARCHAR(20) DEFAULT 'NONE';
    -- 'GLOBAL' → SuperAdmin (all plants)
    -- 'PLANT'  → PlantAdmin (assigned plants only — future)
    -- 'NONE'   → Non-admin role

UPDATE historian_meta.roles SET admin_scope = 'GLOBAL' WHERE is_admin = true;
UPDATE historian_meta.roles SET admin_scope = 'NONE'   WHERE is_admin = false;
```

**Future role model**:
| Role | `admin_scope` | Data scope |
|------|---------------|------------|
| SuperAdmin | `GLOBAL` | All plants — bypass |
| PlantAdmin | `PLANT` | Assigned plants only |
| Engineer | `NONE` | Assigned areas |
| Operator | `NONE` | Assigned areas |
| Viewer | `NONE` | Assigned areas |

**Rule now**: All admin bypass checks must route through `AuthorizationService.is_admin(user_id)`, not hardcoded `role.is_admin`. This ensures the hierarchy can be enforced later without touching endpoint code.

---

### Audit Item 8 🟠 — Signed License Payload (ECDSA)

**Problem**: Plain `max_users INTEGER` in DB can be tampered by anyone with DB write access.

**Fix**: License key is a JWT signed with vendor's ECDSA private key. Vendor public key is embedded in the application binary.

```python
# services/license_service.py

VENDOR_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
... (ECDSA P-256 public key embedded at build time) ...
-----END PUBLIC KEY-----"""

# License payload (signed by vendor):
# { "customer": "Plant1", "max_users": 10, "valid_until": "2027-12-31",
#   "features": ["historian","plc_gateway"], "iat": 1716537600 }

def activate_license(self, raw_key: str, admin_user_id: int) -> dict:
    try:
        payload = jwt.decode(raw_key, VENDOR_PUBLIC_KEY,
                             algorithms=['ES256'],
                             options={'require': ['max_users', 'valid_until', 'customer']})
    except jwt.InvalidTokenError as e:
        raise LicenseInvalidError(f"License signature invalid: {e}")

    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    with self._db.cursor() as cur:
        cur.execute("UPDATE historian_meta.license_keys SET is_active=false WHERE is_active=true")
        cur.execute("""
            INSERT INTO historian_meta.license_keys
            (key_hash, key_label, max_users, issued_to, valid_until, is_active, activated_by, activated_at)
            VALUES (%s, %s, %s, %s, %s, true, %s, NOW())
        """, (key_hash, payload['customer'], payload['max_users'],
              payload.get('customer'), payload.get('valid_until'), admin_user_id))

    return {'max_users': payload['max_users'], 'valid_until': payload.get('valid_until')}
```

**Tamper detection**: A background job periodically re-hashes the stored `key_hash` and verifies it matches the active key record. Direct DB edit of `max_users` is detected on next validation cycle.

---

### Audit Item 9 🔴 — Centralized `AuthorizationService` (Central Policy Engine)

**Problem**: Scattered `area_filter` and `role_permission` checks across endpoints. One missed endpoint = data leak. This is the single most common failure mode in enterprise access control systems.

**Fix**: `AuthorizationService` is the **only** class that makes access decisions. No endpoint constructs its own filter.

```python
# services/authorization_service.py

class AuthorizationService:
    """
    Central policy engine. ALL data endpoints call this. No exceptions.
    """

    def can_access_module(self, user_id: int, module: str, action: str = 'view') -> bool:
        """Tier 1: role_module_permissions check."""

    def get_visible_tag_uids(self, user_id: int) -> list[int] | None:
        """Tiers 2+3: resolved tag set. None=bypass. []=no access."""

    def can_access_tag(self, user_id: int, tag_uid: int) -> bool:
        uids = self.get_visible_tag_uids(user_id)
        return True if uids is None else tag_uid in uids

    def assert_can_access_module(self, user_id: int, module: str, action: str = 'view'):
        if not self.can_access_module(user_id, module, action):
            abort(403, description=f"Role does not permit {action} on {module}")

    def is_admin(self, user_id: int) -> bool:
        """Single point for admin bypass check. Supports future PlantAdmin hierarchy."""

    def invalidate_user_cache(self, user_id: int):
        """Called by ALL admin write operations. Clears area + tag-uid + session caches."""
        self._area_service.invalidate_cache(user_id)
        self._tag_uid_cache.delete(user_id)
```

**Architecture enforcement**: No PR is accepted that constructs a tag or area filter outside `AuthorizationService`.

---

### Audit Item 10 🟠 — Audit Log: Capture Role Changes

```sql
ALTER TABLE historian_meta.access_audit_log
    ADD COLUMN IF NOT EXISTS old_role_id   INTEGER REFERENCES historian_meta.roles(id),
    ADD COLUMN IF NOT EXISTS new_role_id   INTEGER REFERENCES historian_meta.roles(id),
    ADD COLUMN IF NOT EXISTS old_role_name VARCHAR(100),
    ADD COLUMN IF NOT EXISTS new_role_name VARCHAR(100);

-- Extended action values
-- action IN ('ASSIGN','REVOKE','REPLACE','TAG_ACCESS_UPDATED','TAG_ACCESS_CLEARED',
--            'ROLE_CHANGED','USER_CREATED','USER_DEACTIVATED','USER_ACTIVATED','SESSION_REVOKED')
```

**Rule**: Every call to `update_user_role()` must write a `ROLE_CHANGED` audit row with `old_role_id`, `new_role_id`, and call `authz.invalidate_user_cache(user_id)` — role change affects module permissions cache.

---

### Audit Item 11 🔴 — Backend Must Reject Unauthorized `scope=all`

**Rule**: Backend silently downgrades `scope=all` to `assigned` for roles that do not qualify. Never returns 403 (prevents enumeration). Never trusts the frontend's role-based UI restriction.

```python
@tag_bp.route('/api/tags')
@require_auth
def get_tags():
    scope = request.args.get('scope', 'assigned')

    if scope == 'all':
        user_role = get_user_role(g.user_id)
        # Only true Admin bypass; Engineer still uses their resolved tag set
        if not authz.is_admin(g.user_id):
            scope = 'assigned'  # silent downgrade — no error exposed

    visible_uids = authz.get_visible_tag_uids(g.user_id)
    # ... proceed
```

---

### Audit Item 12 🟡 — Historian Partitioning via TimescaleDB

TimescaleDB hypertable chunking already provides partitioning. Tune it:

```sql
-- Set monthly chunk interval (optimal for 100M+ rows)
SELECT set_chunk_time_interval(
    'historian_raw.historian_timeseries', INTERVAL '1 month'
);

-- Enable compression on chunks older than 3 months
ALTER TABLE historian_raw.historian_timeseries SET (
    timescaledb.compress,
    timescaledb.compress_orderby   = 'timestamp DESC',
    timescaledb.compress_segmentby = 'tag_uid'
);
SELECT add_compression_policy(
    'historian_raw.historian_timeseries', INTERVAL '3 months'
);
```

With `(tag_uid, timestamp DESC)` composite index + TimescaleDB chunk exclusion, queries on a specific tag's recent history remain fast at 1B+ rows.

---

### Audit Item 13 ✅ — New Plants/Areas OFF by Default

**Status**: Already correct. No change needed.

New tags with previously unseen plant/area values are invisible to all non-admin users until:
1. Admin runs "Sync from Tags" (adds row to `plants_areas`)
2. Admin explicitly assigns the new area to users

The JOIN filter (`AND pa.is_active = true`, `AND uaa.revoked_at IS NULL`) enforces this automatically.
**Preserve this behaviour in all future refactors. Do not auto-assign new areas to any user.**

---

### Audit Item 14 🟡 — `tag_master.plant_area_id` FK (Future Migration)

```sql
-- Phase 8: after tag_uid is stable, migrate tag_master to use FK
ALTER TABLE historian_meta.tag_master
    ADD COLUMN IF NOT EXISTS plant_area_id INTEGER REFERENCES historian_meta.plants_areas(id);

-- Backfill
UPDATE historian_meta.tag_master tm
SET plant_area_id = pa.id
FROM historian_meta.plants_areas pa
WHERE pa.plant = tm.plant AND pa.area = tm.area;

CREATE INDEX IF NOT EXISTS idx_tag_master_plant_area_id
    ON historian_meta.tag_master(plant_area_id);

-- After validation, change JOINs from:
--   JOIN plants_areas pa ON pa.plant=tm.plant AND pa.area=tm.area
-- to:
--   JOIN plants_areas pa ON pa.id = tm.plant_area_id
-- This eliminates text-matching fragility entirely.
```

---

### Audit Item 15 🔴 — `AuthorizationService` as Full Policy Engine

This is the architectural keystone for the entire system.

```
                ┌──────────────────────────────────────────┐
                │          AuthorizationService            │
                │  (single source of truth for all access) │
                └────────┬─────────────────────────────────┘
                         │ delegates to
        ┌────────────────┼──────────────────┐
        ▼                ▼                  ▼
RolePermissionService  AreaAccessService  TagAccessService
(Tier 1: modules)      (Tier 2: zones)    (Tier 3: tags)
        │                │                  │
        └────────────────┴──────────────────┘
                         │ all backed by
               PostgreSQL historian_meta
               + per-service in-memory TTL cache
```

```python
# container.py (final state)
self.role_permission_service = RolePermissionService(self.config['database'])
self.area_access_service     = AreaAccessService(self.config['database'])      # ✅ done
self.tag_access_service      = TagAccessService(self.config['database'])
self.authorization_service   = AuthorizationService(
    role_service = self.role_permission_service,
    area_service = self.area_access_service,
    tag_service  = self.tag_access_service,
    db_config    = self.config['database']
)
```

| `AuthorizationService` method | Replaces |
|-------------------------------|---------|
| `can_access_module(user_id, module, action)` | Scattered `role_module_permissions` queries |
| `get_visible_tag_uids(user_id)` | All tag JOIN filters across all endpoints |
| `can_access_tag(user_id, tag_uid)` | Single-tag access checks |
| `assert_can_access_module(...)` | Decorator / guard at endpoint entry |
| `is_admin(user_id)` | All `role.is_admin` checks (future hierarchy safe) |
| `invalidate_user_cache(user_id)` | All cache invalidation triggered by admin changes |

---

## 25. Architecture Audit — Priority Summary

| Priority | # | Issue | Fix Applied | Impl Phase |
|----------|---|-------|-------------|------------|
| 🔴 CRITICAL | 2 | ALLOW/BLOCK index wrong — doesn't enforce consistency | Service-layer full DELETE+INSERT atomicity | 6b |
| 🔴 CRITICAL | 1 | `tag_id` VARCHAR as FK — rename breaks permissions | `tag_uid BIGSERIAL` surrogate PK on `tag_master` | 6a |
| 🔴 CRITICAL | 3 | Tag-level JOIN explosion at 50k+ tags | `get_visible_tag_uids()` cache + `ANY(array)` | 6b |
| 🔴 CRITICAL | 4 | Missing historian composite indexes | `(tag_uid, timestamp DESC)` on timeseries tables | 6a |
| 🔴 CRITICAL | 9 | Scattered filter logic — one leak = breach | `AuthorizationService` central policy engine | 6b |
| 🔴 CRITICAL | 11 | `scope=all` trusted from frontend | Backend silent-downgrade for unauthorized | 4e |
| 🔴 CRITICAL | 15 | No central policy engine | `AuthorizationService` + sub-services | 6b |
| 🟠 HIGH | 5 | Sessions lack `device_name` | `device_name VARCHAR(200)` column | 4a |
| 🟠 HIGH | 6 | Forced revoke 10s lag undocumented | Documented + immediate cache flush | 4c |
| 🟠 HIGH | 8 | License key tamper-possible | ECDSA-signed JWT, verify on activation | 4b |
| 🟠 HIGH | 10 | Role changes not audited | `old/new_role_id` in `access_audit_log` | 4d |
| 🟡 FUTURE | 7 | Admin = global god mode (no PlantAdmin) | `roles.admin_scope` scaffold added | 7 |
| 🟡 FUTURE | 12 | Historian partitioning | TimescaleDB chunk interval + compression | 7 |
| 🟡 FUTURE | 13 | New areas OFF by default | ✅ Already correct — preserve | N/A |
| 🟡 FUTURE | 14 | `tag_master` text plant/area → FK | `tag_master.plant_area_id` after tag_uid stable | 8 |
| 🔴 CRITICAL | 16 | `max_users` read directly from DB (tamper) | ECDSA `signed_payload` — `_get_verified_max_users()` | 4b |
| 🔴 CRITICAL | 17 | `tag_master` text JOIN still used in some paths | `plant_area_id` FK migration phased in §27.2 | 8 |
| 🔴 CRITICAL | 18 | Historian rows don't record `plant_area_id` | Immutable context stamped at insert time §27.3 | 6a |
| 🟠 HIGH | 19 | `active_sessions` missing `device_name` | Column added to both CREATE TABLE definitions | 4a |
| 🟠 HIGH | 20 | No central cache invalidation manager | `CacheManager` spec in §27.5 | 6b |
| 🟠 HIGH | 21 | No background maintenance jobs defined | Job schedule table in §27.6 | 4a |
| 🟠 HIGH | 22 | Historian partitioning not concretely designed | Monthly partition + retention policy §27.7 | 7 |
| 🟡 FUTURE | 23 | All queries hit single PostgreSQL instance | Read-replica + archive tier strategy §27.8 | 8 |
| 🟡 FUTURE | 24 | Per-request session validation on HMI polling | Lightweight token-epoch hybrid §27.9 | 8 |

---

## 26. Revised Implementation Order (All Phases)

| Phase | Item | Depends On | Status |
|-------|------|-----------|--------|
| 1 | DB: plants_areas, user_area_assignments, access_audit_log | — | ✅ Done |
| 2a–d | area_access_service, admin endpoints, container, decorators | Phase 1 | ✅ Done |
| 3a–b | AreaAccessTab.tsx, Admin.tsx tab | Phase 2 | ✅ Done |
| **4a** | DB: license_keys, active_sessions + `device_name`, audit log role columns, `roles.admin_scope` | Phase 1 | ⏳ Pending |
| **4b** | `license_service.py` — ECDSA-signed activation | Phase 4a | ⏳ Pending |
| **4c** | `session_service.py` — create/supersede/validate/immediate cache flush | Phase 4a | ⏳ Pending |
| **4d** | `admin_controller.py` — license + session endpoints + role-change audit | Phase 4b/4c | ⏳ Pending |
| **4e** | `decorators.py` — extend `@require_auth` with session DB check + scope=all guard | Phase 4c | ⏳ Pending |
| **4f** | Role area quota enforcement in `area_access_service.set_user_areas()` | Phase 2a | ⏳ Pending |
| **5a–e** | Frontend: license banner, session 401 handler, area quota counter, multi-area dropdown, session panel | Phase 4 | ⏳ Pending |
| **6a** | DB: `tag_uid BIGSERIAL` on tag_master, `user_tag_access` table, historian composite indexes, `tag_uid` backfill | Phase 1 | ⏳ Pending |
| **6b** | `tag_access_service.py` + `authorization_service.py` (central policy engine with resolved-tag-set cache) | Phase 6a | ⏳ Pending |
| **6c** | All data endpoints refactored to use `authz.get_visible_tag_uids()` — tag_controller, historian_controller, alarm_controller, report_controller, analytics_controller | Phase 6b | ⏳ Pending |
| **6d** | Frontend: Tag Access panel in Admin user edit (ALLOW/BLOCK/OPEN per area, group selector) | Phase 6b | ⏳ Pending |
| **7** | Admin hierarchy scaffold: `PlantAdmin` enforcement in `AuthorizationService.is_admin()` | Phase 6 stable | 🟡 Future |
| **7** | TimescaleDB monthly partitions + compression + retention policy | Phase 6a | 🟡 Future |
| **8** | `tag_master.plant_area_id` FK migration (eliminate text-match JOIN) | Phase 6a stable | 🟡 Future |
| **8** | Historian rows stamped with `plant_area_id` at insert time (immutable context) | Phase 8 | 🟡 Future |
| **9** | `CacheManager` centralized invalidation (`invalidate_user`, `invalidate_area`, `invalidate_sessions`) | Phase 6b | ⏳ Pending |
| **9** | Background maintenance jobs: session expiry, audit log rotation, cache consistency, partition creation | Phase 4a | ⏳ Pending |
| **9** | Read-replica connection pool for analytics / trends (primary = writes only) | Phase 8 | 🟡 Future |
| **9** | Token-epoch lightweight validation for high-frequency HMI polling endpoints | Phase 8 | 🟡 Future |

---

*This document is the binding specification for Plant/Area Access Control implementation.*
*Architecture audit completed May 24, 2026. All 🔴 CRITICAL items in §25 must be resolved before production deployment.*

---

## 27. Second Architecture Review — 9 Issues (May 24, 2026)

This section addresses all issues raised in the second formal review. Each subsection documents the **problem**, the **root cause**, and the **binding resolution** that must be implemented.

---

### 27.1 🔴 CRITICAL — License System Still Tamper-able via Direct DB Edit

#### Problem
Even though the activation key is SHA-256 hashed, the `max_users` limit is stored as a plain `INTEGER` column. A DB admin can bypass all seat enforcement with one SQL statement:

```sql
UPDATE historian_meta.license_keys SET max_users = 9999 WHERE is_active = true;
```

The previous `_check_user_limit()` implementation trusted this column directly. That is a **security violation** — license enforcement must not be defeatable by a local DB admin.

#### Root Cause
The limit was read from `max_users` (DB column) instead of from a cryptographically signed payload.

#### Binding Resolution — ECDSA Signed Payload

**License payload format** (signed by vendor's Ed25519 private key):

```json
{
  "customer":  "ABC Steel",
  "max_users": 50,
  "max_areas": null,
  "expiry":    "2027-01-01",
  "issued_at": "2026-05-24"
}
```

**Activation key format** (what the customer receives):
```
base64url(payload_json)  +  "."  +  base64url(ed25519_signature)
```

**What is stored in DB** (`signed_payload TEXT NOT NULL`): the full activation key string verbatim (payload + signature). `max_users` column is populated at activation time for display/reporting only.

**Runtime enforcement** always calls `_get_verified_max_users()` which:
1. Reads `signed_payload` from DB
2. Splits into payload bytes + signature bytes
3. Calls `public_key.verify(signature, payload_bytes)` — raises `InvalidSignature` if tampered
4. Extracts `max_users` from verified JSON
5. Returns `0` on any failure (tampered, missing, or malformed)

**Public key** is embedded in `config/license_public_key.pem` — NOT stored in DB. The vendor holds the private key. A DB admin cannot forge a valid signature without the private key.

**Library**: `pip install cryptography` — `Ed25519PublicKey` from `cryptography.hazmat.primitives.asymmetric.ed25519`

#### Schema Change Already Applied
`signed_payload TEXT NOT NULL` column added to `license_keys` CREATE TABLE in §16.2 above.  
`_get_verified_max_users()` function replaces the old DB-column read in §16.3 above.

#### Rule — DO NOT READ `max_users` DIRECTLY
```python
# ❌ FORBIDDEN — bypassable by DB admin
row['max_users']

# ✅ REQUIRED — cryptographically verified
_get_verified_max_users()
```

---

### 27.2 🔴 CRITICAL — `tag_master` Still Uses Text JOIN for plant/area

#### Problem
Any query that resolves tag scope using:
```sql
pa.plant = tm.plant AND pa.area = tm.area
```
is:
- **Fragile**: area rename → broken join silently returns wrong scope
- **Slower**: string comparison vs integer FK lookup
- **Mutable**: a renamed area or plant can orphan tags from the historian perspective

#### Target Final Model

```sql
-- Phase 8: Add plant_area_id FK to tag_master
ALTER TABLE historian_meta.tag_master
    ADD COLUMN plant_area_id INTEGER
    REFERENCES historian_meta.plants_areas(id) ON DELETE SET NULL;

-- Backfill: match existing text columns to FK
UPDATE historian_meta.tag_master tm
SET plant_area_id = pa.id
FROM historian_meta.plants_areas pa
WHERE pa.plant = tm.plant AND pa.area = tm.area;

-- After backfill verified: add index
CREATE INDEX idx_tag_master_plant_area ON historian_meta.tag_master(plant_area_id);
```

Once migrated, ALL joins become:
```sql
tm.plant_area_id = pa.id   -- integer FK — safe, fast, immutable
```

#### Migration Safety Rules
1. Add column as `NULLABLE` first — do not break existing rows
2. Backfill using text-match (one-time)
3. Verify 100% fill: `SELECT COUNT(*) FROM tag_master WHERE plant_area_id IS NULL` → must be 0
4. Set `NOT NULL` constraint after verification
5. Drop old `plant` + `area` text columns **only after** all code paths migrated
6. Phase 8 dependency: `tag_uid BIGSERIAL` migration (Phase 6a) must be stable first

#### Implementation Phase
Phase 8 — after Phase 6a (`tag_uid`) is stable in production. Do not rush. Text-join still works correctly in the interim.

---

### 27.3 🔴 CRITICAL — Historian Rows Missing Immutable Context at Insert Time

#### Problem
Historian rows in `historian_raw.historian_timeseries` currently record only `tag_uid`. The plant/area/scope of the data is **dynamically inferred** at query time from the current `tag_master` state. This means:

- An area is renamed → historical queries for that area return wrong results
- A tag is moved to a different area → historical data appears under new area retroactively
- A user's area access is revoked → the historical data scope silently changes

This violates the fundamental rule: **historical data must represent the state at capture time, forever**.

#### Binding Resolution — Stamp Context at Insert Time

```sql
-- Phase 6a: Add immutable context columns to historian_timeseries
ALTER TABLE historian_raw.historian_timeseries
    ADD COLUMN plant_area_id INTEGER;   -- FK to plants_areas.id — stamped at insert, never updated

-- ⚠ plant_area_id is intentionally NOT a hard FK here — if the area is later deleted,
--    historical rows must still be queryable. Use soft reference only.
```

**Insert logic in `DbWriterService`** (C#):

```csharp
// When writing historian row:
// Resolve plant_area_id ONCE from tag_master at ingest time
// Cache per tag_uid (invalidate on tag_master NOTIFY)
// Write to historian row: (tag_uid, timestamp, value, quality, plant_area_id)
```

**Query pattern after migration**:
```sql
-- Historical trend for a user
SELECT * FROM historian_raw.historian_timeseries
WHERE tag_uid      = ANY(:visible_tag_uids)
  AND plant_area_id = ANY(:user_plant_area_ids)   -- ← scope from CAPTURE TIME, not current state
  AND timestamp    BETWEEN :start AND :end
```

#### Why This Matters
Without this fix, revoking a user's area access does not retroactively hide data — but renaming an area or moving a tag **silently corrupts** historical scope resolution. Stamping at insert time is the only correct approach.

#### Implementation Phase
Phase 6a — simultaneously with `tag_uid BIGSERIAL` migration. Column added as `NULLABLE`. Backfill via `UPDATE` joining current `tag_master`. New inserts always populate it.

---

### 27.4 🟠 HIGH — `active_sessions` Missing `device_name` Column

#### Status: ✅ FIXED in §17 and §13 SQL Reference above.

Both `CREATE TABLE historian_meta.active_sessions` definitions now include:

```sql
device_name  VARCHAR(150),   -- e.g. 'Control Room PC-3', 'Mobile-iOS'
```

#### Usage Pattern in Login Flow

```python
# POST /api/auth/login — extract device_name from request body
device_name = request.json.get('device_name', 'Unknown')[:150]

# INSERT new session
cur.execute("""
    INSERT INTO historian_meta.active_sessions
        (user_id, session_token, jwt_jti, ip_address, user_agent, device_name, expires_at)
    VALUES
        (%s, %s, %s, %s, %s, %s, NOW() + INTERVAL '8 hours')
""", (user_id, session_token, jwt_jti, ip_address, user_agent, device_name))
```

#### UI Usage
Session management panel in Admin Console shows:
```
User: John Operator
 └─ [Active] Control Room PC-3   IP: 192.168.1.45   Last seen: 2 min ago   [Revoke]
 └─ [Expired] Mobile-iOS         IP: 10.0.0.12      Last seen: 3 days ago
```

---

### 27.5 🟠 HIGH — No Central Cache Invalidation Manager

#### Problem
Cache logic is currently spread across:
- `area_access_service.py` — area assignment cache
- `authorization_service.py` — visible tag UID cache
- `session_service.py` — session token cache
- `OpcDaHub` / WebSocket layer — push invalidation

This creates a distributed cache invalidation problem. When a user's role changes, **every cache layer** must be invalidated atomically. Missed invalidation = stale permissions in production = **security defect**.

#### Binding Resolution — `CacheManager` Singleton

```python
# WEB_HMI_MFA/HMI/services/cache_manager.py

class CacheManager:
    """
    Central invalidation point for ALL in-process caches.
    All cache writes go through CacheManager — no service manages its own TTL dict.

    TTL defaults (configurable):
        user_area_cache:    60s
        visible_tag_cache:  60s
        session_cache:      30s
        role_cache:         300s
    """

    def invalidate_user(self, user_id: int) -> None:
        """
        Clears ALL caches related to a user:
          - area assignments
          - visible tag UID set
          - active session tokens
          - role/permissions
        Call this on: role change, area change, forced logout, password reset.
        """

    def invalidate_area(self, plant_area_id: int) -> None:
        """
        Clears caches for ALL users assigned to the given area.
        Call this on: area deactivated, area renamed, area deleted.
        """

    def invalidate_sessions(self, user_id: int) -> None:
        """
        Clears only session cache for a user.
        Call this on: logout, admin forced-revoke, token superseded.
        """

    def invalidate_tag_scope(self, plant_area_id: int) -> None:
        """
        Clears visible_tag_uid caches for all users assigned to affected area.
        Call this on: tag moved, tag deleted, tag access rule changed.
        """
```

#### Invalidation Rule Table

| Event | Method to Call |
|-------|---------------|
| Role changed | `invalidate_user(user_id)` |
| Area assignment changed | `invalidate_user(user_id)` |
| Area deactivated/renamed | `invalidate_area(plant_area_id)` |
| Tag moved to different area | `invalidate_tag_scope(old_plant_area_id)` |
| Tag access rule added/removed | `invalidate_user(user_id)` |
| Session revoked | `invalidate_sessions(user_id)` |
| WebSocket pub/sub NOTIFY | `invalidate_user(user_id)` (async) |

#### Registration in `container.py`

```python
cache_manager = CacheManager(config)
container.register('cache_manager', cache_manager)

# Inject into all services that hold caches:
area_access_service = AreaAccessService(db, cache_manager)
authorization_service = AuthorizationService(db, cache_manager)
session_service = SessionService(db, cache_manager)
```

#### Implementation Phase
Phase 6b — concurrent with `authorization_service.py`. All existing local TTL dicts in other services must be removed and replaced with `CacheManager` delegation.

---

### 27.6 🟠 HIGH — No Background Maintenance Jobs Defined

#### Problem
The following stale data sources accumulate over time with no cleanup:
- Expired sessions stay in `active_sessions` indefinitely
- Old audit log rows are never archived or rotated
- Orphaned spool files from historian may never be replayed
- Cache state drifts from DB state between NOTIFY events
- TimescaleDB partitions must be pre-created for future months

#### Binding Resolution — Background Job Schedule

All jobs run as Python `threading.Timer` / `apscheduler` tasks started in `app.py`.

| Job | Trigger | Action |
|-----|---------|--------|
| `expire_sessions` | Every 5 min | `UPDATE active_sessions SET is_active=false, revoked_reason='EXPIRED' WHERE expires_at < NOW() AND is_active=true` |
| `cleanup_old_sessions` | Daily 02:00 | `DELETE FROM active_sessions WHERE is_active=false AND expires_at < NOW() - INTERVAL '30 days'` |
| `rotate_audit_log` | Monthly 1st 03:00 | Move rows older than 12 months to `historian_meta.access_audit_log_archive` |
| `refresh_cache_consistency` | Every 10 min | Re-warm top-N user caches from DB; emit NOTIFY if delta detected |
| `timescaledb_partition_check` | Monthly 25th 04:00 | Verify next 2 months' chunks exist; log warning if compression behind |
| `spool_health_check` | Every 30 min | Count spool files on disk; alert if > 50 files or > 500 MB |

#### Implementation Pattern (APScheduler)

```python
# WEB_HMI_MFA/HMI/services/maintenance_jobs.py

from apscheduler.schedulers.background import BackgroundScheduler

def register_maintenance_jobs(app, db_pool, cache_manager):
    scheduler = BackgroundScheduler()

    @scheduler.scheduled_job('interval', minutes=5, id='expire_sessions')
    def expire_sessions():
        with db_pool.getconn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE historian_meta.active_sessions
                    SET is_active = false, revoked_reason = 'EXPIRED'
                    WHERE expires_at < NOW() AND is_active = true
                """)
                conn.commit()

    @scheduler.scheduled_job('cron', hour=2, minute=0, id='cleanup_old_sessions')
    def cleanup_old_sessions():
        ...  # DELETE rows older than 30 days

    scheduler.start()
    app.extensions['scheduler'] = scheduler
```

#### pip dependency
```
apscheduler>=3.10
```

#### Implementation Phase
Phase 4a — with the DB migration. Jobs start running immediately when Flask app starts.

---

### 27.7 🟠 HIGH — Historian Partitioning Not Concretely Designed

#### Problem
`historian_raw.historian_timeseries` is referenced throughout the doc but no concrete partitioning strategy is specified. At industrial scale (1000+ tags × 1-second polling = 86M rows/day), a single unpartitioned table will degrade rapidly.

#### Binding Resolution — TimescaleDB Hypertable with Retention Policy

```sql
-- ── historian_raw.historian_timeseries (final schema) ───────────────────
CREATE TABLE historian_raw.historian_timeseries (
    tag_uid       BIGINT    NOT NULL,
    timestamp     TIMESTAMPTZ NOT NULL,
    opc_timestamp TIMESTAMPTZ,
    value         DOUBLE PRECISION,
    quality       VARCHAR(1) NOT NULL DEFAULT 'G',  -- 'G' | 'B' | 'U'
    plant_area_id INTEGER,   -- stamped at insert time (§27.3)
    ingest_ns     BIGINT     -- nanosecond ingest epoch for dedup
);

-- Convert to hypertable: 1-month chunks
SELECT create_hypertable(
    'historian_raw.historian_timeseries',
    'timestamp',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

-- Compression: compress chunks older than 7 days
ALTER TABLE historian_raw.historian_timeseries
    SET (timescaledb.compress,
         timescaledb.compress_orderby     = 'timestamp ASC',
         timescaledb.compress_segmentby   = 'tag_uid');

SELECT add_compression_policy(
    'historian_raw.historian_timeseries',
    INTERVAL '7 days'
);

-- Retention: drop chunks older than 3 years (configurable)
SELECT add_retention_policy(
    'historian_raw.historian_timeseries',
    INTERVAL '3 years'
);
```

#### Partition Strategy Summary

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Chunk interval | 1 month | Balances query locality vs partition count |
| Compression after | 7 days | Recent data uncompressed for fast live queries |
| Compression method | `segmentby tag_uid` | Columnar scan per-tag is most common access pattern |
| Retention | 3 years (configurable) | Regulatory minimum; archive tier can extend |
| Index | `(tag_uid, timestamp DESC)` per chunk | Trend queries almost always order descending |

#### Archival Policy (Long-Term)
Chunks beyond retention are dropped by TimescaleDB automatically. Before deletion, a `BEFORE_DROP` hook can copy the chunk to an S3-compatible object store or archive PostgreSQL instance.

#### Implementation Phase
Phase 7 — after Phase 6a (`tag_uid` and `plant_area_id` columns stable on historian table).

---

### 27.8 🟠 HIGH — No Read-Replica Strategy Defined

#### Problem
All current consumers — OPC live polling, historian writes, trend queries, analytics engines, report generation — hit the **same PostgreSQL primary**. At industrial scale, analytics and reports will starve live historian writes and session validation.

#### Binding Resolution — Three-Tier DB Topology

```
┌─────────────────────────────────────────────────────────────┐
│  PRIMARY (writes + live reads)                              │
│  ├── historian ingest (BINARY COPY)                         │
│  ├── session create/update/revoke                           │
│  ├── admin CRUD                                             │
│  └── alarm writes                                           │
└────────────────────┬────────────────────────────────────────┘
                     │ streaming replication
          ┌──────────┴──────────┐
          │                     │
┌─────────▼──────┐    ┌─────────▼─────────────────────────────┐
│  REPLICA        │    │  ARCHIVE (separate instance)          │
│  (read-only)   │    │  TimescaleDB chunks > 3 years          │
│  ├── trends    │    │  S3 / cold storage                     │
│  ├── reports   │    │  Accessed via FDW or API               │
│  └── analytics │    └──────────────────────────────────────-─┘
└────────────────┘
```

#### Connection Pool Routing

```python
# container.py — register two pool connections
db_primary = create_pool(config['DB_PRIMARY_URL'])    # writes + live
db_replica  = create_pool(config['DB_REPLICA_URL'])   # trends + reports

# Services use the correct pool:
historian_service.db = db_primary
trend_service.db     = db_replica
report_service.db    = db_replica
session_service.db   = db_primary
```

#### When to Implement
Phase 8 — not urgent for initial deployment. Architect for it by keeping `db_primary` / `db_replica` as separate injectable dependencies from day one. Even if both point to the same server initially, the routing code is already in place.

#### Config Keys to Reserve in `appsettings.json`
```json
"Database": {
  "PrimaryUrl":  "postgresql://cereveate@localhost:5432/Automation_DB",
  "ReplicaUrl":  "postgresql://cereveate@localhost:5432/Automation_DB",
  "ArchiveUrl":  null
}
```

---

### 27.9 🟠 HIGH — Per-Request Session Validation Overhead on HMI Polling

#### Problem
Current `@require_auth` middleware queries `active_sessions` on **every API request**. For HMI endpoints polled at 1-second intervals across 20+ concurrent users, this creates:

```
20 users × 1 req/sec × 1 DB lookup/req = 20 DB hits/sec — just for auth
```

At 100 users polling trend + alarm + value endpoints simultaneously, this becomes 100–300 DB hits/sec for auth alone, before any actual data query.

#### Binding Resolution — Token-Epoch Hybrid Model

```
JWT contains:  { user_id, session_id, epoch: N, exp: +8h }

CacheManager holds per-user: { session_id → (epoch, expires_at) }
  TTL: 30s in-process

On request:
  1. Decode JWT (no DB — just signature verify)
  2. Check CacheManager: is epoch still valid for this session_id?
     IF CACHE HIT → allow (no DB query)
     IF CACHE MISS → query active_sessions DB → update cache
  3. If admin forcibly revokes → increment epoch in DB + call CacheManager.invalidate_sessions(user_id)
     → next request: JWT epoch != DB epoch → 401 immediately
```

#### Epoch Revocation Pattern

```python
# Force-revoke: bump epoch in DB and in cache
cur.execute("""
    UPDATE historian_meta.active_sessions
    SET revoked_epoch = revoked_epoch + 1,
        is_active = false,
        revoked_reason = 'ADMIN_REVOKE'
    WHERE id = %s
""", (session_id,))
cache_manager.invalidate_sessions(user_id)
```

#### Impact
- **Cache hit** (99% of normal polling): zero DB queries for auth
- **Cache miss** (first request after 30s TTL): one DB query
- **Forced revoke**: propagates to user within 30s max (cache TTL), or immediately on next cache miss

#### Polling Endpoint Exemption
Endpoints that receive 1-second HMI polls (e.g., `GET /api/opc/values`, `GET /api/plc/values`) can use a lighter `@require_polling_auth` decorator that:
1. Validates JWT signature only (no DB)
2. Checks in-process epoch cache
3. Skips `last_seen_at` DB update (batched every 30s instead of every request)

#### Implementation Phase
Phase 8 — after session infrastructure is stable. The decorator can be layered on without changing any data endpoints.

---

### 27.10 Summary — All 9 Issues Resolution Status

| # | Severity | Issue | Resolution | Phase | Status |
|---|----------|-------|-----------|-------|--------|
| 1 | 🔴 CRITICAL | `max_users` read from DB — bypassable | ECDSA `signed_payload` + `_get_verified_max_users()` | 4b | ✅ Spec complete |
| 2 | 🔴 CRITICAL | `tag_master` text JOIN fragile | `plant_area_id INTEGER FK` migration | 8 | 📋 Phased |
| 3 | 🔴 CRITICAL | Historian rows missing immutable context | `plant_area_id` stamped at insert time | 6a | 📋 Phased |
| 4 | 🟠 HIGH | `active_sessions` missing `device_name` | Column added to both CREATE TABLE definitions | 4a | ✅ Fixed in doc |
| 5 | 🟠 HIGH | No central cache invalidation | `CacheManager` singleton spec | 6b | ✅ Spec complete |
| 6 | 🟠 HIGH | No background maintenance jobs | APScheduler job table + code pattern | 4a | ✅ Spec complete |
| 7 | 🟠 HIGH | Partitioning not concretely designed | Hypertable spec + compression + retention policy | 7 | ✅ Spec complete |
| 8 | 🟠 HIGH | Single DB for all reads/writes | Three-tier topology + connection pool routing | 8 | ✅ Spec complete |
| 9 | 🟠 HIGH | Per-request session DB lookup on polling | Token-epoch hybrid + `@require_polling_auth` | 8 | ✅ Spec complete |
