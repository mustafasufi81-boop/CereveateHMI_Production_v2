# HMI Database Study Report
**Generated:** May 2026  
**Scope:** `WEB_HMI_MFA/HMI/apex-hmi` (React/TypeScript frontend) + `WEB_HMI_MFA/HMI/` (Python Flask backend)  
**Purpose:** Full inventory of every DB table used, how it is used, and what is redundant — before any new Phase 1 alarm tables are added

---

## System Architecture Overview

```
┌─────────────────────────────────┐
│   apex-hmi (React/TypeScript)   │
│   Vite + Axios + WebSocket       │
└────────────┬────────────────────┘
             │ HTTP REST (axios, baseURL = /api)
             │ WebSocket (mqtt-websocket.ts → localhost:6001/ws)
             ▼
┌─────────────────────────────────┐
│  Flask HMI Backend (Python)     │
│  WEB_HMI_MFA/HMI/app.py         │
│  Blueprints: alarm, auth, admin, │
│  historical, session, approval,  │
│  audit, equipment, tags, reports │
└────────────┬────────────────────┘
             │ psycopg2 direct SQL
             ▼
┌─────────────────────────────────┐
│  PostgreSQL  Automation_DB       │
│  Schemas: historian_raw          │
│           historian_meta         │
└─────────────────────────────────┘
             ▲
             │ INSERT only (alarm events)
             │ AlarmEvaluationService.cs (C#)
             │ HistorianIngestHostedService.cs (C#)
```

**Live data path:** C# OPC → MQTT broker → `mqtt_subscriber_service` websocket bridge → apex-hmi WebSocket  
**No REST polling for live tag values** — all pushed via WebSocket.

---

## Database Tables — Complete Inventory

### Schema: `historian_raw`

---

#### `historian_raw.historian_events`
**Who owns it:** C# `AlarmEvaluationService` (INSERT only)  
**HMI role:** READ + limited UPDATE (ACK/CLEAR state transitions only)

| Operation | Columns | Python File → Route |
|-----------|---------|---------------------|
| SELECT (active alarm list) | event_id, tag_id, event_type, alarm_state, alarm_priority, severity, message, time, acknowledged_by, acknowledged_at, cleared_at, cleared_by, alarm_actual_value, alarm_setpoint, equipment | `alarm_controller.py` → `GET /api/alarms/active` |
| SELECT (before ACK) | alarm_state, event_type, tag_id, alarm_priority, alarm_actual_value, alarm_setpoint WHERE event_id | `alarm_controller.py` → `POST /api/alarms/acknowledge/<id>` |
| SELECT (before CLEAR) | same as above | `alarm_controller.py` → `POST /api/alarms/clear/<id>` |
| SELECT (MQTT ack check) | event_id, alarm_state WHERE message LIKE AND tag_id AND time >= NOW()-1h | `alarm_controller.py` → `POST /api/alarms/acknowledge` |
| SELECT COUNT (stats) | alarm_state, alarm_priority GROUP WHERE last 24h | `alarm_controller.py` → `GET /api/alarms/stats` |
| SELECT (trip causality) | event_id, event_type, severity, alarm_state, time, alarm_actual_value, alarm_setpoint, alarm_priority near trip timestamp | `alarm_controller.py` trip helper |
| UPDATE → ACKNOWLEDGED | alarm_state='ACKNOWLEDGED', acknowledged_at=NOW(), acknowledged_by, message WHERE event_id | `alarm_controller.py` → `POST /api/alarms/acknowledge/<id>` |
| UPDATE → CLEARED | alarm_state='CLEARED', cleared_at=NOW(), cleared_by, clear_reason, clear_notes, message WHERE event_id | `alarm_controller.py` → `POST /api/alarms/clear/<id>` |

**Current alarm_state values in production:** `'ACTIVE'`, `'ACKNOWLEDGED'`, `'CLEARED'`  
**⚠️ CRITICAL:** Phase 1 C# AlarmStateManager will change these to `ACTIVE_UNACK / ACTIVE_ACK / RTN_UNACK / CLEARED` — HMI will break if not updated simultaneously.

