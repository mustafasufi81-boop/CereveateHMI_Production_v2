# ISA-101 Trend Settings - Quick Reference Card

## Color Values for SCADA Configuration

### Copy these exact values into your SCADA system:

#### Ignition (Easy Chart)
```python
# Background
system.gui.color(26, 26, 26)

# Trend Lines (Pens)
PEN_1 = system.gui.color(0, 255, 0)     # Green
PEN_2 = system.gui.color(0, 255, 255)   # Cyan
PEN_3 = system.gui.color(255, 255, 0)   # Yellow
PEN_4 = system.gui.color(255, 0, 255)   # Magenta
PEN_5 = system.gui.color(255, 136, 0)   # Orange

# Grid
GRID_MAJOR = system.gui.color(100, 116, 139, 89)  # 35% opacity
GRID_MINOR = system.gui.color(71, 85, 105, 51)    # 20% opacity

# Line Width
PEN_WIDTH = 2.5  # or 3
```

#### WinCC (Trend Control)
```vbs
' Background
BackColor = RGB(26, 26, 26)

' Curves
Curve(0).Color = RGB(0, 255, 0)      ' Green
Curve(1).Color = RGB(0, 255, 255)    ' Cyan
Curve(2).Color = RGB(255, 255, 0)    ' Yellow
Curve(3).Color = RGB(255, 0, 255)    ' Magenta

' Line Width
Curve(0).Width = 2

' Grid
GridMajor.Color = RGB(100, 116, 139)
GridMinor.Color = RGB(71, 85, 105)

' Font
Font.Name = "Segoe UI"
Font.Size = 13
```

#### Wonderware (Trend Object)
```
BackgroundColor:  RGB(26, 26, 26)
Pen1Color:        RGB(0, 255, 0)
Pen2Color:        RGB(0, 255, 255)
Pen3Color:        RGB(255, 255, 0)
Pen4Color:        RGB(255, 0, 255)
PenWidth:         2
GridColor:        RGB(100, 116, 139)
Font:             Arial, 13pt
TimeFormat:       "HH:mm:ss"
ShowGrid:         TRUE
```

#### FactoryTalk (Trend)
```
Background:   DarkGray or RGB(26,26,26)
Pen1.Color:   RGB(0, 255, 0)
Pen1.Width:   3
GridVisible:  True
TimeFormat:   "HH:mm:ss"
Font:         Arial, 13pt
```

---

## Hex Color Codes (for web/CSS)

```css
/* Backgrounds */
--trend-bg-main:   #1a1a1a;
--trend-bg-grid:   #121212;
--trend-bg-yaxis:  #0f1419;

/* Trend Lines */
--trend-pen1:  #00FF00;  /* Green */
--trend-pen2:  #00FFFF;  /* Cyan */
--trend-pen3:  #FFFF00;  /* Yellow */
--trend-pen4:  #FF00FF;  /* Magenta */
--trend-pen5:  #FF8800;  /* Orange */

/* Grid */
--grid-major:  rgba(100, 116, 139, 0.35);
--grid-minor:  rgba(71, 85, 105, 0.2);
--grid-axis:   rgba(59, 130, 246, 0.6);

/* Text */
--text-primary:    #E5E5E5;
--text-labels:     #60a5fa;
--text-units:      #00FF00;
```

---

## Typography Settings

```
Font Family:   Arial, Segoe UI, Tahoma
Axis Labels:   13pt, Bold (700)
Unit Labels:   12pt, Bold (700)
Value Labels:  Consolas, 13pt, Bold
```

---

## Line Settings

```
Trend Line Width:   2.5px  (range: 2-3px)
Grid Major:         1.5px
Grid Minor:         0.8px
Axis Border:        2.0px
Marker Size:        4px (circle)
Anti-aliasing:      ON
```

---

## Time Format

```
Live:         HH:mm:ss           (14:35:22)
With MS:      HH:mm:ss.SSS       (14:35:22.456)
Historical:   MMM DD, HH:mm      (Jan 15, 14:35)
```

---

## Quick Visual Check

✅ **Background is dark** (#1a1a1a)  
✅ **Lines are bright** (Green, Cyan, Yellow)  
✅ **Lines are 2-3px wide**  
✅ **Units shown on Y-axis** [RPM], [°C], [bar]  
✅ **Grid visible but subtle**  
✅ **Markers on data points**  
✅ **Time format consistent**  
✅ **Smooth, anti-aliased lines**  

---

## Support

For full documentation, see: `ISA101_TREND_IMPLEMENTATION_GUIDE.md`
