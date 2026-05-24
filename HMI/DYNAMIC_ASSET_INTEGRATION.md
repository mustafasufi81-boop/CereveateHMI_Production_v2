# Dynamic Asset Hierarchy - Integration Guide

## Overview
Your existing Asset Browser left panel now displays **dynamic asset taxonomy** from `historian_meta.tag_master` instead of static hardcoded data.

## What Changed

### Before (Static)
```typescript
const assetTree = {
  name: "Northstar Mfg Plant",  // Hardcoded
  children: [...]               // Static structure
}
```

### After (Dynamic)
```typescript
// Fetches from /api/assets/hierarchy
// Data comes from tag_master columns:
Plant → Area → Equipment → Sub-Equipment → Component → Tags
```

## Files Modified

### 1. Backend API
- **File**: `c:\Shakil\DJangoProjects\NEW_HMI\HMI\controllers\asset_controller.py`
- **Added**: Complete asset hierarchy API
- **Registered**: In `app.py` as `asset_bp`

### 2. Frontend Component
- **File**: `c:\Shakil\DJangoProjects\NEW_HMI\apex-hmi\src\components\hmi\AssetSidebar.tsx`
- **Changed**: 
  - Removed static `assetTree` constant
  - Added `useEffect` hook to fetch from API
  - Added loading state
  - Added support for 5 hierarchy levels
  - Added tag count badges
  - Shows individual tags under components

### 3. Database Migration
- **File**: `c:\Shakil\DJangoProjects\NEW_HMI\HMI\migrations\populate_asset_hierarchy.sql`
- **Purpose**: Populate hierarchy for existing tags

## Setup Steps

### Step 1: Run Database Migration (IMPORTANT!)

Open PostgreSQL and run:
```bash
psql -h localhost -U cereveate -d Cereveate -f "c:\Shakil\DJangoProjects\NEW_HMI\HMI\migrations\populate_asset_hierarchy.sql"
```

Or in pgAdmin:
1. Open Query Tool
2. Load file: `populate_asset_hierarchy.sql`
3. Execute

This will populate the hierarchy columns for your existing tags (TT-101, ST-102, VT-105, etc.)

### Step 2: Restart Flask Backend

```bash
cd c:\Shakil\DJangoProjects\NEW_HMI\HMI
python app.py
```

The new `/api/assets/hierarchy` endpoint is now available.

### Step 3: Rebuild React Frontend (if needed)

```bash
cd c:\Shakil\DJangoProjects\NEW_HMI\apex-hmi
npm run build
# or for dev
npm run dev
```

### Step 4: Clear Browser Cache

- Hard refresh: `Ctrl + Shift + R`
- Or clear cache completely

## Visual Changes

### Hierarchy Icons
- 🏭 **Plant** (Factory) - Blue
- 📊 **Area** (Layers) - Green  
- ⚙️ **Equipment** (Cog) - Orange
- 💻 **Sub-Equipment** (Cpu) - Purple
- 🔧 **Component** (Component) - Pink
- 📈 **Tag** (Activity) - Gray

### New Features
1. **Tag Count Badges**: Shows number of tags at each level
2. **Dynamic Loading**: Fetches from database on page load
3. **Auto-Expand**: First plant auto-expands on load
4. **Trip Indicators**: Red pulsing dot for tags with trip_category
5. **Criticality Levels**: Shows equipment_criticality (1-5)

## Database Schema Used

```sql
SELECT 
    tag_id,           -- Tag identifier
    tag_name,         -- Display name
    plant,            -- Level 1: Plant
    area,             -- Level 2: Area
    equipment,        -- Level 3: Equipment
    sub_equipment,    -- Level 4: Sub-Equipment (NEW!)
    components,       -- Level 5: Component (NEW!)
    trip_category,    -- Shows red indicator
    equipment_criticality  -- 1-5 scale
FROM historian_meta.tag_master
WHERE enabled = true
```

## Hierarchy Structure

```
Northstar Mfg Plant (Plant)
├── Raw Material (Area)
│   └── Material Handler (Equipment)
│       └── Conveyor System (Sub-Equipment)
│           └── Sensors (Component)
│               └── [Tags here]
│
├── Mixing (Area)
│   ├── Mixer M-101 (Equipment)
│   │   ├── Temperature Control (Sub-Equipment)
│   │   │   └── Temperature Sensor (Component)
│   │   │       └── TT-101 Temp (Tag)
│   │   ├── Speed Control (Sub-Equipment)
│   │   │   └── Speed Sensor (Component)
│   │   │       └── ST-102 Speed (Tag)
│   │   └── Vibration Monitoring (Sub-Equipment)
│   │       └── Vibration Sensor (Component)
│   │           └── VT-105 Vibration (Tag) 🔴
│   ├── Pump P-201 (Equipment)
│   └── Tank T-305 (Equipment)
│
└── Packaging (Area)
    └── Packaging Line (Equipment)
```