---

#### `historian_raw.historian_timeseries`
**Who owns it:** C# `HistorianIngestHostedService` (INSERT only)  
**HMI role:** SELECT only (trends, historical panels, reports)

| Operation | Columns | Python File → Route |
|-----------|---------|---------------------|
| SELECT (single tag trend) | time, value, quality_code WHERE tag_id AND time range | `historical_controller.py` → `POST /api/historical` |
| SELECT (multiple tag trends) | time, tag_id, value, opc_timestamp | `historical_controller.py` → `POST /api/historical/multiple` |
| SELECT (sampled via ROW_NUMBER) | time, value, tag_id | `historical_controller.py` sampled endpoint |
| SELECT (latest per tag) | value, time, opc_timestamp JOIN tag_master | `tag_controller.py` → `GET /api/tags/latest` |
| SELECT DISTINCT tag_id | tag_id | `historical_controller.py` diagnostic |
| SELECT (daily/shift/monthly aggregates) | time_bucket, avg/min/max via `v_daily_hourly_agg` view | `report_controller.py` → `/api/reports/daily`, `/shift`, `/monthly` |

**React components consuming this:**
- `HistoricalDataPanel.tsx` → `POST /api/historical`
- `TagTrendModal.tsx` → `POST /api/historical` + `POST /api/historical/multiple`
- `TrendChart.tsx` → `POST /api/historical/tag/<id>`

---

#### `historian_raw.alarm_audit_trail`
**Who owns it:** Flask HMI via `AlarmAuditDAO` (from `mqtt_subscriber_service`)  
**HMI role:** INSERT on every ACK/CLEAR, SELECT for audit history view

| Operation | Columns | Python File → Route |
|-----------|---------|---------------------|
| INSERT (on ACK) | event_id, tag_id, event_type, action_type='ACKNOWLEDGED', performed_by, previous_state, new_state, alarm_priority, alarm_actual_value, alarm_setpoint, action_notes, session_id, client_ip | `alarm_controller.py` → inside ACK route |
| INSERT (on CLEAR) | same + action_reason, action_notes | `alarm_controller.py` → inside CLEAR route |
| SELECT (full audit for event) | All 18 columns including tag_name, tag_description, plant, area, equipment, priority_label, minutes_since_previous_action, response_time_seconds | `alarm_controller.py` → `GET /api/alarms/audit/<id>` |
| SELECT (by tag_id) | All columns | `alarm_controller.py` → `GET /api/alarms/audit/tag/<tag_id>` |

**⚠️ Runtime risk:** `AlarmAuditDAO` is imported conditionally. If `mqtt_subscriber_service` is not on Python path, `HAS_ALARM_AUDIT = False` and all INSERT operations are **silently skipped** with a debug print only.

**React consuming this:** `AlarmPanel.tsx` → `GET /api/alarms/audit/<alarmId>` (opens audit history modal)

---

#### `historian_raw.alarm_active` ← **NEW TABLE (Phase 1)**
**Who owns it:** C# `AlarmStateManager` (Phase 1, not yet running)  
**HMI role:** ❌ **ZERO REFERENCES in any Python Flask file or React component**

This table currently has 0 rows and is not read or written by any HMI code. It was created by the DB migration but no code uses it yet.

---

#### `historian_raw.interlock_state_tracking`
**Who owns it:** C# `InterlockEvaluationService` (INSERT assumed)  
**HMI role:** SELECT only

| Operation | Columns | Python File → Route |
|-----------|---------|---------------------|
| SELECT (violations/bypasses) | interlock_event_id, event_time, interlock_tag_id, interlock_type, interlock_state, previous_state, state_duration_seconds, affected_equipment, bypass_reason, bypass_authorized_by, bypass_expires_at, related_trip_event_id | `alarm_controller.py` → `GET /api/alarms/interlocks` |
| SELECT (at trip time) | interlock_tag_id, interlock_type, interlock_state, affected_equipment, event_time WHERE related_trip OR near trip time AND state IN ('VIOLATED','BYPASSED') | `alarm_controller.py` trip helper |

