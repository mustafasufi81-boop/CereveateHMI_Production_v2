# Professional Status Messages for Lakina HMI
**Company:** Lakina (reputation matters!)  
**Date:** May 27, 2026  
**Purpose:** Professional, clear communication with users

---

## 🎯 MESSAGING PRINCIPLES

1. **Be Honest** - Tell users what's happening
2. **Be Professional** - No scary technical jargon
3. **Be Reassuring** - System is designed for this
4. **Be Actionable** - Tell users what to expect

---

## ✅ NORMAL OPERATION MESSAGES

### All Systems Connected
```
🟢 System Operating Normally
   All data sources active
   Real-time updates enabled
```

### Using Backup Connection (REST Fallback)
```
🟡 Operating on Backup Connection
   Real-time feed temporarily unavailable
   Using alternate data source
   Updates every 2 seconds
   
   ℹ️ All data is current and accurate
```

---

## ⚠️ DEGRADED OPERATION MESSAGES

### PLC Disconnected
```
⚠️ Equipment Connection Issue
   PLC "Rockwell Production" - Communication Lost
   Last successful update: 2 minutes ago
   System attempting automatic reconnection
   
   ℹ️ Historical data and other systems remain available
```

### OPC Disconnected  
```
⚠️ Data Source Temporarily Unavailable
   OPC Server connection interrupted
   System using cached values
   Automatic reconnection in progress
   
   ℹ️ Recent data displayed (updated 30 seconds ago)
```

### MQTT Disconnected
```
🟡 Real-Time Updates Paused
   Message broker reconnecting
   Using backup data connection
   
   ℹ️ You will see a brief delay (1-2 seconds) in updates
   ℹ️ All data remains accurate
```

### Multiple Systems Down
```
⚠️ System in Backup Mode
   Primary data sources reconnecting
   Using cached data and alternate connections
   
   ℹ️ Technical team has been notified
   ℹ️ System designed to handle this automatically
```

---

## ❌ CRITICAL MESSAGES (Rare!)

### Complete Data Loss
```
❌ Data Connection Lost
   Unable to retrieve current equipment data
   Technical team notified automatically
   
   📞 For urgent issues: Contact Control Room
   ℹ️ Historical data and reports remain accessible
```

### Database Unavailable
```
⚠️ Historical Data Temporarily Unavailable
   Live monitoring continues normally
   Historical queries disabled
   
   ℹ️ System is recording data for later retrieval
```

---

## 🔄 RECOVERY MESSAGES

### Connection Restored
```
✅ Connection Restored
   "Rockwell Production PLC" reconnected successfully
   Real-time updates resumed
   
   ℹ️ All systems operating normally
```

### Full System Recovery
```
✅ All Systems Operational
   Real-time updates enabled
   All data sources connected
   
   Thank you for your patience
```

---

## 🎨 VISUAL DESIGN GUIDELINES

### Status Indicators
- **Green (🟢)** - All systems normal
- **Yellow (🟡)** - Backup mode, reduced speed
- **Orange (🟠)** - Degraded, some systems offline
- **Red (🔴)** - Critical issue, immediate attention

### Badge Text
- **"LIVE"** - Real-time MQTT feed active
- **"BACKUP"** - Using REST fallback
- **"CACHED"** - Displaying last known values
- **"RECONNECTING"** - Automatic recovery in progress

### Timestamp Display
Always show:
- "Updated: 2 seconds ago" (live)
- "Last update: 5 minutes ago" (degraded)
- "Data from: May 27, 14:30" (cached)

---

## 📊 STATUS DASHBOARD LAYOUT

