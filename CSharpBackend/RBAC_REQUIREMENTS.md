# Role-Based Access Control (RBAC) — Requirements Specification

## 1. Overview

This document defines the exact RBAC requirements for the Cereveate OPC DA / Analytics HMI platform.  
All access enforcement must be maintained at **both the database level (`historian_meta` schema) and the API layer**.  
The UI must dynamically show/hide modules and controls based on the authenticated user's role.

---

## 2. Defined Roles

Four roles must exist in `historian_meta.roles`. No other roles should grant module access.

| Role ID | Role Name  | `is_admin` | Description |
|---------|------------|------------|-------------|
| 1       | `Admin`    | true       | Full system access. User management, configuration, all modules. |
| 2       | `Operator` | false      | Plant floor operator. Can operate HMI, acknowledge/clear alarms, and generate reports. |
| 3       | `Viewer`   | false      | Read-only observer. Can only view live HMI and alarm screens. No reports, no actions. |
| 13      | `Engineer` | false      | Process/control engineer. Can operate HMI, view/generate reports, run BI analytics. |

---

## 3. Access Control Matrix (Source of Truth)

| Module / Function  | Viewer       | Operator             | Engineer           | Admin        | Description                            |
|--------------------|--------------|----------------------|--------------------|--------------|----------------------------------------|
| **HMI Screens**    | View Only    | Operate & View       | View Only          | Full Access  | Plant process monitoring screens       |
| **Alarm Management** | View Only  | Acknowledge & Clear  | View Only          | Full Access  | Alarm monitoring and handling          |
| **Reports**        | No Access    | Generate Reports     | View Only          | Full Access  | Shift, Daily, Monthly Reports          |
| **Admin Module**   | No Access    | No Access            | No Access          | Full Access  | System administration and configuration|
| **BI Analytics**   | No Access    | No Access            | Advanced Analysis  | Full Access  | Industrial business analytics          |

---

## 4. Per-Module Permission Breakdown

### 4.1 HMI Screens

| Action              | Viewer | Operator | Engineer | Admin |
|---------------------|--------|----------|----------|-------|
| View live values    | ✅     | ✅       | ✅       | ✅    |
| Operate (setpoints) | ❌     | ✅       | ❌       | ✅    |
| Modify config       | ❌     | ❌       | ❌       | ✅    |
| Configure layout    | ❌     | ❌       | ❌       | ✅    |

### 4.2 Alarm Management

| Action                  | Viewer | Operator | Engineer | Admin |
|-------------------------|--------|----------|----------|-------|
| View active alarms      | ✅     | ✅       | ✅       | ✅    |
| Acknowledge alarm       | ❌     | ✅       | ❌       | ✅    |
| Clear alarm             | ❌     | ✅       | ❌       | ✅    |
| View alarm history      | ✅     | ✅       | ✅       | ✅    |
| Configure alarm setpoints | ❌   | ❌       | ❌       | ✅    |

### 4.3 Reports

| Action                   | Viewer | Operator | Engineer | Admin |
|--------------------------|--------|----------|----------|-------|
| Access reports module    | ❌     | ✅       | ✅       | ✅    |
| View report on screen    | ❌     | ✅       | ✅       | ✅    |
| Generate (fetch) report  | ❌     | ✅       | ❌       | ✅    |
| Export / Download XLSX   | ❌     | ✅       | ❌       | ✅    |

> **Note:** Engineer role can VIEW reports (read-only, no export button shown).  
> Operator and Admin can generate AND export.

### 4.4 Admin Module

| Action                  | Viewer | Operator | Engineer | Admin |
|-------------------------|--------|----------|----------|-------|
| Access admin module     | ❌     | ❌       | ❌       | ✅    |
| Manage users            | ❌     | ❌       | ❌       | ✅    |
| Approve/revoke users    | ❌     | ❌       | ❌       | ✅    |
| Assign roles            | ❌     | ❌       | ❌       | ✅    |
| System configuration    | ❌     | ❌       | ❌       | ✅    |

