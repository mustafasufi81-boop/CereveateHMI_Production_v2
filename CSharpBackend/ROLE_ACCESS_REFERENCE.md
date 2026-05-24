# Role Access Reference — Cereveate HMI Platform

> **Last updated:** May 24, 2026  
> **Source of truth:** `historian_meta` schema in `Automation_DB`  
> **How to change:** Admin Panel → Users → select role → Permissions tab

---

## How to Configure Each Permission

| Permission Type | Where to Change | DB Table |
|---|---|---|
| Module access (HMI, Reports, Analytics, Alarms, Admin) | Admin Panel → Role → Permissions → **Module Permissions Matrix** | `historian_meta.role_module_permissions` |
| Alarm actions (ACK, Silence, Clear) | Admin Panel → Role → Permissions → *(no UI yet — use SQL below)* | `historian_meta.role_alarm_permissions` |
| Plant / Area access for Reports | Admin Panel → Role → Permissions → **Plant & Area Access** | `historian_meta.role_tag_permissions` |
| Specific tag access | Admin Panel → Role → Permissions → **Specific Tag Access** | `historian_meta.role_tag_permissions` |

---

## 1. Module Permissions

Controls which modules each role can **see and use** in the HMI.

| Module | Action | Admin | Operator | Engineer | Viewer |
|---|---|:---:|:---:|:---:|:---:|
| **HMI** | View (see HMI tab) | ✅ | ✅ | ✅ | ✅ |
| | Operate (write setpoints) | ✅ | ❌ | ❌ | ❌ |
| | Generate | ✅ | ❌ | ❌ | ❌ |
| | Configure | ✅ | ❌ | ❌ | ❌ |
| **Reports** | View (see Reports button) | ✅ | ✅ | ✅ | ❌ |
| | Operate | ✅ | ❌ | ✅ | ❌ |
| | Generate (Download Excel/CSV) | ✅ | ✅ | ✅ | ❌ |
| | Configure | ✅ | ❌ | ❌ | ❌ |
| **Analytics** | View (see Analytics/Predictive tabs) | ✅ | ❌ | ✅ | ❌ |
| | Operate | ✅ | ❌ | ❌ | ❌ |
| | Generate | ✅ | ❌ | ❌ | ❌ |
| | Configure | ✅ | ❌ | ❌ | ❌ |
| **Alarms** | View (see alarm list) | ✅ | ✅ | ✅ | ✅ |
| | Operate (ACK button in panel) | ✅ | ✅ | ❌ | ❌ |
| | Generate | ✅ | ✅ | ❌ | ❌ |
| | Configure | ✅ | ✅ | ❌ | ❌ |
| **Admin** | View (see Admin menu) | ✅ | ❌ | ❌ | ❌ |
| | Operate | ✅ | ❌ | ❌ | ❌ |
| | Generate | ✅ | ❌ | ❌ | ❌ |
| | Configure | ✅ | ❌ | ❌ | ❌ |

> **Change via:** Admin Panel → select role → Permissions tab → Module Permissions Matrix → toggle checkboxes → Save

---

## 2. Alarm Action Permissions

Controls what actions each role can perform on individual alarms (all 4 alarm categories: PROCESS, EQUIPMENT, SAFETY, GENERAL).

| Action | Admin | Operator | Engineer | Viewer |
|---|:---:|:---:|:---:|:---:|
| **View** alarm list | ✅ | ✅ | ✅ | ✅ |
| **Acknowledge** (ACK button) | ✅ | ✅ | ✅ | ❌ |
| **Silence** alarm | ✅ | ✅ | ✅ | ❌ |
| **Clear** alarm | ✅ | ✅ | ❌ | ❌ |
| Requires approval to clear | ❌ | ❌ | ❌ | ❌ |

> **Change via SQL** (no Admin UI panel yet):
> ```sql
> UPDATE historian_meta.role_alarm_permissions
> SET can_clear = TRUE
> WHERE role_id = (SELECT id FROM historian_meta.roles WHERE name = 'Engineer')
>   AND alarm_category = 'PROCESS';
> ```

---

## 3. Plant / Area Access (Report Data Visibility)

Controls which plant+area combinations a role can **see data for** in Reports.  
If a role has no rows here → **Reports show empty results** for that role.

