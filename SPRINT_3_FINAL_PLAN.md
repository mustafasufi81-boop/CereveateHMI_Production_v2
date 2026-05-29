# Sprint 3: Professional Connection Status Display
**Company:** Lakina Manufacturing  
**Date:** May 27, 2026  
**Status:** ✅ REALITY-BASED (No Rebuilding Existing Features!)

---

## 🎯 EXECUTIVE SUMMARY

**What We Have:**
- ✅ Mosquitto MQTT Broker (running, PID 6028, port 1883)
- ✅ C# Backend MQTT Publisher (configured, enabled)
- ✅ Python HMI MQTT Client (372 lines, functional)
- ✅ Transport arbitration (MQTT > SignalR > REST)
- ✅ React frontend with `ConnectionHealthBanner.tsx`
- ✅ Health tracking via `useConnectionHealth` hook
- ✅ `/api/system-status` endpoint (comprehensive data)

**What We Need:**
- 🔧 Enhance `ConnectionHealthBanner.tsx` to show **professional** messages (Lakina reputation!)
- 🔧 Add PLC-specific disconnect detection
- 🔧 Add OPC-specific disconnect detection  
- 🔧 Add MQTT broker status display
- 🔧 Add REST fallback indicator
- 🔧 Test end-to-end MQTT flow
- 🔧 Verify Birth/Death messages working

**Sprint Goal:** Professional, reputation-safe status display that shows users connection issues clearly but calmly.

---

## 📊 SPRINT 3 TASK BREAKDOWN

### Phase 1: Backend Enhancement (2 hours)
**Tasks:**
1. ✅ **Verify `/api/system-status` returns all needed data** *(Already exists!)*
   - Current: Returns `mqtt_ok`, `active_source`, `fallback_active`, `plc_mqtt_alive`
   - Status: **COMPLETE** - No changes needed

2. **Add `/api/health/summary` endpoint** *(30 min)*
   - Location: `HMI/app.py` 
   - Purpose: Simple, UI-friendly health summary
   - Returns:
     ```json
     {
       "status": "NORMAL" | "DEGRADED" | "CRITICAL",
       "message": "System Operating Normally",
       "details": {
         "plc_connected": true,
         "opc_connected": true,
         "mqtt_connected": true,
         "active_transport": "MQTT",
         "fallback_active": false,
         "last_update_seconds_ago": 2
       },
       "timestamp": "2026-05-27T14:30:15Z"
     }
     ```

3. **Test MQTT end-to-end flow** *(1 hour)*
   - Start C# backend: `cd CSharpBackend && dotnet run`
   - Start Flask HMI: `cd HMI && python app.py`
   - Subscribe to all topics: `mosquitto_sub -h localhost -t "#" -v`
   - Verify Birth/Death messages appear
   - Verify tag data flows: `plc/Rockwell-Production-PLC/tags/...`
   - Document in `MQTT_TEST_RESULTS.md`

4. **Add detailed PLC disconnect detection** *(30 min)*
   - Location: `HMI/app.py`, `_update_active_source()` function
   - Logic: Track last MQTT message **per PLC**
   - Alert if no data from specific PLC > 60 seconds
   - Return PLC name in `/api/health/summary`

---

### Phase 2: Frontend Enhancement (3 hours)

5. **Create `SystemHealthStatus` TypeScript types** *(15 min)*
   - File: `HMI/apex-hmi/src/types/health.ts`
   ```typescript
   export type SystemStatus = 'NORMAL' | 'DEGRADED' | 'CRITICAL';
   
   export interface HealthSummary {
     status: SystemStatus;
     message: string;
     details: {
       plc_connected: boolean;
       opc_connected: boolean;
       mqtt_connected: boolean;
       active_transport: 'MQTT' | 'SIGNALR' | 'REST' | 'NONE';
       fallback_active: boolean;
       last_update_seconds_ago: number;
       plc_name?: string;  // Which PLC is disconnected
     };
     timestamp: string;
   }
   ```

6. **Create `useSystemHealth` hook** *(30 min)*
   - File: `HMI/apex-hmi/src/hooks/useSystemHealth.ts`
   - Purpose: Poll `/api/health/summary` every 5 seconds
   - Returns: `HealthSummary` + loading/error states
   - Auto-reconnect on errors

7. **Enhance `ConnectionHealthBanner.tsx`** *(1.5 hours)*
   - **Current:** Shows "CONNECTION LOST" / "WARNING" with technical details
   - **New:** Show professional Lakina-appropriate messages
   
   **Changes:**
   - Import `useSystemHealth` hook
   - Replace technical messages with professional ones:
     - ❌ OLD: "OPC backend (C# service on port 5001) disconnected"
     - ✅ NEW: "Equipment Connection Issue - System Reconnecting"
     
     - ❌ OLD: "Flask backend (port 6001) is not reachable"
     - ✅ NEW: "Data Service Temporarily Unavailable"
     
     - ❌ OLD: "No OPC data received for >15 s"
     - ✅ NEW: "Equipment Data Delayed - Monitoring"
   
   - Add transport indicator badge:
     - 🟢 "LIVE" (MQTT active)
     - 🟡 "BACKUP" (REST fallback)
     - 🟠 "DELAYED" (data stale but connected)
     - 🔴 "RECONNECTING" (hard disconnect)
   
   - Add timestamp: "Updated: 2s ago" / "Last data: 5m ago"
   
   - Add expandable "Technical Details" (for admins only):
     ```
     [Show Details ▼]
     ├─ Transport: REST_FALLBACK
     ├─ MQTT Status: Reconnecting (attempt 3)
     ├─ Last MQTT message: 45s ago
     └─ SignalR: Connected
     ```