### 4.5 BI Analytics

| Action                  | Viewer | Operator | Engineer | Admin |
|-------------------------|--------|----------|----------|-------|
| Access BI module        | ❌     | ❌       | ✅       | ✅    |
| View baselines/trends   | ❌     | ❌       | ✅       | ✅    |
| Run analysis            | ❌     | ❌       | ✅       | ✅    |
| Compare scenarios       | ❌     | ❌       | ✅       | ✅    |
| Configure BI models     | ❌     | ❌       | ❌       | ✅    |

---

## 5. Database Schema Requirements

### 5.1 `historian_meta.roles` table

Must contain exactly these 4 rows (seed data):

```sql
-- Ensure the 4 standard roles exist
INSERT INTO historian_meta.roles (id, name, description, is_admin)
VALUES
  (1, 'Viewer',   'Read-only access to HMI and alarms only',                          false),
  (2, 'Operator', 'Operate HMI, acknowledge/clear alarms, generate and export reports', false),
  (3, 'Engineer', 'View HMI/alarms, view reports (no export), full BI analytics',      false),
  (4, 'Admin',    'Full system access including user management and configuration',     true)
ON CONFLICT (id) DO UPDATE
  SET name        = EXCLUDED.name,
      description = EXCLUDED.description,
      is_admin    = EXCLUDED.is_admin;
```

### 5.2 `historian_meta.role_module_permissions` table (NEW — to be created)

This table enforces permissions at DB level. Each row = one role's access level for one module.

```sql
CREATE TABLE IF NOT EXISTS historian_meta.role_module_permissions (
    id              SERIAL PRIMARY KEY,
    role_id         INTEGER NOT NULL REFERENCES historian_meta.roles(id) ON DELETE CASCADE,
    module          TEXT    NOT NULL,  -- 'hmi' | 'alarms' | 'reports' | 'admin' | 'bi_analytics'
    can_view        BOOLEAN NOT NULL DEFAULT false,
    can_operate     BOOLEAN NOT NULL DEFAULT false,  -- HMI operate / alarm ack+clear
    can_generate    BOOLEAN NOT NULL DEFAULT false,  -- reports: generate+export
    can_configure   BOOLEAN NOT NULL DEFAULT false,  -- admin config / BI config
    UNIQUE (role_id, module)
);

-- Seed data matching the access control matrix
INSERT INTO historian_meta.role_module_permissions
    (role_id, module,        can_view, can_operate, can_generate, can_configure)
VALUES
-- Viewer (role 1)
  (1, 'hmi',          true,  false, false, false),
  (1, 'alarms',       true,  false, false, false),
  (1, 'reports',      false, false, false, false),
  (1, 'admin',        false, false, false, false),
  (1, 'bi_analytics', false, false, false, false),
-- Operator (role 2)
  (2, 'hmi',          true,  true,  false, false),
  (2, 'alarms',       true,  true,  false, false),
  (2, 'reports',      true,  false, true,  false),
  (2, 'admin',        false, false, false, false),
  (2, 'bi_analytics', false, false, false, false),
-- Engineer (role 3)
  (3, 'hmi',          true,  false, false, false),
  (3, 'alarms',       true,  false, false, false),
  (3, 'reports',      true,  false, false, false),
  (3, 'admin',        false, false, false, false),
  (3, 'bi_analytics', true,  true,  false, false),
-- Admin (role 4)
  (4, 'hmi',          true,  true,  true,  true),
  (4, 'alarms',       true,  true,  true,  true),
  (4, 'reports',      true,  false, true,  true),
  (4, 'admin',        true,  true,  true,  true),
  (4, 'bi_analytics', true,  true,  true,  true)
ON CONFLICT (role_id, module) DO UPDATE
  SET can_view      = EXCLUDED.can_view,
      can_operate   = EXCLUDED.can_operate,
      can_generate  = EXCLUDED.can_generate,
      can_configure = EXCLUDED.can_configure;
```

