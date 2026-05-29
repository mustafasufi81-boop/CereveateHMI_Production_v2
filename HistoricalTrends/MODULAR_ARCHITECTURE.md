# 🏗 MODULAR ARCHITECTURE - File Structure

```
HistoricalTrends/
├── static/
│   ├── modules/
│   │   ├── data_processor.js      ✅ Data transformations & calculations
│   │   ├── chart_renderer.js      ✅ All Plotly visualizations
│   │   ├── ui_manager.js          🔄 UI controls & state management
│   │   ├── normalization.js       🔄 Normalization engine
│   │   └── multi_analysis.js      🔄 Multi-parameter analysis
│   ├── trends.js                  🔄 Main coordinator
│   └── styles.css
├── templates/
│   └── trends.html                🔄 HTML structure
├── app.py                          ✅ Flask API
├── parquet_service.py              ✅ Data loading
└── config_reader.py                ✅ Configuration

```

## ✅ **COMPLETED MODULES**

### **1. data_processor.js**
- `normalizeToScale()` - Normalize to 0-100%
- `calculateStats()` - Statistical calculations
- `detectAnomalies()` - 3-sigma detection
- `findPeakMoment()` - Best/Worst finder
- `getWindowData()` - Time window extraction
- `calculateParameterStatsAtMoment()` - Parameter analysis

### **2. chart_renderer.js**
- `renderMultiScaleChart()` - Multi Y-axis support
- `renderBoxPlot()` - Box plot visualization
- `renderDistribution()` - Histogram + Normal curve
- `renderBestWorstComparison()` - Best vs Worst bars

---

## 🔄 **NEXT MODULES TO CREATE**

### **3. ui_manager.js** - UI State & Controls
```javascript
- manageNormalizationToggle()
- manageMultiParameterSelection()
- updateChartModeButtons()
- handleExportOptions()
- showLoadingIndicator()
- displayErrorMessages()
```

### **4. normalization.js** - Advanced Normalization
```javascript
- normalizeToPercentage()     // 0-100%
- normalizeToZScore()          // Z-score standardization
- normalizeToMinMax()          // Custom range
- normalizeToDecibel()         // Logarithmic scale
- batchNormalize()             // Multiple tags at once
```

### **5. multi_analysis.js** - Multi-Parameter Analysis
```javascript
- selectInputParameters()      // Choose input tags
- selectOutputParameters()     // Choose output tags
- analyzeInputOutputRelation() // Correlation analysis
- generateComparisonMatrix()   // Cross-parameter comparison
- exportAnalysisReport()       // PDF/Excel export
```

---

## 🎯 **KEY FEATURES**

### **Feature 1: Multi-Scale Plotting** ✅ IMPLEMENTED
**Problem**: Parameters with different scales (0-10 vs 0-1000) hard to compare
**Solution**: Each parameter gets its own Y-axis
```
Y1 (left)  │ Temperature (0-100°C)
Y2 (right) │ Pressure (0-150 PSI)
Y3 (left)  │ Speed (1000-2000 RPM)
```

### **Feature 2: Normalization** ✅ IMPLEMENTED
**Problem**: Want to see relative changes, not absolute values
**Solution**: Scale all to 0-100%
```
Original: Temp=85°C, Pressure=120PSI, Speed=1850RPM
Normalized: Temp=85%, Pressure=80%, Speed=85%
```

### **Feature 3: Input/Output Analysis** 🔄 TO IMPLEMENT
**Problem**: "Which inputs affect which outputs?"
**Solution**: Multi-parameter correlation
```
INPUTS (Control):    OUTPUTS (Results):
- Temperature        - Production
- Pressure           - Quality
- Speed              - Energy

Analysis shows:
Speed → Production (r=0.92) STRONG!
Temperature → Quality (r=0.65) MODERATE
Pressure → Energy (r=0.34) WEAK
```

### **Feature 4: Custom Time Extraction** 🔄 TO IMPLEMENT
**Problem**: "Show me all timestamps where X > threshold"
**Solution**: Filter and export specific moments
```
Find all moments where:
- Production > 1000 AND
- Vibration < 0.3

Result: 847 timestamps exported
```

