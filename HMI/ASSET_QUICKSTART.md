# Asset Hierarchy - Quick Start Guide

## ✅ What's Done

Your existing Asset Browser now uses **dynamic data from database** instead of hardcoded values!

## 🚀 Quick Setup (3 Steps)

### 1️⃣ Populate Database Hierarchy
```bash
# Run this SQL file to add hierarchy to your existing tags
psql -h localhost -U cereveate -d Cereveate -f "c:\Shakil\DJangoProjects\NEW_HMI\HMI\migrations\populate_asset_hierarchy.sql"
```

### 2️⃣ Restart Flask Backend
```bash
cd c:\Shakil\DJangoProjects\NEW_HMI\HMI
python app.py
```

### 3️⃣ Refresh Browser
Press `Ctrl + Shift + R` to hard refresh

## 📋 What You'll See

### Before:
```
Northstar Mfg Plant (hardcoded)
├── Raw Material
├── Mixing
│   ├── Mixer M-101 (hardcoded)
│   │   ├── TT-101 Temp
│   │   ├── ST-102 Speed
│   │   └── VT-105 Vibration
```

### After:
```
Northstar Mfg Plant (from database)
├── Mixing
│   └── Mixer M-101
│       ├── Temperature Control (Sub-Equipment)
│       │   └── Temperature Sensor (Component)
│       │       └── TT-101 Temp (Tag) [3 tags badge]
│       ├── Speed Control
│       │   └── Speed Sensor
│       │       └── ST-102 Speed
│       └── Vibration Monitoring
│           └── Vibration Sensor
│               └── VT-105 Vibration 🔴 (Trip indicator)
```

## 🎨 New Visual Features

1. **Tag Count Badges**: Shows number of tags at each level
2. **5-Level Hierarchy**: Plant → Area → Equipment → Sub-Equipment → Component → Tags
3. **Trip Indicators**: Red pulsing dot for safety tags
4. **Dynamic Icons**:
   - 🏭 Plant (Blue)
   - 📊 Area (Green)
   - ⚙️ Equipment (Orange)
   - 💻 Sub-Equipment (Purple)
   - 🔧 Component (Pink)

## 📊 API Endpoints Available

```
GET /api/assets/hierarchy     - Tree structure (your sidebar uses this)
GET /api/assets/flat          - Flat list with full paths
GET /api/assets/stats         - Statistics
```

## 🔧 Add More Assets

Just update tag_master:
```sql
UPDATE historian_meta.tag_master
SET 
    plant = 'Northstar Mfg Plant',
    area = 'Production',
    equipment = 'Reactor R-501',
    sub_equipment = 'Pressure Control',
    components = 'Pressure Sensor'
WHERE tag_id = 'PT-501';
```

Refresh browser → Asset appears in sidebar! ✨

## 🐛 Troubleshooting

**Empty sidebar?**
→ Run populate_asset_hierarchy.sql

**"Failed to fetch"?**
→ Check Flask server running on port 5000

**Still seeing old data?**
→ Hard refresh: Ctrl + Shift + R

## 📖 Full Documentation

See `DYNAMIC_ASSET_INTEGRATION.md` for complete details.
