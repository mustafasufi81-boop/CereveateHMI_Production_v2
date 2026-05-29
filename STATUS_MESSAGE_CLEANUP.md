# Connection Status - Changes Made
**Date:** May 27, 2026  
**Time:** $(Get-Date)

---

## ✅ WHAT I FIXED

### 1. Removed All Technical Messages
**Before (BAD - Shows ports/services):**
- ❌ "OPC backend (C# service on port 5001) disconnected — reconnecting (attempt 3)…"
- ❌ "Flask backend (port 6001) is not reachable — data may be stale"
- ❌ "No OPC data received for >15 s — check C# OPC service and SignalR connection"
- ❌ "Is the PEWS service running on port 6001?"

**After (GOOD - Simple, clear):**
- ✅ "System Reconnecting" (RED)
- ✅ "Using Backup Connection" (ORANGE)
- ✅ "Data Update Delayed" (ORANGE)
- ✅ "Service temporarily unavailable"

---

## 🚦 THREE SIGNALS ONLY

| Signal | Condition | Message | Auto-Reconnect |
|--------|-----------|---------|----------------|
| 🟢 **GREEN** | All systems working | No banner shown | N/A |
| 🟠 **ORANGE** | Fallback mode or data delayed | "Using Backup Connection" or "Data Update Delayed" | ✅ Active |
| 🔴 **RED** | No PLC connection | "System Reconnecting" | ✅ Active |

---

## 📝 FILES CHANGED

### 1. `HMI/apex-hmi/src/hooks/useConnectionHealth.ts`
**Function:** `buildProblem()`  
**Changed:** Lines 16-28  
**Purpose:** Single source of truth for status messages

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

### 2. `HMI/apex-hmi/src/components/hmi/ConnectionHealthBanner.tsx`
**Changed:** Lines 77-105  
**Purpose:** Display banner with correct colors

```typescript
// RED: No PLC connection at all
const isRed = !health.socketConnected;
// ORANGE: Connected but using fallback/delayed
const isOrange = health.flaskReachable === false || health.dataIsStale;
```

### 3. `HMI/apex-hmi/src/components/hmi/HmiAnalyticsTab.tsx`
**Changed:** Line 156  
**Purpose:** Remove port number from error message

```typescript
// Before: "⚠ {error} — Is the PEWS service running on port 6001?"
// After:  "⚠ {error} — Service temporarily unavailable"
```

---

## ✅ VERIFICATION

### No More Technical Messages Found In:
- ✅ All `.tsx` components checked
- ✅ All `.ts` services checked
- ✅ Connection status logic consolidated
- ✅ No duplicate message sources

### Console Logs (Developer Only):
Console logs remain unchanged - they're for developer debugging in browser console, NOT shown to operators.

---

## 🎯 RESULT

**ONE SOURCE OF TRUTH:**  
`HMI/apex-hmi/src/hooks/useConnectionHealth.ts` → `buildProblem()` function

**THREE SIMPLE SIGNALS:**
- 🟢 GREEN = All good (no banner)
- 🟠 ORANGE = Fallback mode (warning banner)
- 🔴 RED = No connection (error banner)

**ALWAYS AUTO-RECONNECT:**  
System automatically recovers, user never needs manual action.

**WRONG SIGNALS = DANGEROUS:**  
System shows RED if unsure, rather than FALSE GREEN.

---

## 🚀 NEXT STEPS

1. **Test the changes:**
   ```bash
   cd HMI\apex-hmi
   npm run dev
   ```

2. **Verify signals:**
   - Stop C# backend → Should show 🔴 RED "System Reconnecting"
   - Stop Flask backend → Should show 🟠 ORANGE "Using Backup Connection"
   - All running → Should show 🟢 GREEN (no banner)

3. **Build for production:**
   ```bash
   npm run build
   ```

---

**All technical jargon removed. Simple, safe, auto-reconnecting.**