## API Response Format

```json
{
  "hierarchy": [
    {
      "id": "plant_Northstar Mfg Plant",
      "name": "Northstar Mfg Plant",
      "type": "plant",
      "tag_count": 3,
      "children": [
        {
          "id": "area_Northstar Mfg Plant_Mixing",
          "name": "Mixing",
          "type": "area",
          "tag_count": 3,
          "children": [
            {
              "id": "equip_..._Mixer M-101",
              "name": "Mixer M-101",
              "type": "equipment",
              "tag_count": 3,
              "children": [
                {
                  "id": "subequip_..._Temperature Control",
                  "name": "Temperature Control",
                  "type": "sub_equipment",
                  "tag_count": 1,
                  "children": [
                    {
                      "id": "comp_..._Temperature Sensor",
                      "name": "Temperature Sensor",
                      "type": "component",
                      "tag_count": 1,
                      "tags": [
                        {
                          "tag_id": "TT-101",
                          "tag_name": "Temperature Sensor",
                          "data_type": "Float",
                          "eng_unit": "°C",
                          "trip_category": "PROCESS_TRIP",
                          "criticality": 4
                        }
                      ]
                    }
                  ]
                }
              ]
            }
          ]
        }
      ]
    }
  ],
  "statistics": {
    "total_tags": 3,
    "filtered_tags": 0,
    "plants": 1
  }
}
```

## Adding New Assets

Simply update the tag_master table:

```sql
-- Add new equipment
UPDATE historian_meta.tag_master
SET 
    plant = 'Northstar Mfg Plant',
    area = 'Production',
    equipment = 'Reactor R-501',
    sub_equipment = 'Pressure Control',
    components = 'Pressure Transmitter',
    equipment_criticality = 5
WHERE tag_id = 'PT-501';
```

The Asset Browser will automatically show it on next page load/refresh!

## RBAC Integration

The hierarchy respects user permissions:
- Users only see plants/areas they have access to
- Filtered by `role_tag_permissions` table
- Filtered count shown in statistics

## Troubleshooting

### Issue: Empty hierarchy
**Solution**: Run the populate_asset_hierarchy.sql script

### Issue: "Failed to fetch asset hierarchy"
**Solution**: 
1. Check Flask server is running
2. Check token in localStorage
3. Check browser console for errors

### Issue: No tags showing under components
**Solution**: 
1. Verify tags have `enabled = true`
2. Check hierarchy columns are populated
3. Run: `SELECT * FROM historian_meta.tag_master WHERE enabled = true`

### Issue: Still seeing old static data
**Solution**: 
1. Hard refresh: `Ctrl + Shift + R`
2. Clear browser cache
3. Check if React app rebuilt

## Testing

### Test API Endpoint
```bash
# Get auth token first
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}'

# Test hierarchy endpoint
curl http://localhost:5000/api/assets/hierarchy \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Test in Browser Console
```javascript
// Check if API is accessible
fetch('/api/assets/hierarchy', {
  headers: {
    'Authorization': `Bearer ${localStorage.getItem('token')}`
  }
})
.then(r => r.json())
.then(d => console.log(d));
```

## Performance

- **Single Query**: All data fetched in one DB query
- **Client-side Filtering**: RBAC applied in Python
- **Caching**: Consider adding Redis cache for large datasets
- **Auto-refresh**: Add WebSocket for real-time updates

## Future Enhancements

1. **Search**: Add search box to filter hierarchy
2. **Drag & Drop**: Reorganize assets
3. **Context Menu**: Right-click for actions
4. **Favorites**: Star frequently used equipment
5. **Recent**: Show recently viewed assets
6. **Badges**: Show alarm count per level
7. **Health Icons**: Green/yellow/red status indicators

## Rollback (if needed)

If you need to revert to static data:

```bash
git checkout c:\Shakil\DJangoProjects\NEW_HMI\apex-hmi\src\components\hmi\AssetSidebar.tsx
```

Or manually restore the static `assetTree` constant.
