# Asset Hierarchy Display - Implementation Guide

## Overview
This implementation provides a complete asset hierarchy browser based on the 5-level taxonomy in `historian_meta.tag_master`:

```
Plant → Area → Equipment → Sub-Equipment → Component → Tags
```

## Architecture

### Backend API (`asset_controller.py`)

#### Endpoints:

1. **GET `/api/assets/hierarchy`**
   - Returns nested tree structure
   - Filtered by user RBAC permissions
   - Includes tag counts at each level
   
2. **GET `/api/assets/flat`**
   - Returns flat list with full path
   - Useful for searching/filtering
   - Format: "Plant / Area / Equipment / Sub-Equipment / Component"

3. **GET `/api/assets/stats`**
   - Returns aggregate statistics
   - Plant, area, equipment counts
   - Trip tags, critical equipment counts

### Frontend Component (`AssetHierarchy.tsx`)

#### Features:
- ✅ Collapsible tree view
- ✅ Search across all levels
- ✅ Expand/Collapse all functionality
- ✅ Visual icons for each hierarchy level
- ✅ Tag criticality indicators (L1-L5)
- ✅ Trip category badges
- ✅ Tag count badges
- ✅ RBAC filtering (automatic)
- ✅ Responsive design

#### Icons:
- 🏭 Plant: Factory icon (blue)
- 📊 Area: Layers icon (green)
- 📦 Equipment: Box icon (orange)
- 💻 Sub-Equipment: Cpu icon (purple)
- 🔧 Component: Component icon (pink)
- 🏷️ Tag: Tag icon (gray)

## Data Flow

```
Database (tag_master)
    ↓
Backend API (Flask)
    ↓
RBAC Filter (per user)
    ↓
Hierarchical Transform
    ↓
JSON Response
    ↓
React Component
    ↓
Tree Display
```

## Database Schema

The hierarchy is built from these columns in `historian_meta.tag_master`:

```sql
CREATE TABLE historian_meta.tag_master (
    tag_id TEXT PRIMARY KEY,
    tag_name TEXT,
    plant TEXT,                    -- Level 1
    area TEXT,                     -- Level 2
    equipment TEXT,                -- Level 3
    sub_equipment TEXT,            -- Level 4
    components TEXT,               -- Level 5
    data_type TEXT,
    eng_unit TEXT,
    description TEXT,
    trip_category TEXT,
    equipment_criticality INTEGER,
    enabled BOOLEAN
);
```

## Usage

### 1. Backend Setup

Add to `app.py`:
```python
from controllers.asset_controller import asset_bp
app.register_blueprint(asset_bp)
```

### 2. Frontend Setup

Add route to your React app:
```typescript
import AssetBrowser from './pages/AssetBrowser';

<Route path="/assets" element={<AssetBrowser />} />
```

### 3. Navigation Link

Add to your main navigation:
```jsx
<NavLink to="/assets">Asset Browser</NavLink>
```

## API Examples

### Get Hierarchy
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:5000/api/assets/hierarchy
```

Response:
```json
{
  "hierarchy": [
    {
      "id": "plant_Plant1",
      "name": "Plant1",
      "type": "plant",
      "tag_count": 150,
      "children": [
        {
          "id": "area_Plant1_Area1",
          "name": "Area1",
          "type": "area",
          "tag_count": 50,
          "children": [...]
        }
      ]
    }
  ],
  "statistics": {
    "total_tags": 150,
    "filtered_tags": 0,
    "plants": 1,
    "timestamp": "2026-01-24T10:30:00"
  }
}
```

### Get Flat List
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:5000/api/assets/flat
```

Response:
```json
{
  "assets": [
    {
      "tag_id": "TEMP_01",
      "tag_name": "Temperature Sensor 1",
      "full_path": "Plant1 / Area1 / Turbine / Bearings / Sensor1",
      "plant": "Plant1",
      "area": "Area1",
      "equipment": "Turbine",
      "sub_equipment": "Bearings",
      "component": "Sensor1",
      "data_type": "Float",
      "eng_unit": "°C",
      "criticality": 5,
      "trip_category": "SAFETY_TRIP"
    }
  ],
  "count": 150
}
```