---

## 🐛 **FIXES NEEDED**

### **1. Distribution Page Error** ❌ CAUSING OUT OF MEMORY
**Issue**: Too many data points (15,000+) causing browser crash
**Fix**: Implement downsampling for large datasets
```javascript
if (data.length > 5000) {
    data = downsampleData(data, 5000);  // Reduce to 5000 points
}
```

### **2. Multi-Scale Support** ❌ NOT WORKING
**Issue**: All parameters share one Y-axis
**Fix**: Implement multiple Y-axes (already in chart_renderer.js)

### **3. Normalization Toggle** ❌ NOT IN UI
**Issue**: No button to enable normalization
**Fix**: Add checkbox in control panel

---

## 📋 **IMPLEMENTATION PLAN**

### **Phase 1: Core Fixes** (PRIORITY)
1. ✅ Create data_processor.js
2. ✅ Create chart_renderer.js
3. 🔄 Fix distribution memory error (downsample)
4. 🔄 Add normalization checkbox to UI
5. 🔄 Integrate multi-scale rendering

### **Phase 2: UI Enhancement**
6. 🔄 Create ui_manager.js
7. 🔄 Add Input/Output parameter selection
8. 🔄 Add custom time range filtering
9. 🔄 Add export functionality

### **Phase 3: Advanced Analysis**
10. 🔄 Create multi_analysis.js
11. 🔄 Implement correlation matrix
12. 🔄 Implement custom queries
13. 🔄 Add PDF report generation

---

## 🎨 **NEW UI LAYOUT**

```html
┌─────────────────────────────────────────────────────────┐
│  CONTROL PANEL                                          │
├─────────────────────────────────────────────────────────┤
│  Date Range: [Start] to [End]                          │
│                                                         │
│  Available Tags: (Select Multiple)                     │
│  ☑ Temperature   ☑ Pressure   ☑ Speed   □ Vibration    │
│                                                         │
│  ┌──────────────────┐  ┌─────────────────────────┐    │
│  │ INPUT PARAMS     │  │ OUTPUT PARAMS           │    │
│  │ ☑ Temperature    │  │ ☑ Production            │    │
│  │ ☑ Pressure       │  │ ☑ Quality               │    │
│  │ ☑ Speed          │  │ □ Energy                │    │
│  └──────────────────┘  └─────────────────────────┘    │
│                                                         │
│  Display Options:                                      │
│  ☑ Normalize to 0-100%                                 │
│  ☑ Multi-Scale (Separate Y-axes)                       │
│  ☑ Show Grid                                            │
│                                                         │
│  [📈 Load Data] [📊 Analyze] [💾 Export]               │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  CHART MODES                                            │
│  ○ Lines  ○ Scatter  ○ Box Plot  ○ Distribution        │
│  ○ Anomaly  ○ Correlation  ○ Best/Worst  ○ Multi-Axis  │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  MAIN CHART AREA                                        │
│                                                         │
│  [Interactive Plotly Chart]                             │
│                                                         │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  ANALYSIS RESULTS                                       │
│  Statistics | Correlations | Insights | Export         │
└─────────────────────────────────────────────────────────┘
```

---

## 💡 **BENEFITS OF MODULAR APPROACH**

### **1. Debugability** ✅
- Each module has single responsibility
- Easy to test individually
- Clear error messages

### **2. Performance** ✅
- Load only needed modules
- Optimize specific functions
- Downsample large datasets

### **3. Maintainability** ✅
- Add new features without breaking existing
- Update one module at a time
- Clear code organization

### **4. Scalability** ✅
- Add new chart types easily
- Add new analysis methods
- Extend normalization options

---

## 🚀 **NEXT STEPS**

1. **Immediate**: Fix distribution memory error
2. **Quick Win**: Add normalization checkbox
3. **Impact**: Implement multi-scale rendering
4. **Advanced**: Add Input/Output analysis

Would you like me to proceed with implementing these in order?