```
┌─────────────────────────────────────────────────────┐
│  🏭 Lakina Production Monitoring                    │
│                                                      │
│  Status: 🟢 Operating Normally                      │
│  Data Source: LIVE (Real-time)                      │
│  Last Update: 2 seconds ago                         │
│                                                      │
│  System Health:                                      │
│  ├─ 🟢 PLC Connections     (3/3 active)            │
│  ├─ 🟢 OPC Servers         (2/2 connected)         │
│  ├─ 🟢 Message Broker      (connected)             │
│  └─ 🟢 Database           (operational)            │
│                                                      │
│  [ View Details ]                                    │
└─────────────────────────────────────────────────────┘
```

### When Degraded:
```
┌─────────────────────────────────────────────────────┐
│  🏭 Lakina Production Monitoring                    │
│                                                      │
│  Status: 🟡 Backup Connection Active                │
│  Data Source: BACKUP (Automatic fallback)           │
│  Update Delay: ~2 seconds                           │
│                                                      │
│  System Health:                                      │
│  ├─ 🟢 PLC Connections     (3/3 active)            │
│  ├─ 🟢 OPC Servers         (2/2 connected)         │
│  ├─ 🟡 Message Broker      (reconnecting...)       │
│  └─ 🟢 Database           (operational)            │
│                                                      │
│  ℹ️ System operating normally on backup connection  │
│  Real-time feed will restore automatically          │
│                                                      │
│  [ View Details ]                                    │
└─────────────────────────────────────────────────────┘
```

---

## 🔧 TECHNICAL DETAILS (Expandable Section)

**For power users / technicians:**

```
Technical Details:
├─ Active Transport: REST_FALLBACK
├─ MQTT Status: Disconnected (last seen: 45s ago)
├─ SignalR Status: Connected
├─ REST Poll Interval: 1000ms
├─ Cache Size: 1,247 tags
├─ Connected Clients: 8
└─ Backoff Status: Normal (1.0s)
```

**NOT shown to operators by default!**

---

## 🚫 WHAT NOT TO SAY

### ❌ BAD Examples:
- "ERROR: MQTT BROKER DEAD"
- "CRASH DETECTED IN DRIVER"
- "SYSTEM FAILURE"
- "CONNECTION LOST - PANIC!"
- "NULL POINTER EXCEPTION"
- "WORKER THREAD TERMINATED"

### ✅ GOOD Alternatives:
- "Real-time updates paused"
- "Equipment communication issue"
- "System using backup connection"
- "Reconnection in progress"
- "Data source temporarily unavailable"
- "System recovering automatically"

---

## 📱 NOTIFICATION STRATEGY

### Silent Issues (Auto-Handled):
- MQTT reconnection (< 30 seconds)
- REST fallback activation
- Temporary network blips

### Notify User:
- Connection down > 2 minutes
- Multiple systems affected
- Data older than 5 minutes

### Alert Technical Team:
- All connections failed
- Database unavailable
- System not auto-recovering after 10 minutes

---

## 🎯 IMPLEMENTATION CHECKLIST

### API Endpoints Needed:
- ✅ `/api/system-status` (exists)
- ✅ `/api/source-status` (exists)  
- ❌ `/api/health/summary` (simple format for UI)

### UI Components Needed:
- ❌ Status banner (top of page)
- ❌ Connection indicator badges
- ❌ Expandable technical details
- ❌ Toast notifications for changes

### Frontend Logic:
- Poll `/api/system-status` every 5 seconds
- Show banner based on `active_source` field
- Update timestamp display
- Smooth transitions (no flashing)

---

## 🔄 STATE TRANSITIONS

```
NORMAL → DEGRADED
├─ Show yellow banner
├─ Update "Data Source" badge
├─ Increase poll frequency (optional)
└─ Log transition (technical details)

DEGRADED → NORMAL
├─ Show green "Restored" message (5 seconds)
├─ Update banner to green
├─ Resume normal polling
└─ Log recovery

DEGRADED → CRITICAL
├─ Show red banner
├─ Toast notification
├─ Suggest contacting support
└─ Alert technical team (auto)
```

---

**REMEMBER: This is Lakina's reputation. Professional, calm, informative.**