### 5.3 DB-Level Permission Check Function

```sql
CREATE OR REPLACE FUNCTION historian_meta.get_user_permissions(p_user_id INTEGER)
RETURNS TABLE (
    module        TEXT,
    can_view      BOOLEAN,
    can_operate   BOOLEAN,
    can_generate  BOOLEAN,
    can_configure BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT rmp.module, rmp.can_view, rmp.can_operate, rmp.can_generate, rmp.can_configure
    FROM historian_meta.role_module_permissions rmp
    JOIN historian_meta.users u ON u.role_id = rmp.role_id
    WHERE u.id = p_user_id
      AND u.status = 'approved';
END;
$$ LANGUAGE plpgsql STABLE;
```

---

## 6. API Enforcement Requirements

### 6.1 Login Response — Must Return Role + Permissions

The `/api/auth/login` and `/api/auth/validate` responses must include:

```json
{
  "user_id": 5,
  "username": "Mustafa",
  "role": "Operator",
  "role_id": 2,
  "is_admin": false,
  "permissions": {
    "hmi":          { "can_view": true,  "can_operate": true,  "can_generate": false, "can_configure": false },
    "alarms":       { "can_view": true,  "can_operate": true,  "can_generate": false, "can_configure": false },
    "reports":      { "can_view": true,  "can_operate": false, "can_generate": true,  "can_configure": false },
    "admin":        { "can_view": false, "can_operate": false, "can_generate": false, "can_configure": false },
    "bi_analytics": { "can_view": false, "can_operate": false, "can_generate": false, "can_configure": false }
  }
}
```

### 6.2 API Endpoint Guards

Every protected endpoint must check the role from JWT token before processing:

| Endpoint Pattern              | Required Permission              |
|-------------------------------|----------------------------------|
| `GET /api/opc/*`              | `hmi.can_view`                   |
| `POST /api/opc/write`         | `hmi.can_operate`                |
| `GET /api/alarms/*`           | `alarms.can_view`                |
| `POST /api/alarms/ack`        | `alarms.can_operate`             |
| `POST /api/alarms/clear`      | `alarms.can_operate`             |
| `GET /api/reports/*`          | `reports.can_view`               |
| `GET /api/reports/*/export`   | `reports.can_generate`           |
| `GET /api/admin/*`            | `admin.can_view` (is_admin=true) |
| `POST /api/admin/*`           | `admin.can_configure`            |
| `GET /api/bi/*`               | `bi_analytics.can_view`          |
| `POST /api/bi/configure`      | `bi_analytics.can_configure`     |

---

## 7. Frontend (React/Vite) UI Requirements

The frontend must read `permissions` from the auth context and conditionally render:

### 7.1 Navigation Menu Visibility

| Nav Item          | Show when                          |
|-------------------|------------------------------------|
| HMI               | Always (all roles)                 |
| Alarm Management  | Always (all roles)                 |
| Reports           | `reports.can_view = true`          |
| Admin             | `is_admin = true`                  |
| BI Analytics      | `bi_analytics.can_view = true`     |

### 7.2 Action Button Visibility

| Button / Control           | Show when                          |
|----------------------------|------------------------------------|
| HMI operate controls       | `hmi.can_operate = true`           |
| Alarm ACK button           | `alarms.can_operate = true`        |
| Alarm CLEAR button         | `alarms.can_operate = true`        |
| Report Generate button     | `reports.can_generate = true`      |
| Report Export/Download     | `reports.can_generate = true`      |
| BI Configure button        | `bi_analytics.can_configure = true`|
| Admin panel actions        | `is_admin = true`                  |

### 7.3 Engineer Reports — View Only Mode

When `reports.can_view = true` AND `reports.can_generate = false`:
- Show report table (read-only, no filters active for generate)
- **Hide** "Generate Report" button
- **Hide** "Export / Download XLSX" button
- Show a badge: `👁 View Only`

---

## 8. Implementation Checklist