8. **Create `StatusIndicator` component** *(45 min)*
   - File: `HMI/apex-hmi/src/components/hmi/StatusIndicator.tsx`
   - Purpose: Small badge showing system status in header
   - Displays:
     - 🟢 "LIVE" (green pulse animation)
     - 🟡 "BACKUP" (yellow, no animation)
     - 🔴 "OFFLINE" (red blink)
   - Tooltip on hover shows full status message
   - Click opens full status modal (optional)

---

### Phase 3: Integration & Testing (2 hours)

9. **Add `ConnectionHealthBanner` to main layouts** *(15 min)*
   - Files: 
     - `IndustrialPrototype.tsx`
     - `EnhancedHMI.tsx`
     - Any other HMI pages
   - Import and render at top: `<ConnectionHealthBanner />`

10. **Add `StatusIndicator` to `UserHeader.tsx`** *(15 min)*
    - File: `HMI/apex-hmi/src/components/hmi/UserHeader.tsx`
    - Add next to user menu/logout button
    - Shows continuous system status

11. **Test all disconnect scenarios** *(1 hour)*
    - **Test 1:** Stop Mosquitto MQTT → Should show "Real-Time Updates Paused" + "BACKUP" badge
    - **Test 2:** Stop C# backend → Should show "Equipment Connection Issue" + "RECONNECTING"
    - **Test 3:** Stop Flask → Should show red banner (frontend still works via cache)
    - **Test 4:** Disconnect PLC → Should show "PLC [name] - Communication Lost"
    - **Test 5:** Simulate OPC error → Should show "Data Source Temporarily Unavailable"
    - Document results in `SPRINT_3_TEST_RESULTS.md`

12. **Create user documentation** *(30 min)*
    - File: `USER_STATUS_MESSAGES_GUIDE.md`
    - Explain what each status message means
    - What users should do (usually nothing - auto-recovery)
    - When to contact support (only critical issues)

---

## 📋 IMPLEMENTATION CHECKLIST

### Backend Tasks:
- [ ] Add `/api/health/summary` endpoint to `HMI/app.py`
- [ ] Enhance PLC-specific disconnect tracking
- [ ] Test MQTT end-to-end with `mosquitto_sub`
- [ ] Verify Birth/Death messages sent
- [ ] Document test results

### Frontend Tasks:
- [ ] Create `src/types/health.ts` type definitions
- [ ] Create `src/hooks/useSystemHealth.ts` hook
- [ ] Enhance `ConnectionHealthBanner.tsx` with professional messages
- [ ] Create `StatusIndicator.tsx` component
- [ ] Add banner to all HMI pages
- [ ] Add status indicator to header
- [ ] Test all disconnect scenarios
- [ ] Create user documentation

---

## 🧪 TEST SCENARIOS

### Scenario 1: Normal Operation
```
Given: All systems running
When: User opens HMI
Then: 
  - No banner shown
  - Header shows "LIVE" (green)
  - Tooltip: "System Operating Normally"
```

### Scenario 2: MQTT Disconnected (REST Fallback)
```
Given: Mosquitto stopped
When: System switches to REST
Then:
  - Banner: "🟡 Operating on Backup Connection"
  - Subtext: "Real-time feed temporarily unavailable"
  - Badge: "BACKUP" (yellow)
  - No scary errors!
```

### Scenario 3: PLC Disconnected
```
Given: PLC network cable unplugged
When: No PLC data for 60 seconds
Then:
  - Banner: "⚠️ Equipment Connection Issue"
  - Subtext: "PLC 'Rockwell Production' - Communication Lost"
  - Subtext: "Last successful update: 1 minute ago"
  - Badge: "DELAYED" (orange)
```

### Scenario 4: Complete Outage
```
Given: All backends down
When: No data sources available
Then:
  - Banner: "❌ Data Connection Lost"
  - Subtext: "Unable to retrieve current equipment data"
  - Subtext: "📞 For urgent issues: Contact Control Room"
  - Badge: "OFFLINE" (red)
  - Historical data still viewable
```

### Scenario 5: Recovery
```
Given: MQTT reconnects after being down
When: Data flow resumes
Then:
  - Banner: "✅ Connection Restored" (green, 4 seconds)
  - Subtext: "Real-time updates resumed"
  - Badge: "LIVE" (green pulse)
  - Banner auto-hides after 4 seconds
```

---

## 🎨 DESIGN MOCKUPS

