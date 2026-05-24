# UI Feature Removal — 23 May 2026

## Summary
Five UI features removed permanently from all users (no role exceptions).  
All changes are in the React/Vite frontend only. No backend APIs were removed.  
TypeScript compile errors after changes: **0**

---

## What Was Removed

### 1. ANALYTICS Tab
**File:** `WEB_HMI_MFA/HMI/apex-hmi/src/components/hmi/IndustrialHMIPrototype.tsx`  
**What:** The `⚡ ANALYTICS` tab in the center panel tab bar, and its content (`HmiAnalyticsTab` component).  
**How:** The tab bar was changed from a dynamic `(['trends','analytics','predictive']).map(...)` loop to a single static **TRENDS** button. The `{mainTab === 'analytics' && ...}` conditional block was removed entirely.  
**Imports removed:** `HmiAnalyticsTab` from `./HmiAnalyticsTab`

---

### 2. PREDICTIVE (Pre-Alarm) Tab
**File:** `WEB_HMI_MFA/HMI/apex-hmi/src/components/hmi/IndustrialHMIPrototype.tsx`  
**What:** The `🔮 PREDICTIVE` tab in the center panel, and its content (`PredictiveAlarmPanel` component).  
**How:** Removed as part of the tab bar refactor above. The `{mainTab === 'predictive' && ...}` block was deleted.  
**State removed:** `mainTab` useState variable  
**Imports removed:** `PredictiveAlarmPanel` from `./PredictiveAlarmPanel`

---

### 3. REPORTS Button (Top Navigation Bar)
**File:** `WEB_HMI_MFA/HMI/apex-hmi/src/components/hmi/IndustrialHMIPrototype.tsx`  
**What:** The green `📈 REPORTS` button in the top-right navigation bar linking to `/reports/daily`.  
**How:** Removed the `<Link to="/reports/daily">` wrapper and the `<button>` element inside it. The separator `<div>` before it was also removed.  
**Note:** The Reports pages (`/reports/daily`, `/reports/shift`, `/reports/monthly`) still exist in the router and can be navigated to by URL — only the nav shortcut was removed.

---

### 4. PREDICTIVE ALERTS Panel (Right Side Panel, Below Alarms)
**File:** `WEB_HMI_MFA/HMI/apex-hmi/src/components/hmi/IndustrialHMIPrototype.tsx`  
**What:** The resizable `⚡ PREDICTIVE ALERTS` panel in the right column below the Alarms panel, including the drag-resize handle between Alarms and Predictive Alerts.  
**How:** Removed the entire drag handle `<div>` and the Predictive Alerts `<div>` block (height was `predictiveAlertsHeight` px, default 200px). The Alarms panel now takes full height of the right column.  
**State removed:** `predictiveAlertsHeight` useState, `rightPanelDragRef` useRef  
**Imports removed:** `PredictiveAlertsPanel` from `./PredictiveAlertsPanel`

---

### 5. CSV Download Button (Alarm History Modal)
**File:** `WEB_HMI_MFA/HMI/apex-hmi/src/components/hmi/AlarmHistoryModal.tsx`  
**What:** The green `⬇ CSV` export button in the Alarm History modal header bar.  
**How:** Removed the `<button onClick={exportCSV}>` element. The `exportCSV` function and `Download` icon import remain in the file (no errors) but the button is no longer rendered.  
**Note:** The `exportCSV` function still exists in the file — if re-enabling is needed in future, just re-add the button.

---

### 6. PNG + CSV Export Buttons (Trend Chart)
**File:** `WEB_HMI_MFA/HMI/apex-hmi/src/components/hmi/IndustrialHMIPrototype.tsx`  
**What:** The `PNG` and `CSV` export buttons inside the "Export Controls" toolbar group on each trend chart unit.  
**How:** Removed the entire `{/* Export Controls */}` `<div>` block containing both buttons. The `REF` button (reference lines toggle) in a separate group was kept.  
**Functions remaining (unused):** `exportChartAsPNG` and `exportDataAsCSV` — still defined but no longer called. No TS errors because unused functions don't cause compile errors.

---

## Files Changed

| File | Changes |
|------|---------|
| `src/components/hmi/IndustrialHMIPrototype.tsx` | Removed tabs, REPORTS button, export buttons, predictive alerts panel, unused state/imports |
| `src/components/hmi/AlarmHistoryModal.tsx` | Removed CSV download button |

## Files NOT Changed (backends still intact)
- `controllers/asset_controller.py` — unchanged
- All report page files (`DailyReport.tsx`, `ShiftReport.tsx`, `MonthlyReport.tsx`) — still exist
- `PredictiveAlarmPanel.tsx`, `PredictiveAlertsPanel.tsx`, `HmiAnalyticsTab.tsx` — files still exist, just not imported/used

## Verification
- TypeScript compile errors after all changes: **0**
- Vite hot-reload will apply changes automatically (no rebuild needed)
- Hard-refresh browser (`Ctrl+Shift+R`) to clear cached bundle

---

*Performed by GitHub Copilot on 23 May 2026 at request of Mustafa (Admin)*