### Get Statistics
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:5000/api/assets/stats
```

Response:
```json
{
  "plants": 2,
  "areas": 8,
  "equipment": 45,
  "sub_equipment": 120,
  "components": 380,
  "total_tags": 1500,
  "trip_tags": 85,
  "critical_equipment_tags": 230
}
```

## Features

### 1. RBAC Integration
- Automatically filters based on user's plant/area permissions
- Shows only accessible assets
- Displays filtered count in statistics

### 2. Search Functionality
- Searches across all levels: plant, area, equipment, sub-equipment, component
- Searches tag IDs, names, and descriptions
- Real-time filtering as you type

### 3. Criticality Display
Equipment criticality levels:
- **L5** (Critical): Red badge - Safety systems
- **L4** (Urgent): Orange badge - Main production
- **L3** (High): Yellow badge - Key equipment
- **L2** (Medium): Blue badge - Isolated systems
- **L1** (Low): Green badge - Maintenance mode

### 4. Trip Category Badges
Shows trip/interlock classification:
- PROCESS_TRIP
- SAFETY_TRIP
- EMERGENCY_TRIP
- INTERLOCK

## Performance Considerations

1. **Database Query**: Single query fetches all data with proper indexing
2. **RBAC Filtering**: Applied in Python (lightweight)
3. **Tree Building**: O(n) complexity where n = number of tags
4. **Frontend Rendering**: Virtualized for large datasets
5. **Search**: Client-side filtering for instant response

## Recommended Indexes

Add these to your database for optimal performance:

```sql
-- Composite index for hierarchy traversal
CREATE INDEX idx_tag_master_hierarchy 
ON historian_meta.tag_master(plant, area, equipment, sub_equipment, components) 
WHERE enabled = true;

-- Index for search
CREATE INDEX idx_tag_master_search 
ON historian_meta.tag_master USING gin(to_tsvector('english', 
  COALESCE(tag_id, '') || ' ' || 
  COALESCE(tag_name, '') || ' ' || 
  COALESCE(description, '')
));
```

## Customization

### Change Colors
Edit `AssetHierarchy.tsx`:
```typescript
const getIcon = (type: string) => {
  switch (type) {
    case 'plant':
      return <Factory className="w-4 h-4 text-YOUR-COLOR" />;
    // ...
  }
};
```

### Add More Tag Information
Modify the tag display section:
```typescript
<div className="flex items-center gap-2">
  <Tag className="w-3 h-3 text-gray-400" />
  <span>{tag.tag_id}</span>
  {/* Add your custom fields here */}
</div>
```

### Export Functionality
Add export button:
```typescript
const exportToCSV = () => {
  // Flatten hierarchy and export as CSV
  const csv = flattenHierarchy(hierarchy);
  downloadCSV(csv, 'asset-hierarchy.csv');
};
```

## Testing

### Test Data
Add test data to `tag_master`:
```sql
INSERT INTO historian_meta.tag_master 
  (tag_id, tag_name, plant, area, equipment, sub_equipment, components, 
   data_type, enabled, equipment_criticality, trip_category)
VALUES
  ('TEMP_01', 'Turbine Temperature', 'Plant1', 'Production', 'Turbine1', 
   'Bearings', 'Sensor1', 'Float', true, 5, 'SAFETY_TRIP'),
  ('PRESS_01', 'Turbine Pressure', 'Plant1', 'Production', 'Turbine1', 
   'Inlet', 'Sensor2', 'Float', true, 4, 'PROCESS_TRIP');
```

### Test API
```bash
# Test hierarchy endpoint
python -c "
import requests
token = 'YOUR_TOKEN'
r = requests.get('http://localhost:5000/api/assets/hierarchy',
                 headers={'Authorization': f'Bearer {token}'})
print(r.json())
"
```

## Troubleshooting

### Issue: Empty hierarchy
**Cause**: No tags with `enabled = true`
**Solution**: Check `SELECT COUNT(*) FROM historian_meta.tag_master WHERE enabled = true`

### Issue: RBAC filtering too aggressive
**Cause**: User role configuration
**Solution**: Check role permissions in `historian_meta.role_tag_permissions`

### Issue: Slow loading
**Cause**: Missing indexes
**Solution**: Add recommended indexes above

### Issue: NULL values showing as "Unassigned"
**Cause**: Intentional behavior for incomplete hierarchy
**Solution**: Update tags with proper plant/area/equipment values

## Future Enhancements

1. **Drag & Drop**: Reorganize assets by dragging
2. **Bulk Edit**: Select multiple tags and update hierarchy
3. **Export**: Export hierarchy to Excel/CSV
4. **Context Menu**: Right-click for tag operations
5. **Real-time Updates**: WebSocket integration for live changes
6. **Asset Details Panel**: Click tag to see full details
7. **Comparison View**: Compare two assets side-by-side
8. **Health Status**: Show live health indicators per asset
9. **Maintenance Schedule**: Integration with maintenance system
10. **Asset Photos**: Upload and display equipment photos

## Security

- ✅ JWT token authentication required
- ✅ RBAC filtering per user
- ✅ SQL injection protection (parameterized queries)
- ✅ XSS protection (React auto-escaping)
- ✅ CORS configured for specific origins
- ✅ Rate limiting recommended (add middleware)

## License

Internal use only - Part of HMI system