### Normal Operation (No Banner):
```
┌─────────────────────────────────────────────────────────┐
│  🏭 Lakina HMI          [User ▼]  🟢 LIVE  [Logout]    │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  [Normal HMI content - gauges, trends, etc.]            │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Degraded Operation (Backup Mode):
```
┌─────────────────────────────────────────────────────────┐
│  🏭 Lakina HMI          [User ▼]  🟡 BACKUP  [Logout]  │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 🟡 Operating on Backup Connection                │  │
│  │    Real-time feed temporarily unavailable        │  │
│  │    Using alternate data source                    │  │
│  │    ℹ️ All data is current and accurate           │  │
│  │                                    [Reconnect ↻]  │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  [Normal HMI content continues working...]              │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Critical Issue:
```
┌─────────────────────────────────────────────────────────┐
│  🏭 Lakina HMI          [User ▼]  🔴 OFFLINE  [Logout] │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │ ❌ Data Connection Lost                          │  │
│  │    Unable to retrieve current equipment data     │  │
│  │    Technical team notified automatically         │  │
│  │                                                   │  │
│  │    📞 For urgent issues: Contact Control Room    │  │
│  │    ℹ️ Historical data and reports remain         │  │
│  │       accessible                                  │  │
│  │                                    [Reconnect ↻]  │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  [Cached data shown - read-only mode]                   │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## ⏱️ TIME ESTIMATES

| Phase | Task | Time | Difficulty |
|-------|------|------|------------|
| **Phase 1** | Add `/api/health/summary` | 30 min | Easy |
| | Test MQTT end-to-end | 1 hour | Medium |
| | Add PLC disconnect tracking | 30 min | Easy |
| **Phase 2** | Create TypeScript types | 15 min | Easy |
| | Create `useSystemHealth` hook | 30 min | Easy |
| | Enhance `ConnectionHealthBanner` | 1.5 hours | Medium |
| | Create `StatusIndicator` component | 45 min | Easy |
| **Phase 3** | Integration (add to layouts) | 30 min | Easy |
| | Test all scenarios | 1 hour | Medium |
| | User documentation | 30 min | Easy |
| **TOTAL** | | **7 hours** | |

**Team:** 1 developer  
**Duration:** 1 day (with testing)  
**Risk:** Low (enhancing existing, not rebuilding)

---

## 🚀 DEPLOYMENT PLAN

### Step 1: Backend Changes
```bash
cd d:\CereveateHMI_Production\HMI

# 1. Add /api/health/summary endpoint to app.py
# 2. Test locally
python app.py

# 3. Verify endpoint works
curl http://localhost:6001/api/health/summary
```

### Step 2: Frontend Changes
```bash
cd d:\CereveateHMI_Production\HMI\apex-hmi

# 1. Create new files (types, hooks, components)
# 2. Enhance existing ConnectionHealthBanner
# 3. Build production
npm run build

# 4. Test in browser
npm run dev
```

### Step 3: Integration Testing
```bash
# Terminal 1: Start Mosquitto (already running as service)
# Terminal 2: Start C# Backend
cd CSharpBackend
dotnet run

# Terminal 3: Start Flask HMI
cd HMI
python app.py

# Terminal 4: Start React frontend
cd HMI\apex-hmi
npm run dev

# Terminal 5: Monitor MQTT
mosquitto_sub -h localhost -t "#" -v
```

### Step 4: Disconnect Testing
```powershell
# Test 1: Stop Mosquitto
Stop-Service Mosquitto
# → Check UI shows "Backup Connection" message
Start-Service Mosquitto

# Test 2: Stop C# Backend
# → Check UI shows "Equipment Connection Issue"

# Test 3: Simulate PLC disconnect (in C# config)
# → Check UI shows PLC-specific message
```

---

## 📚 DOCUMENTATION DELIVERABLES

1. **MQTT_TEST_RESULTS.md** - End-to-end MQTT flow verification
2. **SPRINT_3_TEST_RESULTS.md** - All disconnect scenarios tested
3. **USER_STATUS_MESSAGES_GUIDE.md** - User-facing documentation
4. **PROFESSIONAL_STATUS_MESSAGES.md** - ✅ Already created!

---

## ✅ SUCCESS CRITERIA

Sprint 3 is complete when:

1. ✅ All disconnect scenarios tested and working
2. ✅ Professional, reputation-safe messages displayed
3. ✅ Users clearly informed of issues without panic
4. ✅ Technical details hidden from operators (expandable for admins)
5. ✅ Auto-recovery working (no manual intervention needed)
6. ✅ MQTT end-to-end verified with `mosquitto_sub`
7. ✅ Birth/Death messages confirmed
8. ✅ User documentation created
9. ✅ No existing features rebuilt or broken!

---

## 🎯 KEY PRINCIPLES

### ✅ DO:
- Show professional, calm messages
- Inform users clearly about status
- Use Lakina-appropriate language
- Auto-recover without user action
- Provide technical details for admins (hidden)
- Test all scenarios thoroughly

### ❌ DON'T:
- Show technical errors to operators
- Use scary language ("CRASH", "ERROR", "DEAD")
- Rebuild existing working features
- Break existing MQTT infrastructure
- Assume services need installation without checking
- Show port numbers/service names to end users

---

**Remember: This is Lakina's reputation. Professional, clear, reassuring.**