### Database
- [x] Verify `historian_meta.roles` has all 4 roles — **DONE** (Admin=1, Operator=2, Viewer=3, Engineer=13)
- [x] Create `historian_meta.role_module_permissions` table — **DONE** (May 2026)
- [x] Seed all 20 permission rows (4 roles × 5 modules) — **DONE**
- [ ] Create `historian_meta.get_user_permissions()` function (§5.3) — optional, Python method preferred

### Backend (Flask)
- [x] Update `/api/auth/login` response to include `permissions` object — **DONE** (`auth_controller.py`)
- [x] Update `/api/auth/mfa/verify` response to include `permissions` object — **DONE**
- [x] Update `/api/auth/validate` response to include `permissions` object — **DONE**
- [x] Add `get_user_module_permissions(user_id)` method in `rbac_service.py` — **DONE**
- [ ] Apply `require_permission` decorator to report export endpoints (`can_generate`)
- [ ] Apply `require_permission` decorator to alarm ACK/CLEAR endpoints (`can_operate`)
- [ ] Apply `require_permission` decorator to BI endpoints (`can_view`)

### Frontend (React)
- [x] `UserPermissions` / `ModulePermission` types added to `auth-service.ts` — **DONE**
- [x] `permissions` field added to `User` interface — **DONE**
- [x] `usePermission(module, action)` hook created at `hooks/usePermission.ts` — **DONE**
- [x] `useModulePermissions(module)` convenience hook created — **DONE**
- [x] Admin panel: approve user with role dropdown — **DONE** (`UsersTab.tsx`)
- [x] Admin panel: change role of approved user — **DONE** (`UsersTab.tsx`)
- [ ] Hide Reports nav item for Viewer role (use `usePermission('reports','canView')`)
- [ ] Hide Admin nav item for non-Admin roles (use `user.isAdmin`)
- [ ] Hide BI nav item for Viewer and Operator roles
- [ ] Hide alarm ACK/CLEAR buttons for Viewer and Engineer
- [ ] Hide report Generate/Export buttons for Viewer (show view-only badge for Engineer)

---

## 9. Current System State

The following RBAC infrastructure **already exists** in the codebase:

| Component | File | Status |
|-----------|------|--------|
| `historian_meta.roles` table (4 roles) | DB | ✅ Admin, Operator, Viewer, Engineer |
| `historian_meta.users` table | DB | ✅ Exists |
| `historian_meta.role_module_permissions` | DB | ✅ **Created & seeded May 2026** |
| `RBACService` (user/role CRUD) | `services/rbac_service.py` | ✅ Exists |
| `get_user_module_permissions()` method | `services/rbac_service.py` | ✅ **Added May 2026** |
| `permissions` in login/validate response | `controllers/auth_controller.py` | ✅ **Added May 2026** |
| `UserPermissions` / `ModulePermission` types | `services/auth-service.ts` | ✅ **Added May 2026** |
| `usePermission(module, action)` hook | `hooks/usePermission.ts` | ✅ **Created May 2026** |
| Admin panel user approval with role dropdown | `pages/admin/components/UsersTab.tsx` | ✅ Exists |
| Admin panel change role for approved users | `pages/admin/components/UsersTab.tsx` | ✅ Exists |
| `IndustrialRBACService` (SoD, certs) | `services/industrial_rbac_service.py` | ✅ Exists |
| Frontend permission-based nav/button hiding | React components | ⏳ **Pending — use `usePermission` hook** |

---

## 10. Notes

- Role names in DB are **case-sensitive**: `Viewer`, `Operator`, `Engineer`, `Admin`
- `is_admin = true` only for the `Admin` role — used as a fast-path check
- If a user has no role assigned (`role_id = NULL`), they get **zero permissions** (treat as Viewer with no access)
- Role changes take effect on next login (new JWT issued)
- All RBAC violations must be logged to `historian_raw.alarm_audit_trail` with `action_type = 'ACCESS_DENIED'`