| Plant | Area | Admin | Operator | Engineer | Viewer |
|---|---|:---:|:---:|:---:|:---:|
| BlastFurnace | Equipment | ✅ | ✅ | ✅ | ✅ |
| FTP-1 | POTLINE | ✅ | ✅ | ✅ | ❌ |
| PLANT_001 | AREA_A | ✅ | ✅ | ✅ | ✅ |
| Plant_A | Area-2 | ✅ | ✅ | ✅ | ❌ |
| Plant_A | Control_Systems | ✅ | ✅ | ✅ | ✅ |
| Plant1 | Area-2 | ✅ | ✅ | ✅ | ❌ |
| Plant1 | Area1 | ✅ | ✅ | ✅ | ❌ |
| Plant1 | Production | ✅ | ✅ | ✅ | ❌ |
| PowerPlant | Equipment | ✅ | ✅ | ✅ | ❌ |

> **Change via:** Admin Panel → select role → Permissions tab → **Plant & Area Access** section  
> - Click a Plant/Area button to **add** access  
> - Click 🗑 trash icon next to a row to **remove** access  
> - "All Plants/Areas" button grants access to everything at once

---

## 4. Quick Summary per Role

### 🔴 Admin
- **Full access to everything** — all modules, all alarms (view/ACK/silence/clear), all plants/areas
- Only role with `is_admin = TRUE` in the DB (bypasses all permission checks automatically)
- Can access the Admin Panel to manage other roles

### 🟠 Operator
- **HMI:** View only (no write/setpoint changes)
- **Reports:** View + Generate (Download Excel) — all 9 plants/areas
- **Analytics:** ❌ No access (Analytics/Predictive tabs hidden)
- **Alarms:** View + ACK + Silence + **Clear** ✅
- **Admin Panel:** ❌ No access

### 🔵 Engineer
- **HMI:** View only
- **Reports:** View + Operate + Generate (Download Excel) — all 9 plants/areas
- **Analytics:** ✅ View (Analytics + Predictive tabs visible)
- **Alarms:** View + ACK + Silence — **cannot Clear** ❌
- **Admin Panel:** ❌ No access

### ⚪ Viewer
- **HMI:** View only
- **Reports:** ❌ No access (Reports button hidden)
- **Analytics:** ❌ No access
- **Alarms:** View only — cannot ACK/Silence/Clear
- **Admin Panel:** ❌ No access
- **Plant access:** Only BlastFurnace/Equipment, PLANT_001/AREA_A, Plant_A/Control_Systems

---

## 5. SQL Reference — Direct DB Changes

Use these if the Admin UI is not available or for bulk changes.

### Grant/revoke a module permission
```sql
-- Grant Operator access to Analytics
UPDATE historian_meta.role_module_permissions
SET can_view = TRUE
WHERE role_id = (SELECT id FROM historian_meta.roles WHERE name = 'Operator')
  AND module = 'analytics';
```

### Grant all alarm actions to a role
```sql
UPDATE historian_meta.role_alarm_permissions
SET can_acknowledge = TRUE, can_silence = TRUE, can_clear = TRUE
WHERE role_id = (SELECT id FROM historian_meta.roles WHERE name = 'Engineer');
```

### Grant all plants/areas to a role
```sql
INSERT INTO historian_meta.role_tag_permissions (role_id, plant, area, can_view, can_write)
SELECT (SELECT id FROM historian_meta.roles WHERE name = 'Viewer'), plant, area, TRUE, FALSE
FROM (SELECT DISTINCT plant, area FROM historian_meta.tag_master WHERE plant IS NOT NULL AND area IS NOT NULL) AS t
ON CONFLICT (role_id, plant, area) DO UPDATE SET can_view = TRUE;
```

### Remove a plant/area from a role
```sql
DELETE FROM historian_meta.role_tag_permissions
WHERE role_id = (SELECT id FROM historian_meta.roles WHERE name = 'Viewer')
  AND plant = 'FTP-1' AND area = 'POTLINE';
```

### View current state of all permissions
```sql
-- Module permissions
SELECT r.name, rmp.module, rmp.can_view, rmp.can_operate, rmp.can_generate, rmp.can_configure
FROM historian_meta.role_module_permissions rmp
JOIN historian_meta.roles r ON r.id = rmp.role_id
ORDER BY r.name, rmp.module;

-- Alarm permissions
SELECT r.name, rap.alarm_category, rap.can_view, rap.can_acknowledge, rap.can_silence, rap.can_clear
FROM historian_meta.role_alarm_permissions rap
JOIN historian_meta.roles r ON r.id = rap.role_id
ORDER BY r.name, rap.alarm_category;

-- Plant/area access
SELECT r.name, rtp.plant, rtp.area, rtp.can_view
FROM historian_meta.role_tag_permissions rtp
JOIN historian_meta.roles r ON r.id = rtp.role_id
ORDER BY r.name, rtp.plant, rtp.area;
```

---

> **Note:** Module permission changes take effect on **next login** (token refresh).  
> Alarm and plant/area permission changes take effect **immediately** (checked live on each request).