**React consuming this:** `InterlockStatusBoard.tsx` — data arrives via WebSocket `mqtt_interlock` event (not REST). The REST endpoint is fallback/initial load.

---

#### `historian_raw.trip_event_tracking`
**Who owns it:** C# service (assumed)  
**HMI role:** SELECT only

| Operation | Columns | Python File → Route |
|-----------|---------|---------------------|
| SELECT (trip list with JOINs) | trip_event_id, trip_time, trip_tag_id, trip_category, equipment_affected, trip_duration_seconds, trip_cleared_at, root_cause_tag_id, automated_diagnosis, rated_capacity_mw, revenue_per_mwh, acknowledged_at, acknowledged_by, cleared_by, initiating_alarm_id (FK → historian_events) | `alarm_controller.py` → `GET /api/alarms/trips` |

**React consuming this:** `TripEventCard.tsx`, `TripTimeline.tsx` — props supplied by parent pages, not direct fetch.

---

### Schema: `historian_meta`

---

#### `historian_meta.tag_master`
**Who owns it:** C# configuration / manual DB inserts  
**HMI role:** SELECT only (read-only reference data)

| Operation | Columns | Python File → Route |
|-----------|---------|---------------------|
| SELECT (enabled tags for display) | tag_id, tag_name, plant, area, equipment, data_type, eng_unit | `tag_controller.py` → `GET /api/tags` |
| SELECT (P&ID mappings) | tag_id, tag_name, description, equipment, eng_unit, data_type, hi_limit, hi_warning, lo_warning, lo_limit WHERE equipment patterns | `tag_controller.py` → `GET /api/tags/pid-mappings` |
| SELECT (plant/area for RBAC) | plant, area WHERE enabled | `admin_controller.py` → `GET /api/admin/plants-areas` |
| SELECT (available tags for role perms) | tag_id, tag_name, plant, area, equipment | `admin_controller.py` → `GET /api/admin/tags` |
| SELECT (JOIN in alarm queries) | tag_name via LEFT JOIN on tag_id | `alarm_controller.py` multiple queries |
| SELECT (JOIN in trip queries) | tag_name via LEFT JOIN | `alarm_controller.py` trip query |

**React consuming this:** `usePIDTagMappings.ts` → `GET /api/tags/pid-mappings`, `PermissionsTab.tsx`, live P&ID panels

---

#### `historian_meta.users`
**Who owns it:** Flask HMI (full CRUD)  
**HMI role:** Full owner — auth, admin management

| Operation | Columns | Python File → Route |
|-----------|---------|---------------------|
| INSERT | username, password_hash, role_id, email, failed_login_attempts, is_active | `auth_service.py` → `POST /api/auth/register` |
| SELECT (login) | id, password_hash, role_id, is_active, failed_login_attempts, locked_until | `auth_service.py` → `POST /api/auth/login` |
| SELECT (all with role JOIN) | id, username, email, is_active, role_name, role_id, mfa_enabled, is_admin | `admin_controller.py` → `GET /api/admin/users` |
| UPDATE (lockout/unlock) | failed_login_attempts, locked_until | `auth_service.py` |
| UPDATE (MFA settings) | mfa_secret, mfa_enabled, security_questions (JSONB) | `auth_service.py` |
| UPDATE (password reset) | password_hash, failed_login_attempts | `auth_service.py` → `POST /api/auth/reset-password` |
| UPDATE (role change) | role_id | `admin_controller.py` → `POST /api/admin/users/<id>/approve` |

---

#### `historian_meta.roles`
**Who owns it:** Flask HMI admin  
**HMI role:** Full CRUD

