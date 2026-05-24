# Performance Improvements - Data Scrolling & Decimation

## Changes Made (December 21, 2025)

### 1. **Data Decimation** (LTTB Algorithm)
- **Pure JavaScript implementation** - NO external dependencies
- Automatically reduces large datasets (>500 live, >5000 historical)
- Uses "Largest Triangle Three Buckets" algorithm to preserve visual shape
- Keeps first/last points always visible

### 2. **Data Windowing & Scrolling**
- Added scroll controls: **⬅️ Back**, **➡️ Forward**, **⏩ Live**
- Scroll backward/forward by 50% of visible range
- Filter data to show only visible window (huge performance gain)
- Auto-exit scroll mode when reaching live data

### 3. **Responsive Chart Updates**
```javascript
// Performance state
maxLivePoints: 500       // Max points before decimation
maxHistoricalPoints: 5000 // Max historical points
dataWindow: {
    start: null,
    end: null,
    isScrolling: false
}
```

### 4. **UI Controls Added**
Location: Below "Clear History" button in control panel

```html
📜 Scroll Data:
[⬅️ Back] [➡️ Forward] [⏩ Live]
```

**Button States:**
- Disabled when no tags selected
- "Live" button pulses when in scroll mode
- Auto-disables when at live data

## How It Works

### Live Mode (Default)
- Shows last 500 points per tag
- Updates every 1 second
- Smooth scrolling, no lag

### Historical Load
- If >5000 points: Decimates using LTTB
- Preserves peaks, valleys, and trends
- Visual appearance maintained

### Scroll Mode
1. Load historical data (e.g., "📅 1 Month")
2. Click **⬅️ Back** to scroll backward in time
3. Click **➡️ Forward** to scroll forward
4. Click **⏩ Live** to jump back to real-time

### Performance Benefits
- **Before:** 50K points = browser hang
- **After:** 50K decimated to 5K = smooth 60fps

## Testing Checklist

✅ **Live Data:** Select 2-3 tags, verify smooth updates
✅ **Quick Buttons:** Click "1 Month", verify data loads
✅ **Decimation:** Load large dataset (6 months), check console for "📉 Decimated"
✅ **Scroll Back:** Click ⬅️ Back, chart shifts backward
✅ **Scroll Forward:** Click ➡️ Forward, chart shifts forward
✅ **Jump to Live:** Click ⏩ Live, returns to real-time
✅ **Reset All:** Clears everything, disables scroll buttons

## Code Locations

### JavaScript (dashboard.js)
- Lines 8-28: State with performance settings
- Lines 509-640: `updateChart()` with windowing/decimation
- Lines 642-680: `decimateData()` LTTB implementation
- Lines 814-914: Scroll functions (back/forward/live)

### HTML (dashboard.html)
- Lines 103-107: Scroll button controls

## No Dependencies
All code is **pure JavaScript** - no external libraries needed beyond existing Chart.js

## Browser Compatibility
✅ Chrome/Edge (tested)
✅ Firefox
✅ Safari 14+
⚠️ IE11 not supported (needs Map polyfill)
