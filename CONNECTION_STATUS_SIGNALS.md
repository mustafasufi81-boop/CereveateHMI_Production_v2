# Connection Status Signals - ONE SOURCE OF TRUTH
**Date:** May 27, 2026  
**Location:** `HMI/apex-hmi/src/hooks/useConnectionHealth.ts`

---

## 🚦 THREE SIGNALS ONLY

### 🟢 GREEN (No Banner) = ALL WELL
- Socket connected ✅
- Flask reachable ✅
- Data flowing ✅
- **Message:** Nothing shown (system working)

### 🟠 ORANGE (Warning Banner) = RUNNING ON FALLBACK
- Socket connected ✅
- BUT Flask unreachable OR data delayed
- **Message:** "Using Backup Connection" OR "Data Update Delayed"
- **Auto-reconnect:** Working in background

### 🔴 RED (Error Banner) = NO PLC CONNECTION AT ALL
- Socket disconnected ❌
- **Message:** "System Reconnecting"
- **Auto-reconnect:** Active, will restore automatically

---

## ⚠️ CRITICAL RULE
**WRONG SIGNALS ARE MORE DANGEROUS THAN TELLING TRUTH**

If system says GREEN but connection is down = DANGEROUS ❌  
If system says RED when it's actually orange = Better safe than sorry ✅

---

## 📍 CODE LOCATIONS (Single Source of Truth)

### Message Logic:
**File:** `HMI/apex-hmi/src/hooks/useConnectionHealth.ts`  
**Function:** `buildProblem()`  
**Lines:** 16-28

```typescript
function buildProblem(h: MQTTHealth): string | null {
    // RED: No connection at all
    if (!h.socketConnected)
        return 'System Reconnecting';
    
    // ORANGE: Connected but using fallback
    if (h.flaskReachable === false)
        return 'Using Backup Connection';
    if (h.dataIsStale)
        return 'Data Update Delayed';
    
    // GREEN: All good
    return null;
}
```

### Display Logic:
**File:** `HMI/apex-hmi/src/components/hmi/ConnectionHealthBanner.tsx`  
**Lines:** 77-85

```typescript
// RED: No PLC connection at all
const isRed = !health.socketConnected;
// ORANGE: Connected but using fallback/delayed
const isOrange = health.flaskReachable === false || health.dataIsStale;
```

---

## 🔍 NO OTHER MESSAGE SOURCES

All connection status messages come from these 2 files ONLY:
1. `useConnectionHealth.ts` - Defines what message to show
2. `ConnectionHealthBanner.tsx` - Shows the message

**NO duplicated logic anywhere else!**

---

## ✅ AUTO-RECONNECT ALWAYS ACTIVE

User never needs to do anything manually. System automatically:
1. Detects disconnection
2. Shows appropriate signal (RED or ORANGE)
3. Reconnects in background
4. Returns to GREEN when restored

**"Retry" button is optional** - system reconnects automatically anyway.

---

## 📊 TESTING

### Test 1: Stop Flask (Orange)
```powershell
# Stop Flask backend
cd HMI
# Kill python process
```
**Expected:** 🟠 "Using Backup Connection"

### Test 2: Stop C# Backend (Red)
```powershell
# Stop C# backend
Stop-Process -Name "OpcDaWebBrowser"
```
**Expected:** 🔴 "System Reconnecting"

### Test 3: All Running (Green)
```powershell
# Both backends running
```
**Expected:** No banner shown

---

**Remember: Simple is safe. Three signals. One source of truth. Always auto-reconnect.**