| Operation | Columns | Python File → Route |
|-----------|---------|---------------------|
| SELECT (all) | id, name, description, permissions, created_at | `admin_controller.py` → `GET /api/admin/roles` |
| SELECT (JOIN in user queries) | role_name via JOIN | multiple routes |
| INSERT | name, description, permissions | `admin_controller.py` → `POST /api/admin/roles` |
| UPDATE | name, description, permissions WHERE id | `admin_controller.py` → `PUT /api/admin/roles/<id>` |
| DELETE | WHERE id | `admin_controller.py` → `DELETE /api/admin/roles/<id>` |

---

#### `historian_meta.user_sessions`
**Who owns it:** Flask HMI (via DB stored functions)  
**HMI role:** Full owner — session lifecycle management

| Operation | How | Python File → Route |
|-----------|-----|---------------------|
| INSERT (new session) | Via `historian_meta.create_user_session()` | `session_service.py` → login |
| SELECT (validate token) | By session_token hash | `session_service.py` → `GET /api/auth/validate` |
| UPDATE (heartbeat) | Via `historian_meta.update_session_activity()` | `session_controller.py` → `POST /api/session/activity` |
| UPDATE (logout) | Via DB function | `session_controller.py` → `POST /api/session/logout` |
| SELECT (active sessions view) | Via `historian_meta.active_sessions` view | `session_controller.py` → `GET /api/session/active` |
| UPDATE (admin force-end) | forced_logout=true, logout_time, logout_reason WHERE id | `session_controller.py` → `POST /api/session/end-by-id/<id>` |

---

#### `historian_meta.user_actions_audit`
**Who owns it:** Flask HMI (central audit sink)  
**HMI role:** INSERT everywhere, SELECT for audit viewer

This is the **single central audit table** for all human actions. Every significant operation calls `audit_service.log_action()` which calls the DB stored function `historian_meta.log_user_action()`.

**Events logged to this table:**
| Action Type | Category | Triggered By |
|------------|----------|--------------|
| LOGIN / LOGOUT | `authentication` | `auth_service.py` |
| FAILED_LOGIN | `authentication` | `auth_service.py` |
| ALARM_ACKNOWLEDGMENT | `alarm` | `alarm_controller.py` |
| ALARM_CLEAR | `alarm` | `alarm_controller.py` |
| SETPOINT_CHANGE | `control` | HMI control actions |
| EQUIPMENT_OPERATION (START/STOP/RESTART/EMERGENCY_STOP) | `control` | equipment controller |
| MODE_CHANGE | `control` | equipment controller |
| PAGE_VIEW | `navigation` | frontend `audit-service.ts` |
| USER_CREATED / ROLE_CHANGED | `admin` | `admin_controller.py` |
| SESSION_TERMINATED | `admin` | `session_controller.py` |
| PASSWORD_RESET | `authentication` | `auth_controller.py` |

**React consuming this:** `audit-service.ts` → `POST /api/audit/log` (fire-and-forget)  
**Admin view:** `AlertsTab.tsx` reads `GET /api/admin/alerts` → queries `system_alerts` (lockout events)  
**Full audit search:** `GET /api/audit` with filters → `historian_meta.user_actions_audit`

---

#### `historian_meta.operation_approvals` + `historian_meta.critical_operations`
**Who owns it:** Flask HMI (via DB stored functions)  
**HMI role:** Full owner

| Operation | Function | Python File → Route |
|-----------|----------|---------------------|
| SELECT (pending for approver) | `pending_approvals` view | `approval_controller.py` → `GET /api/approval/pending` |
| SELECT (my requests) | `user_pending_approvals` view | `approval_controller.py` → `GET /api/approval/my-requests` |
| INSERT (request approval) | `historian_meta.request_critical_operation_approval()` | `approval_controller.py` → `POST /api/approval/request` |
| UPDATE (approve) | `historian_meta.approve_critical_operation()` | `approval_controller.py` → `POST /api/approval/approve/<id>` |
| UPDATE (deny) | `historian_meta.deny_critical_operation()` | `approval_controller.py` → `POST /api/approval/deny/<id>` |
| UPDATE (expire old) | UPDATE status='expired' WHERE pending AND expires_at < NOW() | `approval_controller.py` → `POST /api/approval/expire-old` |
| SELECT (check if operation needs approval) | WHERE operation_code AND requires_approval=true | `approval_controller.py` → `GET /api/approval/check/<op_code>` |

