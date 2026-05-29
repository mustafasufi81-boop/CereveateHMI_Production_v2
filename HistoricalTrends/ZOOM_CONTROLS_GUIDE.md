# 🖱️ INTERACTIVE ZOOM CONTROLS - User Guide

## ✅ **NEW FEATURE: Mouse Drag Zoom**

### **How It Works:**

```
┌─────────────────────────────────────────┐
│         CHART AREA                      │
│                                         │
│  👆 Click & Hold anywhere on chart     │
│  ▼ Drag DOWN → 🔍 ZOOM IN (Enlarge)    │
│  ▲ Drag UP   → 🔎 ZOOM OUT (Shrink)    │
│                                         │
│  💡 Live indicator shows zoom %        │
└─────────────────────────────────────────┘
```

---

## 🎮 **ALL ZOOM CONTROLS**

### **1. Mouse Drag** (NEW!)
- **Click** on chart and hold
- **Drag DOWN** ▼ = Zoom IN (enlarge)  
- **Drag UP** ▲ = Zoom OUT (shrink)
- **Visual feedback** shows zoom level in real-time

### **2. Mouse Wheel**
- **Scroll UP** = Zoom IN
- **Scroll DOWN** = Zoom OUT
- Works on both main and correlation charts

### **3. Double Click**
- **Double-click** anywhere on chart
- **Resets zoom** to 100% (original view)
- Shows "↺ Zoom Reset" notification

### **4. Plotly Built-in**
- **Box select** = Drag rectangle to zoom area
- **Pan** = Hold shift + drag to move view
- **Autoscale** = Click autoscale button in Plotly toolbar

### **5. Touch (Mobile/Tablet)**
- **Pinch out** = Zoom IN
- **Pinch in** = Zoom OUT
- Two-finger gestures

---

## 🎨 **VISUAL FEEDBACK**

### **During Drag:**
```
┌─────────────────────────────────┐
│                                 │
│     🔍 ZOOM IN                  │
│        150%                     │
│   ▼ Drag Down: Enlarge         │
│                                 │
└─────────────────────────────────┘
```

### **Zoom Levels:**
- **Minimum**: 10% (0.1x)
- **Normal**: 100% (1.0x)
- **Maximum**: 1000% (10x)

---

## 📊 **USE CASES**

### **1. Examine Details**
Drag down to zoom in on specific time periods
```
Before: See whole day
After: See minute-by-minute details
```

### **2. Compare Patterns**
Zoom out to see long-term trends
```
Before: See 1 hour
After: See full week pattern
```

### **3. Find Anomalies**
Zoom in on suspected problem areas
```
Spot unusual spikes or drops
Analyze exact values at peak moments
```

---

## 🎯 **TIPS & TRICKS**

✅ **Smooth Zooming**: Drag slowly for precise control  
✅ **Quick Zoom**: Drag fast for rapid zoom in/out  
✅ **Reset Quickly**: Double-click to return to 100%  
✅ **Combine Methods**: Use drag + wheel for fine-tuning  
✅ **Mobile Friendly**: All controls work on touch devices  

---

## ⚠️ **IMPORTANT NOTES**

1. **Zoom is independent** for each chart (Main & Correlation)
2. **Zoom persists** until reset or page reload
3. **Works on all chart modes** (Lines, Scatter, Box Plot, etc.)
4. **Live indicator** appears during drag only
5. **Cursor changes** to ↕ (resize) during drag

---

## 🚀 **KEYBOARD SHORTCUTS (Planned)**

Future enhancements:
- **+ key**: Zoom IN
- **- key**: Zoom OUT
- **0 key**: Reset to 100%
- **F key**: Fit to window
- **Ctrl + Wheel**: Horizontal zoom only

---

## 🎓 **EXAMPLES**

### **Example 1: Investigate Production Drop**
1. Load production data
2. See small dip in chart
3. **Drag DOWN** over dip area
4. Chart enlarges to show minute details
5. Identify exact timestamp and value
6. **Double-click** to reset

### **Example 2: View Long-Term Trend**
1. Load 30 days of data
2. Chart looks cluttered
3. **Drag UP** to zoom out
4. See overall pattern clearly
5. Spot weekly cycles
6. **Drag DOWN** on interesting week to examine

### **Example 3: Compare Multiple Parameters**
1. Load Temperature, Pressure, Speed
2. **Drag DOWN** to zoom into specific time
3. See exact correlation at that moment
4. Use mouse wheel for fine adjustment
5. **Double-click** to reset

---

## 🔧 **TECHNICAL DETAILS**

### **Drag Sensitivity:**
- **100 pixels** down = 2x zoom (200%)
- **100 pixels** up = 0.5x zoom (50%)
- **Smooth interpolation** between values

### **Performance:**
- **Optimized** for large datasets (15,000+ points)
- **GPU accelerated** via Plotly
- **No lag** during drag operations

### **Browser Support:**
- ✅ Chrome/Edge (Recommended)
- ✅ Firefox
- ✅ Safari
- ✅ Mobile browsers

---

## 📝 **QUICK REFERENCE**

| Action | Result |
|--------|--------|
| Click + Drag ▼ | Zoom IN (Enlarge) |
| Click + Drag ▲ | Zoom OUT (Shrink) |
| Double Click | Reset to 100% |
| Mouse Wheel ↑ | Zoom IN |
| Mouse Wheel ↓ | Zoom OUT |
| Pinch Out (👆👆) | Zoom IN (Mobile) |
| Pinch In (👆👆) | Zoom OUT (Mobile) |

---

## 💡 **PRO TIPS**

🌟 **Combine with Best/Worst Analysis**: Zoom into peak moments for detailed examination  
🌟 **Use with Anomaly Detection**: Zoom into flagged anomalies to verify  
🌟 **Stack with Filters**: Zoom after filtering specific time ranges  
🌟 **Export Zoomed View**: Take screenshot while zoomed for reports  

---

## 🎉 **ENJOY EXPLORING YOUR DATA!**

The new drag zoom makes data analysis **faster, easier, and more intuitive**!

**Feedback?** Let us know how to improve zoom controls further.