**React consuming this:** `useApprovalWorkflow.ts` — polls every 2000ms when status = pending

---

#### `historian_meta.role_tag_permissions` + `historian_meta.role_specific_tag_permissions`
**Who owns it:** Flask HMI admin  
**HMI role:** Full CRUD

Used by `PermissionsTab.tsx` in admin panel. Controls which roles can view/write which plant/area/tag combinations.

| Table | Key Columns | Operations |
|-------|-------------|------------|
| `role_tag_permissions` | id, role_id, plant, area, tag_id, can_view, can_write | SELECT/INSERT-UPSERT/DELETE |
| `role_specific_tag_permissions` | id, role_id, tag_id, can_view, can_write | SELECT/INSERT-UPSERT/DELETE |
| `historian_meta.role_alarm_permissions` | id, role_id, plant, area, tag_id, can_acknowledge, can_clear, can_suppress | SELECT/INSERT-UPSERT/DELETE |

---

#### `historian_meta.equipment_permissions`
**Who owns it:** Flask HMI  
**HMI role:** Full owner

| Operation | Columns | Python File → Route |
|-----------|---------|---------------------|
| INSERT/UPSERT | user_id, equipment_id, permission_level | `equipment_controller.py` → `POST /api/equipment/permissions` |
| SELECT (check user perm) | permission_level, grant_type, granted_by, expires_at | `equipment_controller.py` → `GET /api/equipment/permissions/<equipment_id>` |
| SELECT (user's all perms) | all columns | `equipment_controller.py` → `GET /api/equipment/permissions` |

**React consuming this:** `useEquipmentPermission.ts` → permission check before control actions  
**Permission levels (ascending):** NONE(0) → VIEW(1) → OPERATE(2) → CONTROL(3) → CONFIGURE(4) → MAINTAIN(5) → ADMIN(6) → FULL_CONTROL(7)

---

### DB Views Used (not base tables)

| View | Schema | Used By |
|------|--------|---------|
| `v_daily_hourly_agg` | `historian_raw` | `report_controller.py` (daily/shift/monthly reports) |
| `active_sessions` | `historian_meta` | `session_controller.py` |
| `user_concurrent_sessions` | `historian_meta` | `session_service.py` |
| `pending_approvals` | `historian_meta` | `approval_controller.py` |
| `user_pending_approvals` | `historian_meta` | `approval_controller.py` |
| `recent_critical_actions` | `historian_meta` | `audit_controller.py` |
| `audit_statistics` | `historian_meta` | `audit_controller.py` |
| `user_activity_summary` | `historian_meta` | `audit_controller.py` |
| `approval_statistics` | `historian_meta` | `approval_controller.py` |

### DB Stored Functions Used

| Function | Called By |
|----------|-----------|
| `historian_meta.log_user_action(...)` | `audit_service.py` (called from everywhere) |
| `historian_meta.create_user_session(...)` | `session_service.py` |
| `historian_meta.update_session_activity(...)` | `session_service.py` |
| `historian_meta.request_critical_operation_approval(...)` | `approval_service.py` |
| `historian_meta.approve_critical_operation(...)` | `approval_service.py` |
| `historian_meta.deny_critical_operation(...)` | `approval_service.py` |

---

## Live Data Flow (WebSocket — No DB Read from Frontend)

The apex-hmi frontend receives ALL live data via WebSocket to `localhost:6001/ws` (not REST):

| WebSocket Event | Data | Source |
|----------------|------|--------|
| `tag_update` | `{tagId: string, value: number/string, timestamp}` | C# OPC → MQTT → WS bridge |
| `mqtt_alarm` | Full alarm object with all fields | C# AlarmEvaluationService → MQTT |
| `active_alarms_snapshot` | Array of all active alarms on connect | WS bridge sends current state |
| `mqtt_interlock` | Full interlock event object | C# InterlockEvaluationService → MQTT |

**No DB query happens for live values in the frontend.** The WebSocket bridge (`mqtt_subscriber_service/websocket_bridge.py`) seeds `active_alarms_snapshot` from in-memory state, NOT from a DB query.

---

## Critical Findings & Decisions Required

### Finding 1: `alarm_active` Table is NOT Used Anywhere

The `alarm_active` table was created by the Phase 1 DB migration but:
- No Flask Python route reads or writes it
- No React component queries it
- The existing HMI uses `historian_events` directly for active alarm list

**Decision needed:** Do we want `alarm_active` as a fast-lookup cache for the C# side only, or should the HMI start reading from it? If C# only → keep it but HMI stays on `historian_events`. If HMI should use it → we need a new Flask route `GET /api/alarms/active` backed by `alarm_active` + update the React `AlarmPanel.tsx`.

### Finding 2: `alarm_audit_trail` Write is Fragile

The HMI writes to `alarm_audit_trail` via `AlarmAuditDAO` imported from `mqtt_subscriber_service`. If that import fails (path issue), **audit writes silently drop**. The 921 existing rows confirm it has worked, but the dependency is brittle.

**Decision needed:** Should `alarm_audit_trail` writes be moved into `alarm_controller.py` directly (inline SQL) to remove the dependency? This makes the system more robust.

### Finding 3: Phase 1 Alarm States WILL Break the HMI

The C# `AlarmStateManager.InitializeSchemaAsync()` will ALTER the `historian_events.alarm_state` CHECK constraint to Phase 1 states. The HMI has these hardcoded old state strings in 7 places:

| File | Line | Old State String | Must Change To |
|------|------|-----------------|----------------|
| `alarm_controller.py` | 125 | `'ACTIVE'` in IN() | `'ACTIVE_UNACK', 'ACTIVE_ACK'` |
| `alarm_controller.py` | 125 | `'ACKNOWLEDGED'` in IN() | `'ACTIVE_ACK'` |
| `alarm_controller.py` | 125 | `'CLEARED'` | `'CLEARED'` ✅ same |
| `alarm_controller.py` | 129 | `'ACTIVE', 'ACKNOWLEDGED'` | `'ACTIVE_UNACK', 'ACTIVE_ACK'` |
| `alarm_controller.py` | 343 | `if alarm_state == 'ACKNOWLEDGED'` | `if alarm_state == 'ACTIVE_ACK'` |
| `alarm_controller.py` | 365 | `SET alarm_state = 'ACKNOWLEDGED'` | `SET alarm_state = 'ACTIVE_ACK'` |
| `alarm_controller.py` | 575 | `if alarm_state != 'ACKNOWLEDGED'` | `if alarm_state != 'ACTIVE_ACK'` |
| `alarm_controller.py` | 603 | `SET alarm_state = 'CLEARED'` | ✅ same |
| `alarm_controller.py` | 751 | `SET alarm_state = 'ACKNOWLEDGED'` | `SET alarm_state = 'ACTIVE_ACK'` |
| `alarm_controller.py` | 806 | `alarm_state = 'ACTIVE'` | `alarm_state IN ('ACTIVE_UNACK','ACTIVE_ACK')` |
| `alarm_controller.py` | 807 | `alarm_state = 'ACKNOWLEDGED'` | `alarm_state = 'ACTIVE_ACK'` |

**Do NOT start the C# server before this HMI is updated. Both must change together.**

### Finding 4: No `public.audit_log` Table Exists

The React `audit-service.ts` POSTs to `/api/audit/log`. The Flask backend routes this to `historian_meta.log_user_action()` stored function which writes to `historian_meta.user_actions_audit`. There is **no `public.audit_log` table** in the system.

### Finding 5: `alarm_audit_trail` vs `historian_events` vs `user_actions_audit`

These three tables are completely separate and non-redundant:

| Table | Purpose | Who Writes | Mutable? |
|-------|---------|-----------|---------|
| `historian_raw.historian_events` | Alarm event journal (one row per alarm raise) | C# `AlarmEvaluationService` | Only alarm_state/ack/clear fields updated |
| `historian_raw.alarm_audit_trail` | Operator action log per alarm (who ACK'd, when, notes) | Flask `alarm_controller.py` via `AlarmAuditDAO` | Append-only |
| `historian_meta.user_actions_audit` | All user actions system-wide (login, control, alarm ops) | Flask `audit_service.py` → DB stored function | Append-only |

### Finding 6: Reports Use a DB View, Not Raw Tables

Daily/Shift/Monthly reports use the `historian_raw.v_daily_hourly_agg` view. This view aggregates `historian_timeseries` data. The reports API (`/api/reports/daily`, `/shift`, `/monthly`) reads from this view only — it does not touch `historian_events`, `alarm_audit_trail`, or any alarm table.

---

## Summary: Table Ownership Map

| Table | Owner (Writes) | HMI (Reads) | HMI (Writes) |
|-------|---------------|-------------|--------------|
| `historian_raw.historian_events` | C# AlarmEvaluationService | ✅ Yes | ⚠️ ACK/CLEAR state only |
| `historian_raw.historian_timeseries` | C# HistorianIngestHostedService | ✅ Yes | ❌ No |
| `historian_raw.alarm_audit_trail` | Flask alarm_controller | ✅ Yes | ✅ Yes (ACK/CLEAR) |
| `historian_raw.alarm_active` | C# AlarmStateManager (Phase 1) | ❌ No | ❌ No |
| `historian_raw.interlock_state_tracking` | C# InterlockEvaluationService | ✅ Yes | ❌ No |
| `historian_raw.trip_event_tracking` | C# trip service | ✅ Yes | ❌ No |
| `historian_meta.tag_master` | C# / manual | ✅ Yes | ❌ No |
| `historian_meta.users` | Flask auth/admin | ✅ Yes | ✅ Full CRUD |
| `historian_meta.roles` | Flask admin | ✅ Yes | ✅ Full CRUD |
| `historian_meta.user_sessions` | Flask session_service | ✅ Yes | ✅ Full lifecycle |
| `historian_meta.user_actions_audit` | Flask audit_service | ✅ Yes | ✅ INSERT always |
| `historian_meta.operation_approvals` | Flask approval_service | ✅ Yes | ✅ Full lifecycle |
| `historian_meta.critical_operations` | Manual/migration | ✅ Yes | ❌ No |
| `historian_meta.role_tag_permissions` | Flask admin | ✅ Yes | ✅ Full CRUD |
| `historian_meta.role_alarm_permissions` | Flask admin | ✅ Yes | ✅ Full CRUD |
| `historian_meta.role_specific_tag_permissions` | Flask admin | ✅ Yes | ✅ Full CRUD |
| `historian_meta.equipment_permissions` | Flask equipment | ✅ Yes | ✅ Full CRUD |

---

## Recommended Next Steps (in order)

1. **BEFORE starting C# server:** Update `alarm_controller.py` to handle both old states (for existing 796 rows) and new Phase 1 states simultaneously — use a DB migration that runs alongside, then switch HMI code atomically
2. **Decide `alarm_active` purpose:** If it's C#-internal only → leave HMI as-is. If HMI should use it → add Flask route backed by `alarm_active` for faster active alarm queries
3. **Fix `alarm_audit_trail` write path:** Move `AlarmAuditDAO` SQL inline into `alarm_controller.py` to eliminate the fragile cross-package import
4. **RTN_UNACK state in HMI:** This is a new ISA-18.2 state the current HMI never shows — decide if `AlarmPanel.tsx` needs a new visual state for "returned but not yet acknowledged"
